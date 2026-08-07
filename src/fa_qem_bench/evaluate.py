from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh

from .mesh import geometric_weld, load_mesh, mesh_topology
from .texture import _sample_image


def _sample(mesh: trimesh.Trimesh, count: int, seed: int) -> np.ndarray:
    sampled = trimesh.sample.sample_surface(mesh, count, seed=seed)
    return np.asarray(sampled[0], dtype=np.float64)


def _closest_distances(mesh: trimesh.Trimesh, points: np.ndarray) -> np.ndarray:
    _, distances, _ = trimesh.proximity.closest_point(mesh, points)
    return np.asarray(distances, dtype=np.float64)


def geometry_metrics(reference: trimesh.Trimesh, result: trimesh.Trimesh, count: int, seed: int) -> dict[str, float]:
    reference_points = _sample(reference, count, seed)
    result_points = _sample(result, count, seed + 1)
    result_to_reference = _closest_distances(reference, result_points)
    reference_to_result = _closest_distances(result, reference_points)
    return {
        "samples_per_direction": count,
        "hausdorff_symmetric_sampled": float(
            max(result_to_reference.max(initial=0.0), reference_to_result.max(initial=0.0))
        ),
        "chamfer_mean_squared_symmetric": float(
            0.5 * (np.mean(result_to_reference**2) + np.mean(reference_to_result**2))
        ),
        "mean_distance_result_to_reference": float(np.mean(result_to_reference)),
        "mean_distance_reference_to_result": float(np.mean(reference_to_result)),
    }


def _colors_at_surface_points(mesh: trimesh.Trimesh, points: np.ndarray, face_ids: np.ndarray) -> np.ndarray:
    visual = cast(Any, mesh.visual)
    material = cast(Any, visual.material)
    if getattr(visual, "uv", None) is None or getattr(material, "baseColorTexture", None) is None:
        raise ValueError("mesh has no base-color texture coordinates")
    triangles = np.asarray(mesh.triangles)[face_ids]
    barycentric = trimesh.triangles.points_to_barycentric(triangles, points)
    face_uv = np.asarray(visual.uv)[np.asarray(mesh.faces)[face_ids]]
    uvs = np.sum(face_uv * barycentric[:, :, None], axis=1)
    colors = _sample_image(material.baseColorTexture, uvs)
    factor = np.asarray(getattr(material, "baseColorFactor", [255, 255, 255, 255]), dtype=np.float64)[:3]
    if factor.max(initial=1.0) > 1.0:
        factor /= 255.0
    return np.clip(colors * factor, 0.0, 1.0)


def texture_metrics(reference: trimesh.Trimesh, result: trimesh.Trimesh, count: int, seed: int) -> dict[str, Any]:
    reference_sample = trimesh.sample.sample_surface(reference, count, seed=seed)
    result_sample = trimesh.sample.sample_surface(result, count, seed=seed + 1)
    reference_points = np.asarray(reference_sample[0], dtype=np.float64)
    reference_faces = np.asarray(reference_sample[1], dtype=np.int64)
    result_points = np.asarray(result_sample[0], dtype=np.float64)
    result_faces = np.asarray(result_sample[1], dtype=np.int64)
    reference_colors = _colors_at_surface_points(reference, reference_points, reference_faces)
    result_colors = _colors_at_surface_points(result, result_points, result_faces)

    closest_reference, _, closest_reference_faces = trimesh.proximity.closest_point(reference, result_points)
    closest_result, _, closest_result_faces = trimesh.proximity.closest_point(result, reference_points)
    paired_reference_colors = _colors_at_surface_points(reference, closest_reference, closest_reference_faces)
    paired_result_colors = _colors_at_surface_points(result, closest_result, closest_result_faces)
    result_to_reference = np.linalg.norm(result_colors - paired_reference_colors, axis=1)
    reference_to_result = np.linalg.norm(reference_colors - paired_result_colors, axis=1)
    return {
        "status": "evaluated",
        "samples_per_direction": count,
        "symmetric_mean_rgb_l2": float(0.5 * (np.mean(result_to_reference) + np.mean(reference_to_result))),
        "mean_rgb_l2_result_to_reference": float(np.mean(result_to_reference)),
        "mean_rgb_l2_reference_to_result": float(np.mean(reference_to_result)),
    }


def evaluate_paths(
    reference_path: Path,
    result_path: Path,
    count: int,
    seed: int,
    original_diagonal: float = 1.0,
    input_is_normalized: bool = True,
    texture_count: int | None = None,
) -> dict[str, Any]:
    reference = load_mesh(reference_path, process=False)
    result = load_mesh(result_path, process=False)
    raw = geometry_metrics(reference, result, count=count, seed=seed)
    if input_is_normalized:
        normalized = raw
        original_scale = original_diagonal
    else:
        original_scale = 1.0
        normalized = {
            "samples_per_direction": raw["samples_per_direction"],
            "hausdorff_symmetric_sampled": raw["hausdorff_symmetric_sampled"] / original_diagonal,
            "chamfer_mean_squared_symmetric": raw["chamfer_mean_squared_symmetric"] / original_diagonal**2,
            "mean_distance_result_to_reference": raw["mean_distance_result_to_reference"] / original_diagonal,
            "mean_distance_reference_to_result": raw["mean_distance_reference_to_result"] / original_diagonal,
        }
    original = {
        "samples_per_direction": raw["samples_per_direction"],
        "hausdorff_symmetric_sampled": raw["hausdorff_symmetric_sampled"] * original_scale,
        "chamfer_mean_squared_symmetric": raw["chamfer_mean_squared_symmetric"] * original_scale**2,
        "mean_distance_result_to_reference": raw["mean_distance_result_to_reference"] * original_scale,
        "mean_distance_reference_to_result": raw["mean_distance_reference_to_result"] * original_scale,
    }
    topology: dict[str, Any] = {"attribute_view": mesh_topology(result)}
    if input_is_normalized:
        topology["geometry_view"] = topology["attribute_view"]
    else:
        welded_vertices, welded_faces, _ = geometric_weld(np.asarray(result.vertices), np.asarray(result.faces))
        topology["geometry_view"] = mesh_topology(
            trimesh.Trimesh(vertices=welded_vertices, faces=welded_faces, process=False)
        )
    metrics: dict[str, Any] = {
        "geometry": {
            "normalized_unit_diagonal": normalized,
            "original_units": original,
        },
        "topology": topology,
    }
    if texture_count is not None:
        try:
            metrics["texture"] = texture_metrics(reference, result, texture_count, seed + 10)
        except ValueError as error:
            metrics["texture"] = {"status": "N/A", "reason": str(error)}
    return metrics
