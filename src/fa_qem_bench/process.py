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
    resource_source: str


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
        resource_source="psutil_process_tree",
    )


def _gnu_time_metrics(stderr_text: str) -> tuple[float, int]:
    values: dict[str, str] = {}
    for line in stderr_text.splitlines():
        stripped = line.strip()
        for key in (
            "User time (seconds)",
            "System time (seconds)",
            "Maximum resident set size (kbytes)",
        ):
            prefix = f"{key}:"
            if stripped.startswith(prefix):
                values[key] = stripped.removeprefix(prefix).strip()
    required = {
        "User time (seconds)",
        "System time (seconds)",
        "Maximum resident set size (kbytes)",
    }
    if values.keys() < required:
        raise ValueError("GNU time -v metrics are missing from stderr")
    cpu_seconds = float(values["User time (seconds)"]) + float(values["System time (seconds)"])
    peak_rss_bytes = int(values["Maximum resident set size (kbytes)"]) * 1024
    return cpu_seconds, peak_rss_bytes


def run_measured_wsl(command: list[str], cwd: Path, log_dir: Path, timeout: float | None = None) -> ProcessResult:
    if not command or Path(command[0]).name.lower() != "wsl.exe":
        raise ValueError("WSL measurement requires a wsl.exe command")
    timed_command = [command[0], "/usr/bin/time", "-v", *command[1:]]
    measured = run_measured(timed_command, cwd, log_dir, timeout)
    cpu_seconds, peak_rss_bytes = _gnu_time_metrics(measured.stderr_path.read_text(encoding="utf-8", errors="replace"))
    return ProcessResult(
        command=timed_command,
        returncode=measured.returncode,
        wall_seconds=measured.wall_seconds,
        cpu_seconds=cpu_seconds,
        peak_rss_bytes=peak_rss_bytes,
        stdout_path=measured.stdout_path,
        stderr_path=measured.stderr_path,
        resource_source="gnu_time_v_inside_wsl",
    )
