from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else f"exit={result.returncode}"


def _git_snapshot(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {"commit": None, "dirty": None}
    prefix = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root)]
    try:
        commit = subprocess.run(
            [*prefix, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        status = subprocess.run(
            [*prefix, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"commit": None, "dirty": None}
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def environment_snapshot(root: Path | None = None) -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "processor": platform.processor(),
        "git": command_version(["git", "--version"]),
        "cmake": command_version(["cmake", "--version"]),
        "ninja": command_version(["ninja", "--version"]),
        "repository": _git_snapshot(root.resolve() if root is not None else None),
    }
