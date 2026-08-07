from __future__ import annotations

import subprocess
from pathlib import Path

from fa_qem_bench.util import environment_snapshot


def test_environment_snapshot_records_repository_state(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "fixture"], check=True)

    clean = environment_snapshot(tmp_path)["repository"]
    assert clean["commit"]
    assert clean["dirty"] is False

    tracked.write_text("dirty\n", encoding="utf-8")
    assert environment_snapshot(tmp_path)["repository"]["dirty"] is True
