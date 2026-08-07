from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .util import atomic_json, sha256_file


@dataclass(frozen=True)
class Transform:
    center: list[float]
    diagonal: float


def load_mesh(path: Path, *, process: bool = False) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="scene", process=process)
    if isinstance(loaded, trimesh.Scene):
        geometries = []
        for node_name in loaded.graph.nodes_geometry:
            transform, geometry_name = loaded.graph[node_name]
            geometry = loaded.geometry[geometry_name].copy()
            geometry.apply_transform(transform)
            geometries.append(geometry)
        if not geometries:
            raise ValueError(f"no mesh geometry in {path}")
        mesh = geometries[0] if len(geometries) == 1 else trimesh.util.concatenate(geometries)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise TypeError(f"unsupported loaded object: {type(loaded)!r}")
    if len(mesh.faces) == 0:
        raise ValueError(f"empty mesh: {path}")
    return mesh


def normalization_transform(mesh: trimesh.Trimesh) -> Transform:
    bounds = np.asarray(mesh.bounds, dtype=np.float64)
    center = (bounds[0] + bounds[1]) / 2.0
    diagonal = float(np.linalg.norm(bounds[1] - bounds[0]))
    if not np.isfinite(diagonal) or diagonal <= 0:
        raise ValueError("mesh bounding-box diagonal must be positive and finite")
    return Transform(center=center.tolist(), diagonal=diagonal)


def normalized_vertices(vertices: np.ndarray, transform: Transform) -> np.ndarray:
    return (
        np.asarray(vertices, dtype=np.float64) - np.asarray(transform.center)
    ) / transform.diagonal


def restored_vertices(vertices: np.ndarray, transform: Transform) -> np.ndarray:
    return np.asarray(vertices, dtype=np.float64) * transform.diagonal + np.asarray(
        transform.center
    )


def geometric_weld(
    vertices: np.ndarray, faces: np.ndarray, digits: int = 6
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rounded = np.round(np.asarray(vertices, dtype=np.float64), decimals=digits)
    _, first, inverse = np.unique(rounded, axis=0, return_index=True, return_inverse=True)
    welded_vertices = np.asarray(vertices, dtype=np.float64)[first]
    welded_faces = inverse[np.asarray(faces, dtype=np.int64)]
    nondegenerate = (
        (welded_faces[:, 0] != welded_faces[:, 1])
        & (welded_faces[:, 1] != welded_faces[:, 2])
        & (welded_faces[:, 2] != welded_faces[:, 0])
    )
    return welded_vertices, welded_faces[nondegenerate], inverse


def mesh_topology(mesh: trimesh.Trimesh) -> dict[str, Any]:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edges = np.sort(faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    areas = np.asarray(mesh.area_faces)
    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(faces)),
        "boundary_edges": int(np.count_nonzero(counts == 1)),
        "nonmanifold_edges": int(np.count_nonzero(counts > 2)),
        "degenerate_faces": int(np.count_nonzero(~np.isfinite(areas) | (areas <= 1e-15))),
        "components": int(len(mesh.split(only_watertight=False))),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "finite_vertices": bool(np.isfinite(mesh.vertices).all()),
    }


def prepare_source(source: Path, destination: Path, expected_faces: int) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    raw = load_mesh(source, process=False)
    if len(raw.faces) != expected_faces:
        raise ValueError(
            f"source face count mismatch: expected {expected_faces}, got {len(raw.faces)}"
        )
    transform = normalization_transform(raw)
    raw_vertices = normalized_vertices(raw.vertices, transform)
    geom_vertices, geom_faces, corner_to_geometry = geometric_weld(raw_vertices, raw.faces)
    geometry = trimesh.Trimesh(vertices=geom_vertices, faces=geom_faces, process=False)

    np.savez_compressed(
        destination / "canonical.npz",
        attribute_vertices=raw_vertices,
        attribute_faces=np.asarray(raw.faces, dtype=np.int64),
        geometry_vertices=geom_vertices,
        geometry_faces=geom_faces,
        attribute_to_geometry=corner_to_geometry,
        center=np.asarray(transform.center),
        diagonal=np.asarray(transform.diagonal),
    )
    geometry.export(destination / "geometry_unit.obj")
    raw_unit = raw.copy()
    raw_unit.vertices = raw_vertices
    raw_unit.export(destination / "attribute_unit.glb")
    raw_unit.export(destination / "attribute_unit.obj")

    displacement = np.linalg.norm(geom_vertices[corner_to_geometry] - raw_vertices, axis=1)
    manifest = {
        "schema_version": 1,
        "source": str(source),
        "source_sha256": sha256_file(source),
        "transform": asdict(transform),
        "attribute_view": mesh_topology(raw),
        "geometry_view": mesh_topology(geometry),
        "attribute_to_geometry_count": int(len(corner_to_geometry)),
        "max_weld_displacement_unit": float(displacement.max(initial=0.0)),
        "files": {
            "canonical_npz": "canonical.npz",
            "geometry_obj": "geometry_unit.obj",
            "attribute_glb": "attribute_unit.glb",
            "attribute_obj": "attribute_unit.obj",
        },
    }
    atomic_json(destination / "manifest.json", manifest)
    return manifest
