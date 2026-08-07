import numpy as np
import trimesh

from fa_qem_bench.evaluate import _closest_distances, triangle_quality


def test_triangle_quality_is_normalized_for_equilateral_triangle() -> None:
    mesh = trimesh.Trimesh(
        vertices=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, np.sqrt(3.0) / 2.0, 0.0]]),
        faces=np.array([[0, 1, 2]]),
        process=False,
    )

    quality = triangle_quality(mesh)

    assert np.isclose(quality["minimum_angle_degrees"], 60.0)
    assert np.isclose(quality["aspect_ratio_p95"], 1.0)
    assert np.isclose(quality["aspect_ratio_maximum"], 1.0)


def test_closest_distances_chunks_large_queries(monkeypatch) -> None:
    mesh = trimesh.creation.icosphere(subdivisions=1)
    points = np.zeros((5000, 3), dtype=np.float64)
    calls: list[int] = []

    def fake_closest_point(_mesh, chunk):
        calls.append(len(chunk))
        return chunk, np.zeros(len(chunk)), np.zeros(len(chunk), dtype=np.int64)

    monkeypatch.setattr("trimesh.proximity.closest_point", fake_closest_point)
    distances = _closest_distances(mesh, points)
    assert len(distances) == len(points)
    assert calls == [2048, 2048, 904]
