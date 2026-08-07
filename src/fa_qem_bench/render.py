from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from .mesh import load_mesh
from .texture import _sample_image


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


def render_mesh(
    mesh: trimesh.Trimesh,
    resolution: int = 512,
    textured: bool = False,
) -> Image.Image:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    screen, _, viewed = _screen_coordinates(vertices, resolution)
    zbuffer = np.full((resolution, resolution), -np.inf, dtype=np.float64)
    canvas = np.full((resolution, resolution, 3), 245.0, dtype=np.float32)
    face_normals = np.cross(viewed[faces[:, 1]] - viewed[faces[:, 0]], viewed[faces[:, 2]] - viewed[faces[:, 0]])
    face_normals /= np.maximum(np.linalg.norm(face_normals, axis=1, keepdims=True), 1e-20)
    light = np.array([-0.25, -0.35, 0.9])
    light /= np.linalg.norm(light)
    shade = 0.25 + 0.75 * np.abs(face_normals @ light)
    uvs: np.ndarray | None = None
    texture = None
    if textured:
        visual = cast(Any, mesh.visual)
        material = cast(Any, getattr(visual, "material", None))
        if getattr(visual, "uv", None) is not None and getattr(material, "baseColorTexture", None) is not None:
            uvs = np.asarray(visual.uv, dtype=np.float64)
            texture = material.baseColorTexture

    for face_id, face in enumerate(faces):
        triangle = screen[face]
        minimum = np.maximum(np.floor(triangle[:, :2].min(axis=0)).astype(int), 0)
        maximum = np.minimum(np.ceil(triangle[:, :2].max(axis=0)).astype(int), resolution - 1)
        if np.any(maximum < minimum):
            continue
        x = np.arange(minimum[0], maximum[0] + 1, dtype=np.float64) + 0.5
        y = np.arange(minimum[1], maximum[1] + 1, dtype=np.float64) + 0.5
        xx, yy = np.meshgrid(x, y)
        p0, p1, p2 = triangle[:, :2]
        denominator = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(denominator) <= 1e-20:
            continue
        w0 = ((p1[1] - p2[1]) * (xx - p2[0]) + (p2[0] - p1[0]) * (yy - p2[1])) / denominator
        w1 = ((p2[1] - p0[1]) * (xx - p2[0]) + (p0[0] - p2[0]) * (yy - p2[1])) / denominator
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        depth = w0 * triangle[0, 2] + w1 * triangle[1, 2] + w2 * triangle[2, 2]
        rows = slice(minimum[1], maximum[1] + 1)
        columns = slice(minimum[0], maximum[0] + 1)
        local_depth = zbuffer[rows, columns]
        write = inside & (depth > local_depth)
        if not np.any(write):
            continue
        local_depth[write] = depth[write]
        local_canvas = canvas[rows, columns]
        if uvs is not None and texture is not None:
            weights = np.column_stack((w0[write], w1[write], w2[write]))
            pixel_uv = np.sum(uvs[face] * weights[:, :, None], axis=1)
            color = _sample_image(texture, pixel_uv) * 255.0 * (0.45 + 0.55 * shade[face_id])
            local_canvas[write] = color
        else:
            local_canvas[write] = np.array([174.0, 181.0, 188.0]) * shade[face_id]
    return Image.fromarray(np.clip(np.rint(canvas), 0, 255).astype(np.uint8), mode="RGB")


def render_contact_sheet(
    mesh_path: Path,
    output_path: Path,
    center: list[float],
    diagonal: float,
    coordinates_are_normalized: bool,
    label: str,
    resolution: int = 512,
) -> dict[str, Any]:
    mesh = load_mesh(mesh_path, process=False)
    if not coordinates_are_normalized:
        mesh.vertices = (np.asarray(mesh.vertices) - np.asarray(center)) / diagonal
    neutral = render_mesh(mesh, resolution, textured=False)
    textured = render_mesh(mesh, resolution, textured=True)
    header = 36
    sheet = Image.new("RGB", (resolution * 2, resolution + header), "white")
    sheet.paste(neutral, (0, header))
    sheet.paste(textured, (resolution, header))
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 10), f"{label} | neutral clay", fill="black")
    draw.text((resolution + 10, 10), f"{label} | PBR/base color", fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return {"path": str(output_path), "width": sheet.width, "height": sheet.height}
