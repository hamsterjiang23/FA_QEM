from __future__ import annotations

import numpy as np

from fa_qem_bench.texture import _face_tangent_basis, _rasterize


def test_face_tangent_basis_is_orthonormal() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    faces = np.array([[0, 1, 2]])
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    tangent, bitangent, normal = _face_tangent_basis(vertices, faces, uvs)
    np.testing.assert_allclose(tangent, [[1.0, 0.0, 0.0]], atol=1e-12)
    np.testing.assert_allclose(bitangent, [[0.0, 1.0, 0.0]], atol=1e-12)
    np.testing.assert_allclose(normal, [[0.0, 0.0, 1.0]], atol=1e-12)


def test_rasterize_assigns_covered_texels() -> None:
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    faces = np.array([[0, 1, 2]])
    face_map, barycentric, covered = _rasterize(uvs, faces, 16)
    assert np.count_nonzero(covered) > 0
    assert np.all(face_map[covered] == 0)
    np.testing.assert_allclose(barycentric[covered].sum(axis=1), 1.0, atol=1e-6)
