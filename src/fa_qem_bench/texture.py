from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
import xatlas
from PIL import Image
from pygltflib import ARRAY_BUFFER, FLOAT, GLTF2, Accessor, BufferView
from scipy.ndimage import distance_transform_edt
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from .config import ExperimentConfig
from .mesh import Transform, geometric_weld, load_mesh, restored_vertices
from .runner import load_run_record
from .successive import atlas_faces_to_target_faces, load_successive_map, map_points_successively
from .util import atomic_json, sha256_file


def _face_tangent_basis(
    vertices: np.ndarray, faces: np.ndarray, uvs: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    triangles = vertices[faces]
    uv_triangles = uvs[faces]
    edge1 = triangles[:, 1] - triangles[:, 0]
    edge2 = triangles[:, 2] - triangles[:, 0]
    duv1 = uv_triangles[:, 1] - uv_triangles[:, 0]
    duv2 = uv_triangles[:, 2] - uv_triangles[:, 0]
    determinant = duv1[:, 0] * duv2[:, 1] - duv1[:, 1] * duv2[:, 0]
    safe = np.where(np.abs(determinant) > 1e-12, determinant, 1.0)
    tangent = (edge1 * duv2[:, 1, None] - edge2 * duv1[:, 1, None]) / safe[:, None]
    normal = np.cross(edge1, edge2)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-20)
    tangent -= normal * np.sum(normal * tangent, axis=1, keepdims=True)
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-20)
    fallback = np.cross(normal, np.array([0.0, 0.0, 1.0]))
    fallback_bad = np.linalg.norm(fallback, axis=1) <= 1e-12
    fallback[fallback_bad] = np.cross(normal[fallback_bad], np.array([0.0, 1.0, 0.0]))
    fallback /= np.maximum(np.linalg.norm(fallback, axis=1, keepdims=True), 1e-20)
    bad = np.abs(determinant) <= 1e-12
    tangent[bad] = fallback[bad]
    bitangent = np.cross(normal, tangent)
    return tangent, bitangent, normal


def _vertex_tangents(vertices: np.ndarray, faces: np.ndarray, uvs: np.ndarray, normals: np.ndarray) -> np.ndarray:
    face_tangent, face_bitangent, _ = _face_tangent_basis(vertices, faces, uvs)
    tangent_sum = np.zeros_like(vertices)
    bitangent_sum = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(tangent_sum, faces[:, corner], face_tangent)
        np.add.at(bitangent_sum, faces[:, corner], face_bitangent)
    tangent_sum -= normals * np.sum(normals * tangent_sum, axis=1, keepdims=True)
    tangent_sum /= np.maximum(np.linalg.norm(tangent_sum, axis=1, keepdims=True), 1e-20)
    handedness = np.where(
        np.sum(np.cross(normals, tangent_sum) * bitangent_sum, axis=1) < 0.0,
        -1.0,
        1.0,
    )
    return np.column_stack((tangent_sum, handedness)).astype(np.float32)


def _rasterize(uvs: np.ndarray, faces: np.ndarray, resolution: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    face_map = np.full((resolution, resolution), -1, dtype=np.int32)
    barycentric = np.zeros((resolution, resolution, 3), dtype=np.float32)
    pixel_uv = np.column_stack((uvs[:, 0] * (resolution - 1), (1.0 - uvs[:, 1]) * (resolution - 1)))
    for face_id, triangle in enumerate(pixel_uv[faces]):
        minimum = np.maximum(np.floor(triangle.min(axis=0)).astype(int), 0)
        maximum = np.minimum(np.ceil(triangle.max(axis=0)).astype(int), resolution - 1)
        if np.any(maximum < minimum):
            continue
        x = np.arange(minimum[0], maximum[0] + 1, dtype=np.float64) + 0.5
        y = np.arange(minimum[1], maximum[1] + 1, dtype=np.float64) + 0.5
        xx, yy = np.meshgrid(x, y)
        p0, p1, p2 = triangle
        denominator = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(denominator) <= 1e-20:
            continue
        w0 = ((p1[1] - p2[1]) * (xx - p2[0]) + (p2[0] - p1[0]) * (yy - p2[1])) / denominator
        w1 = ((p2[1] - p0[1]) * (xx - p2[0]) + (p0[0] - p2[0]) * (yy - p2[1])) / denominator
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        rows = slice(minimum[1], maximum[1] + 1)
        columns = slice(minimum[0], maximum[0] + 1)
        available = face_map[rows, columns] < 0
        write = inside & available
        face_map[rows, columns][write] = face_id
        local = barycentric[rows, columns]
        local[write] = np.column_stack((w0[write], w1[write], w2[write]))
    covered = face_map >= 0
    return face_map, barycentric, covered


def _sample_image(image: Image.Image, uvs: np.ndarray) -> np.ndarray:
    pixels = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    height, width = pixels.shape[:2]
    wrapped = np.mod(uvs, 1.0)
    x = wrapped[:, 0] * (width - 1)
    y = (1.0 - wrapped[:, 1]) * (height - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = (x - x0)[:, None]
    wy = (y - y0)[:, None]
    top = pixels[y0, x0] * (1.0 - wx) + pixels[y0, x1] * wx
    bottom = pixels[y1, x0] * (1.0 - wx) + pixels[y1, x1] * wx
    return top * (1.0 - wy) + bottom * wy


def _dilate(image: np.ndarray, covered: np.ndarray, pixels: int = 8) -> np.ndarray:
    distance_result = distance_transform_edt(~covered, return_indices=True)
    if not isinstance(distance_result, tuple):
        raise RuntimeError("distance transform did not return nearest-pixel indices")
    distance, indices = distance_result
    fill = (~covered) & (distance <= pixels)
    result = image.copy()
    result[fill] = image[indices[0][fill], indices[1][fill]]
    return result


def _as_image(values: np.ndarray, covered: np.ndarray, default: tuple[float, float, float]) -> Image.Image:
    canvas = np.empty((*covered.shape, 3), dtype=np.float32)
    canvas[:] = default
    canvas[covered] = values
    canvas = _dilate(canvas, covered)
    return Image.fromarray(np.clip(np.rint(canvas * 255.0), 0, 255).astype(np.uint8), mode="RGB")


def _append_tangents(path: Path, tangents: np.ndarray) -> None:
    gltf = GLTF2().load_binary(str(path))
    if gltf is None:
        raise RuntimeError(f"failed to load exported GLB: {path}")
    blob = gltf.binary_blob()
    if blob is None:
        raise RuntimeError(f"exported GLB has no binary blob: {path}")
    padding = (-len(blob)) % 4
    blob += b"\x00" * padding
    offset = len(blob)
    tangent_bytes = np.asarray(tangents, dtype="<f4").tobytes()
    if gltf.bufferViews is None or gltf.accessors is None or gltf.meshes is None or gltf.buffers is None:
        raise RuntimeError("exported GLB is missing required mesh buffers")
    gltf.bufferViews.append(BufferView(buffer=0, byteOffset=offset, byteLength=len(tangent_bytes), target=ARRAY_BUFFER))
    accessor_index = len(gltf.accessors)
    gltf.accessors.append(
        Accessor(
            bufferView=len(gltf.bufferViews) - 1,
            byteOffset=0,
            componentType=FLOAT,
            count=len(tangents),
            type="VEC4",
        )
    )
    gltf.meshes[0].primitives[0].attributes.TANGENT = accessor_index
    combined = blob + tangent_bytes
    gltf.buffers[0].byteLength = len(combined)
    gltf.set_binary_blob(combined)
    gltf.save_binary(str(path))


def bake_pbr_asset(
    source_glb: Path,
    target_path: Path,
    output_path: Path,
    center: list[float],
    diagonal: float,
    resolution: int = 2048,
    successive_map_path: Path | None = None,
) -> dict[str, Any]:
    source = load_mesh(source_glb, process=False)
    source.vertices = (np.asarray(source.vertices) - np.asarray(center)) / diagonal
    target = load_mesh(target_path, process=False)
    source_visual = cast(Any, source.visual)
    source_uv = np.asarray(source_visual.uv, dtype=np.float64)
    material = cast(Any, source_visual.material)
    target_vertices, target_faces, _ = geometric_weld(target.vertices, target.faces)
    target = trimesh.Trimesh(vertices=target_vertices, faces=target_faces, process=False)

    mapping, atlas_faces, atlas_uv = xatlas.parametrize(
        np.asarray(target.vertices, dtype=np.float32), np.asarray(target.faces, dtype=np.uint32)
    )
    atlas_faces = np.asarray(atlas_faces, dtype=np.int64)
    atlas_uv = np.asarray(atlas_uv, dtype=np.float64)
    atlas_vertices_unit = np.asarray(target.vertices, dtype=np.float64)[np.asarray(mapping, dtype=np.int64)]
    atlas_mesh = trimesh.Trimesh(vertices=atlas_vertices_unit, faces=atlas_faces, process=False)
    atlas_normals = np.asarray(atlas_mesh.vertex_normals, dtype=np.float64)
    face_map, barycentric, covered = _rasterize(atlas_uv, atlas_faces, resolution)
    rows, columns = np.nonzero(covered)
    mapped_faces = face_map[rows, columns]
    weights = barycentric[rows, columns].astype(np.float64)
    target_points = np.sum(atlas_vertices_unit[atlas_faces[mapped_faces]] * weights[:, :, None], axis=1)

    mapping_audit: dict[str, Any]
    if successive_map_path is not None:
        history = load_successive_map(successive_map_path)
        if len(history.final_face_ids) != len(target.faces):
            raise ValueError("successive map final-face count does not match the target mesh")
        atlas_to_target = atlas_faces_to_target_faces(np.asarray(mapping), atlas_faces, np.asarray(target.faces))
        final_internal_faces = history.final_face_ids[atlas_to_target[mapped_faces]]
        source_face_ids, mapping_audit = map_points_successively(history, target_points, final_internal_faces)
        if len(source_face_ids) and int(source_face_ids.max()) >= len(source.faces):
            raise ValueError("successive map references a face outside the source mesh")
        source_triangles = np.asarray(source.triangles)[source_face_ids]
        closest = trimesh.triangles.closest_point(source_triangles, target_points)
        mapping_audit["mode"] = "stmw_successive_one_ring_projection"
        mapping_audit["history_path"] = str(successive_map_path)
        mapping_audit["history_sha256"] = sha256_file(successive_map_path)
    else:
        closest, _, source_face_ids = trimesh.proximity.closest_point(source, target_points)
        mapping_audit = {"mode": "global_closest_surface"}
    source_triangles = np.asarray(source.triangles)[source_face_ids]
    source_barycentric = trimesh.triangles.points_to_barycentric(source_triangles, closest)
    mapped_source_uv = np.sum(
        source_uv[np.asarray(source.faces)[source_face_ids]] * source_barycentric[:, :, None],
        axis=1,
    )

    base_values = _sample_image(material.baseColorTexture, mapped_source_uv)
    mr_values = _sample_image(material.metallicRoughnessTexture, mapped_source_uv)
    emissive_values = _sample_image(material.emissiveTexture, mapped_source_uv)
    sampled_normal = _sample_image(material.normalTexture, mapped_source_uv) * 2.0 - 1.0
    sampled_normal /= np.maximum(np.linalg.norm(sampled_normal, axis=1, keepdims=True), 1e-20)

    source_tangent, source_bitangent, source_normal = _face_tangent_basis(
        np.asarray(source.vertices), np.asarray(source.faces), source_uv
    )
    world_normal = (
        source_tangent[source_face_ids] * sampled_normal[:, 0, None]
        + source_bitangent[source_face_ids] * sampled_normal[:, 1, None]
        + source_normal[source_face_ids] * sampled_normal[:, 2, None]
    )
    world_normal /= np.maximum(np.linalg.norm(world_normal, axis=1, keepdims=True), 1e-20)
    target_tangent, target_bitangent, target_normal = _face_tangent_basis(atlas_vertices_unit, atlas_faces, atlas_uv)
    baked_normal = np.column_stack(
        (
            np.sum(world_normal * target_tangent[mapped_faces], axis=1),
            np.sum(world_normal * target_bitangent[mapped_faces], axis=1),
            np.sum(world_normal * target_normal[mapped_faces], axis=1),
        )
    )
    baked_normal /= np.maximum(np.linalg.norm(baked_normal, axis=1, keepdims=True), 1e-20)
    baked_normal = baked_normal * 0.5 + 0.5

    base_image = _as_image(base_values, covered, (1.0, 1.0, 1.0))
    mr_image = _as_image(mr_values, covered, (0.0, 1.0, 0.0))
    emissive_image = _as_image(emissive_values, covered, (0.0, 0.0, 0.0))
    normal_image = _as_image(baked_normal, covered, (0.5, 0.5, 1.0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pbr = PBRMaterial(
        baseColorTexture=base_image,
        metallicRoughnessTexture=mr_image,
        normalTexture=normal_image,
        emissiveTexture=emissive_image,
        metallicFactor=1.0,
        roughnessFactor=1.0,
        doubleSided=True,
    )
    export_vertices = restored_vertices(atlas_vertices_unit, Transform(center=center, diagonal=diagonal))
    exported = trimesh.Trimesh(
        vertices=export_vertices,
        faces=atlas_faces,
        vertex_normals=atlas_normals,
        visual=TextureVisuals(uv=atlas_uv, material=pbr),
        process=False,
    )
    exported.export(output_path)
    tangents = _vertex_tangents(atlas_vertices_unit, atlas_faces, atlas_uv, atlas_normals)
    _append_tangents(output_path, tangents)
    return {
        "resolution": resolution,
        "atlas_vertices": int(len(atlas_vertices_unit)),
        "atlas_faces": int(len(atlas_faces)),
        "covered_texels": int(np.count_nonzero(covered)),
        "coverage": float(np.mean(covered)),
        "output_sha256": sha256_file(output_path),
        "channels": ["base_color", "normal", "metallic_roughness", "emissive"],
        "tangents": True,
        "mapping": mapping_audit,
    }


def rebake_run(config: ExperimentConfig, asset_run_id: str, resolution: int = 2048) -> dict[str, Any]:
    record_path = config.artifacts / "runs" / asset_run_id / "run.json"
    record = load_run_record(record_path)
    if record.get("track") != "asset":
        raise ValueError("rebake expects an asset-track run")
    if record.get("status") != "SUCCESS" or not record.get("output_path"):
        raise ValueError(f"asset geometry is unavailable: {asset_run_id}")
    manifest = json.loads((config.artifacts / "prepared" / "manifest.json").read_text(encoding="utf-8"))
    output = config.artifacts / "runs" / asset_run_id / "asset-pbr.glb"
    successive_map_path: Path | None = None
    research_run_id = str(record.get("parameters", {}).get("research_run_id", ""))
    if record.get("method") == "stmw" and research_run_id:
        research = load_run_record(config.artifacts / "runs" / research_run_id / "run.json")
        mapping_relative = research.get("parameters", {}).get("successive_mapping_path")
        expected_hash = research.get("parameters", {}).get("successive_mapping_sha256")
        lineage_action = record.get("repair_lineage", {}).get("action")
        if mapping_relative and lineage_action == "not_required":
            candidate = config.root / str(mapping_relative)
            if sha256_file(candidate) != expected_hash:
                raise ValueError("STMW successive mapping history hash mismatch")
            successive_map_path = candidate
    metrics = bake_pbr_asset(
        config.source,
        config.root / record["output_path"],
        output,
        manifest["transform"]["center"],
        float(manifest["transform"]["diagonal"]),
        resolution,
        successive_map_path,
    )
    record["output_path"] = str(output.relative_to(config.root))
    record["output_sha256"] = metrics["output_sha256"]
    record.setdefault("metrics", {})["rebake"] = metrics
    atomic_json(record_path, record)
    return metrics
