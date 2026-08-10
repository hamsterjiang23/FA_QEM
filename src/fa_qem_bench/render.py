from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from .mesh import load_mesh
from .texture import _sample_image


@dataclass(frozen=True)
class BaseColorSource:
    mesh: trimesh.Trimesh
    uv: np.ndarray
    image: Image.Image
    image_path: Path | None


def load_base_color_source(
    mesh_path: Path,
    center: list[float],
    diagonal: float,
    image_path: Path | None = None,
) -> BaseColorSource:
    mesh = load_mesh(mesh_path, process=False)
    mesh.vertices = (np.asarray(mesh.vertices, dtype=np.float64) - np.asarray(center)) / diagonal
    visual = cast(Any, mesh.visual)
    uv = getattr(visual, "uv", None)
    if uv is None:
        raise ValueError(f"source mesh has no UV coordinates: {mesh_path}")
    if image_path is not None:
        image = Image.open(image_path).convert("RGB")
    else:
        material = cast(Any, getattr(visual, "material", None))
        embedded = getattr(material, "baseColorTexture", None)
        if embedded is None:
            raise ValueError(f"source mesh has no embedded base-color texture: {mesh_path}")
        image = embedded.convert("RGB")
    return BaseColorSource(
        mesh=mesh,
        uv=np.asarray(uv, dtype=np.float64),
        image=image,
        image_path=image_path,
    )


def _view_matrix() -> np.ndarray:
    yaw = np.deg2rad(18.0)
    pitch = np.deg2rad(-22.0)
    rotate_z = np.array([[np.cos(yaw), -np.sin(yaw), 0.0], [np.sin(yaw), np.cos(yaw), 0.0], [0.0, 0.0, 1.0]])
    rotate_x = np.array([[1.0, 0.0, 0.0], [0.0, np.cos(pitch), -np.sin(pitch)], [0.0, np.sin(pitch), np.cos(pitch)]])
    return rotate_x @ rotate_z


def _screen_coordinates(vertices: np.ndarray, resolution: int) -> tuple[np.ndarray, float, np.ndarray]:
    viewed = vertices @ _view_matrix().T
    half_extent = 0.52
    scale = (resolution - 1) / (2.0 * half_extent)
    screen = np.column_stack(
        (
            (viewed[:, 0] + half_extent) * scale,
            (half_extent - viewed[:, 1]) * scale,
            viewed[:, 2],
        )
    )
    return screen, scale, viewed


def _source_projected_face_colors(mesh: trimesh.Trimesh, source: BaseColorSource) -> np.ndarray:
    target_centroids = np.asarray(mesh.triangles_center, dtype=np.float64)
    closest, _, source_face_ids = trimesh.proximity.closest_point(source.mesh, target_centroids)
    source_faces = np.asarray(source.mesh.faces, dtype=np.int64)[source_face_ids]
    source_triangles = np.asarray(source.mesh.vertices, dtype=np.float64)[source_faces]
    barycentric = trimesh.triangles.points_to_barycentric(source_triangles, closest)
    source_uv = np.sum(source.uv[source_faces] * barycentric[:, :, None], axis=1)
    return _sample_image(source.image, source_uv) * 255.0


def _render_mesh(
    mesh: trimesh.Trimesh,
    resolution: int = 512,
    textured: bool = False,
    base_color_source: BaseColorSource | None = None,
) -> tuple[Image.Image, str]:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    screen, _, viewed = _screen_coordinates(vertices, resolution)
    canvas = Image.new("RGB", (resolution, resolution), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    face_normals = np.cross(viewed[faces[:, 1]] - viewed[faces[:, 0]], viewed[faces[:, 2]] - viewed[faces[:, 0]])
    face_normals /= np.maximum(np.linalg.norm(face_normals, axis=1, keepdims=True), 1e-20)
    light = np.array([-0.25, -0.35, 0.9])
    light /= np.linalg.norm(light)
    shade = 0.25 + 0.75 * np.abs(face_normals @ light)
    colors = np.repeat(np.array([[174.0, 181.0, 188.0]]), len(faces), axis=0) * shade[:, None]
    texture_mode = "neutral_clay"
    if textured:
        visual = cast(Any, mesh.visual)
        material = cast(Any, getattr(visual, "material", None))
        embedded = getattr(material, "baseColorTexture", None)
        if getattr(visual, "uv", None) is not None and embedded is not None:
            uvs = np.asarray(visual.uv, dtype=np.float64)
            centroid_uv = np.mean(uvs[faces], axis=1)
            colors = _sample_image(embedded, centroid_uv) * 255.0
            texture_mode = "embedded_base_color"
        elif getattr(visual, "uv", None) is not None and base_color_source is not None:
            uvs = np.asarray(visual.uv, dtype=np.float64)
            centroid_uv = np.mean(uvs[faces], axis=1)
            colors = _sample_image(base_color_source.image, centroid_uv) * 255.0
            texture_mode = "original_uv_with_source_base_color"
        elif base_color_source is not None:
            colors = _source_projected_face_colors(mesh, base_color_source)
            texture_mode = "projected_source_base_color"
        else:
            texture_mode = "gray_fallback_no_base_color"
        colors *= 0.45 + 0.55 * shade[:, None]

    triangles = screen[faces]
    visible = (
        (triangles[:, :, 0].max(axis=1) >= 0)
        & (triangles[:, :, 0].min(axis=1) < resolution)
        & (triangles[:, :, 1].max(axis=1) >= 0)
        & (triangles[:, :, 1].min(axis=1) < resolution)
    )
    depth_order = np.argsort(np.mean(triangles[:, :, 2], axis=1))
    for face_id in depth_order[visible[depth_order]]:
        polygon = [tuple(point) for point in triangles[face_id, :, :2]]
        color = tuple(int(value) for value in np.clip(np.rint(colors[face_id]), 0, 255))
        draw.polygon(polygon, fill=color)
    return canvas, texture_mode


def render_mesh(
    mesh: trimesh.Trimesh,
    resolution: int = 512,
    textured: bool = False,
    base_color_source: BaseColorSource | None = None,
) -> Image.Image:
    image, _ = _render_mesh(mesh, resolution, textured, base_color_source)
    return image


def render_contact_sheet(
    mesh_path: Path,
    output_path: Path,
    center: list[float],
    diagonal: float,
    coordinates_are_normalized: bool,
    label: str,
    resolution: int = 512,
    base_color_source: BaseColorSource | None = None,
) -> dict[str, Any]:
    mesh = load_mesh(mesh_path, process=False)
    if not coordinates_are_normalized:
        mesh.vertices = (np.asarray(mesh.vertices) - np.asarray(center)) / diagonal
    neutral, _ = _render_mesh(mesh, resolution, textured=False)
    textured, texture_mode = _render_mesh(
        mesh,
        resolution,
        textured=True,
        base_color_source=base_color_source,
    )
    header = 36
    sheet = Image.new("RGB", (resolution * 2, resolution + header), "white")
    sheet.paste(neutral, (0, header))
    sheet.paste(textured, (resolution, header))
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 10), f"{label} | neutral clay", fill="black")
    texture_labels = {
        "embedded_base_color": "embedded PBR/base color",
        "original_uv_with_source_base_color": "original UV + source base color",
        "projected_source_base_color": "source-projected base color",
        "gray_fallback_no_base_color": "no base color (gray fallback)",
    }
    draw.text((resolution + 10, 10), f"{label} | {texture_labels[texture_mode]}", fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return {
        "path": str(output_path),
        "width": sheet.width,
        "height": sheet.height,
        "renderer": "depth-sorted face-centroid preview",
        "base_color_mode": texture_mode,
        "base_color_source": (
            str(base_color_source.image_path)
            if base_color_source is not None and base_color_source.image_path is not None
            else None
        ),
    }
