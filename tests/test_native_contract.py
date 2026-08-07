from pathlib import Path


def test_native_fixtures_are_tracked() -> None:
    fixture_root = Path("tests/fixtures")
    assert (fixture_root / "octahedron.obj").is_file()
    assert (fixture_root / "disconnected_triangles.obj").is_file()
    assert (fixture_root / "interior_close_triangles.obj").is_file()
    assert (fixture_root / "qem4vr_uv_seam.obj").is_file()


def test_faqem_is_runnable_but_not_counted_as_a_baseline() -> None:
    from fa_qem_bench.config import RUNNABLE_METHODS, SUPPORTED_METHODS

    assert "fa-qem" in RUNNABLE_METHODS
    assert "fa-qem" not in SUPPORTED_METHODS
