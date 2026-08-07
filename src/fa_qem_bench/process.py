from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True)
class ProcessResult:
    command: list[str]
    returncode: int
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int
    stdout_path: Path
    stderr_path: Path


def run_measured(command: list[str], cwd: Path, log_dir: Path, timeout: float | None = None) -> ProcessResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
    start = time.perf_counter()
    peak_rss = 0
    cpu_seconds = 0.0
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr)
        tracked = psutil.Process(process.pid)
        while process.poll() is None:
            try:
                children = tracked.children(recursive=True)
                processes = [tracked, *children]
                peak_rss = max(peak_rss, sum(item.memory_info().rss for item in processes))
                cpu_seconds = max(
                    cpu_seconds,
                    sum(item.cpu_times().user + item.cpu_times().system for item in processes),
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            if timeout is not None and time.perf_counter() - start > timeout:
                process.kill()
                raise TimeoutError(f"command exceeded {timeout}s: {command}")
            time.sleep(0.1)
        returncode = process.wait()
    return ProcessResult(
        command=command,
        returncode=returncode,
        wall_seconds=time.perf_counter() - start,
        cpu_seconds=cpu_seconds,
        peak_rss_bytes=peak_rss,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
