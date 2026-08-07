from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .mesh import load_mesh, mesh_topology


def _sample(mesh: trimesh.Trimesh, count: int, seed: int) -> np.ndarray:
    sampled = trimesh.sample.sample_surface(mesh, count, seed=seed)
    return np.asarray(sampled[0], dtype=np.float64)


def _closest_distances(mesh: trimesh.Trimesh, points: np.ndarray) -> np.ndarray:
    _, distances, _ = trimesh.proximity.closest_point(mesh, points)
    return np.asarray(distances, dtype=np.float64)


def geometry_metrics(
    reference: trimesh.Trimesh, result: trimesh.Trimesh, count: int, seed: int
) -> dict[str, float]:
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


def evaluate_paths(
    reference_path: Path,
    result_path: Path,
    count: int,
    seed: int,
    original_diagonal: float = 1.0,
) -> dict[str, Any]:
    reference = load_mesh(reference_path, process=False)
    result = load_mesh(result_path, process=False)
    normalized = geometry_metrics(reference, result, count=count, seed=seed)
    original = {
        "samples_per_direction": normalized["samples_per_direction"],
        "hausdorff_symmetric_sampled": normalized["hausdorff_symmetric_sampled"]
        * original_diagonal,
        "chamfer_mean_squared_symmetric": normalized["chamfer_mean_squared_symmetric"]
        * original_diagonal**2,
        "mean_distance_result_to_reference": normalized[
            "mean_distance_result_to_reference"
        ]
        * original_diagonal,
        "mean_distance_reference_to_result": normalized[
            "mean_distance_reference_to_result"
        ]
        * original_diagonal,
    }
    return {
        "geometry": {
            "normalized_unit_diagonal": normalized,
            "original_units": original,
        },
        "topology": mesh_topology(result),
    }
