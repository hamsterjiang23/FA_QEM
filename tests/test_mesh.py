import numpy as np
import trimesh

from fa_qem_bench.mesh import (
    geometric_weld,
    mesh_topology,
    normalization_transform,
    normalized_vertices,
    restored_vertices,
)


def test_normalization_round_trip() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=1)
    transform = normalization_transform(mesh)
    restored = restored_vertices(normalized_vertices(mesh.vertices, transform), transform)
    assert np.allclose(restored, mesh.vertices)


def test_weld_preserves_surface_positions() -> None:
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]], dtype=float)
    faces = np.array([[0, 1, 2], [3, 2, 1]])
    welded_vertices, welded_faces, inverse = geometric_weld(vertices, faces)
    assert len(welded_vertices) == 3
    assert np.allclose(welded_vertices[inverse], vertices)
    assert len(welded_faces) == 2


def test_closed_fixture_topology() -> None:
    topology = mesh_topology(trimesh.creation.icosphere(subdivisions=1))
    assert topology["boundary_edges"] == 0
    assert topology["nonmanifold_edges"] == 0
    assert topology["watertight"]
