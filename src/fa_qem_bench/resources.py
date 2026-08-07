from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import ExperimentConfig
from .runner import load_run_record
from .util import atomic_json


def _parse_cpu_time(value: str) -> float:
    day_parts = value.split("-", 1)
    if len(day_parts) == 2:
        days = int(day_parts[0])
        clock = day_parts[1]
    else:
        days = 0
        clock = day_parts[0]
    parts = [float(part) for part in clock.split(":")]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = 0.0
        minutes, seconds = parts
    else:
        raise ValueError(f"unsupported process CPU time: {value}")
    return days * 86400.0 + hours * 3600.0 + minutes * 60.0 + seconds


def read_wsl_monitor(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"resource monitor has no samples: {path}")
    elapsed = [int(row["elapsed_seconds"]) for row in rows]
    rss = [int(row["rss_kib"]) * 1024 for row in rows]
    cpu = [_parse_cpu_time(row["cpu_time"]) for row in rows]
    timestamps = [row["timestamp_utc"] for row in rows]
    intervals = [later - earlier for earlier, later in zip(elapsed, elapsed[1:], strict=False)]
    interval = min(intervals) if intervals else None
    return {
        "algorithm_wall_seconds": float(max(elapsed)),
        "algorithm_wall_seconds_range": [float(max(elapsed)), float(max(elapsed))],
        "algorithm_wall_seconds_samples": [float(max(elapsed))],
        "cpu_seconds": float(max(cpu)),
        "cpu_seconds_range": [float(max(cpu)), float(max(cpu))],
        "cpu_seconds_samples": [float(max(cpu))],
        "peak_rss_bytes": max(rss),
        "peak_rss_bytes_samples": [max(rss)],
        "resource_measurement": "wsl_proc_sampled",
        "resource_monitor_path": str(path),
        "resource_monitor_samples": len(rows),
        "resource_monitor_first_timestamp_utc": timestamps[0],
        "resource_monitor_last_timestamp_utc": timestamps[-1],
        "resource_monitor_started_elapsed_seconds": min(elapsed),
        "resource_monitor_interval_seconds": interval,
        "peak_rss_is_lower_bound": bool(min(elapsed) > (interval or 0) * 2),
        "warmup_runs": 0,
        "warmup_wall_seconds": [],
        "repetitions": 1,
    }


def recover_wsl_resources(
    config: ExperimentConfig,
    run_id: str,
    monitor_path: Path,
    *,
    repository_commit: str | None = None,
    repository_dirty: bool | None = None,
    provenance_note: str | None = None,
) -> dict[str, Any]:
    record_path = config.artifacts / "runs" / run_id / "run.json"
    record = load_run_record(record_path)
    timing = read_wsl_monitor(monitor_path)
    timing["resource_monitor_path"] = str(monitor_path.resolve().relative_to(config.root))
    record["timing"] = timing
    repository = record.setdefault("environment", {}).setdefault("repository", {})
    if repository_commit is not None:
        repository["commit"] = repository_commit
    if repository_dirty is not None:
        repository["dirty"] = repository_dirty
    if provenance_note is not None:
        repository["recovery_note"] = provenance_note
    atomic_json(record_path, record)
    return timing
