from pathlib import Path


def test_native_fixtures_are_tracked() -> None:
    fixture_root = Path("tests/fixtures")
    assert (fixture_root / "octahedron.obj").is_file()
    assert (fixture_root / "disconnected_triangles.obj").is_file()

