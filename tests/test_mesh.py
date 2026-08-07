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


def test_attribute_seams_do_not_change_welded_components() -> None:
    source = trimesh.creation.icosphere(subdivisions=1)
    corner_vertices = np.asarray(source.vertices)[np.asarray(source.faces)].reshape(-1, 3)
    corner_faces = np.arange(len(corner_vertices), dtype=np.int64).reshape(-1, 3)
    attribute_mesh = trimesh.Trimesh(vertices=corner_vertices, faces=corner_faces, process=False)
    welded_vertices, welded_faces, _ = geometric_weld(attribute_mesh.vertices, attribute_mesh.faces)
    welded = trimesh.Trimesh(vertices=welded_vertices, faces=welded_faces, process=False)

    assert mesh_topology(attribute_mesh)["components"] == len(attribute_mesh.faces)
    assert mesh_topology(welded)["components"] == 1
    assert mesh_topology(welded)["watertight"]
