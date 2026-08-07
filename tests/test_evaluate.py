import numpy as np
import trimesh

from fa_qem_bench.evaluate import triangle_quality


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
