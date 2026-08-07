from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .util import atomic_json


class RunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    TARGET_UNREACHABLE = "TARGET_UNREACHABLE"
    ALGORITHM_FAILURE = "ALGORITHM_FAILURE"
    BUILD_FAILURE = "BUILD_FAILURE"
    REPAIR_FAILED = "REPAIR_FAILED"


@dataclass
class RunRecord:
    schema_version: int
    run_id: str
    method: str
    method_source: str
    track: str
    ratio: str
    target_faces: int
    status: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    actual_faces: int | None = None
    source_sha256: str | None = None
    input_sha256: str | None = None
    output_sha256: str | None = None
    command: list[str] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    output_path: str | None = None
    repair_lineage: dict[str, Any] | None = None
    error: str | None = None

    def write(self, path: Path) -> None:
        atomic_json(path, asdict(self))
