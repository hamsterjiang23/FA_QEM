from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .config import ExperimentConfig
from .process import run_measured
from .records import RunRecord, RunStatus
from .runner import load_run_record
from .util import environment_snapshot, sha256_file


def _native_hard_failure(record: dict[str, Any]) -> bool:
    topology = record.get("metrics", {}).get("native_topology", {})
    internal_failure = bool(
        topology.get("boundary_edges", 0)
        or topology.get("nonmanifold_edges", 0)
        or topology.get("degenerate_faces", 0)
        or not topology.get("finite_vertices", False)
        or not topology.get("winding_consistent", False)
    )
    external_constraints = record.get("metrics", {}).get("external_inspection", {}).get("hard_constraints", {})
    external_failure = external_constraints.get("passed") is False
    return internal_failure or external_failure


def _asset_run_id(research_run_id: str) -> str:
    if not research_run_id.endswith("-research"):
        raise ValueError("repair expects a research-track run id")
    return f"{research_run_id.removesuffix('-research')}-asset"


def repair_run(config: ExperimentConfig, research_run_id: str) -> dict[str, Any]:
    research_path = config.artifacts / "runs" / research_run_id / "run.json"
    research = load_run_record(research_path)
    asset_id = _asset_run_id(research_run_id)
    asset_dir = config.artifacts / "runs" / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    record = RunRecord(
        schema_version=1,
        run_id=asset_id,
        method=str(research["method"]),
        method_source=str(research["method_source"]),
        track="asset",
        ratio=str(research["ratio"]),
        target_faces=int(research["target_faces"]),
        actual_faces=research.get("actual_faces"),
        status=RunStatus.BUILD_FAILURE,
        source_sha256=research.get("source_sha256"),
        input_sha256=research.get("output_sha256"),
        environment=environment_snapshot(config.root),
        metrics={"native_topology": research.get("metrics", {}).get("native_topology", {})},
        parameters={"research_run_id": research_run_id},
    )
    record_path = asset_dir / "run.json"

    if not research.get("output_path"):
        research_status = str(research.get("status", RunStatus.ALGORITHM_FAILURE))
        record.status = (
            research_status
            if research_status in {RunStatus.BUILD_FAILURE, RunStatus.ALGORITHM_FAILURE}
            else RunStatus.ALGORITHM_FAILURE
        )
        record.error = f"research output unavailable: {research_status}"
        record.repair_lineage = {"action": "not_possible", "research_run_id": research_run_id}
        record.write(record_path)
        return {"run_id": asset_id, "action": "not_possible", "status": record.status}

    native = config.root / research["output_path"]
    frozen_hash = sha256_file(native)
    if frozen_hash != research.get("output_sha256"):
        raise ValueError("native output changed after the research record was written")
    record.input_sha256 = frozen_hash

    if not _native_hard_failure(research):
        output = asset_dir / "geometry.obj"
        shutil.copy2(native, output)
        record.status = RunStatus.SUCCESS
        record.output_path = str(output.relative_to(config.root))
        record.output_sha256 = sha256_file(output)
        record.repair_lineage = {
            "action": "not_required",
            "research_run_id": research_run_id,
            "frozen_native_sha256": frozen_hash,
        }
        record.write(record_path)
        return {"run_id": asset_id, "action": "not_required", "status": record.status}

    tool_root = Path(str(config.data["repair"]["tool_root"]))
    executable = tool_root / ".venv" / "Scripts" / "asset-tools-v2.exe"
    if not executable.is_file():
        record.status = RunStatus.BUILD_FAILURE
        record.error = f"repair executable is unavailable: {executable}"
        record.write(record_path)
        return {"run_id": asset_id, "action": "repair_unavailable", "status": record.status}

    repair_dir = asset_dir / "repair"
    command = [
        str(executable),
        "mesh-repair",
        "repair",
        str(native),
        "--output",
        str(repair_dir),
        "--backend",
        "auto",
        "--preset",
        "high_fidelity",
        "--surface-mode",
        "solid",
        "--timeout-seconds",
        "900",
        "--workspace",
        str(config.root),
        "--json",
    ]
    measured = run_measured(command, config.root, asset_dir / "logs", timeout=1200)
    tool_record_path = repair_dir / "result.json"
    if not tool_record_path.is_file():
        record.status = RunStatus.REPAIR_FAILED
        record.command = command
        record.timing = {"repair_wall_seconds": measured.wall_seconds}
        record.error = f"repair tool exited {measured.returncode} without result.json"
        record.write(record_path)
        return {"run_id": asset_id, "action": "repair_failed", "status": record.status}

    tool_record = json.loads(tool_record_path.read_text(encoding="utf-8"))
    metrics = tool_record.get("metrics", tool_record)
    selected = metrics.get("selected_path")
    debug_name = metrics.get("debug_candidate")
    debug_path = None
    if debug_name:
        debug_path = repair_dir / "candidates" / str(debug_name) / "candidate.glb"
    record.command = command
    record.timing = {"repair_wall_seconds": measured.wall_seconds}
    record.repair_lineage = {
        "action": "repair",
        "research_run_id": research_run_id,
        "frozen_native_sha256": frozen_hash,
        "tool_result": str(tool_record_path.relative_to(config.root)),
        "tool_status": tool_record.get("status"),
        "selected_candidate": metrics.get("selected_candidate"),
        "selected_sha256": metrics.get("selected_sha256"),
        "debug_candidate": debug_name,
        "debug_path": (str(debug_path.relative_to(config.root)) if debug_path and debug_path.is_file() else None),
        "failed_constraints": metrics.get("failed_constraints", []),
    }
    if selected:
        selected_path = Path(str(selected))
        output = asset_dir / "geometry.glb"
        shutil.copy2(selected_path, output)
        record.status = RunStatus.SUCCESS
        record.output_path = str(output.relative_to(config.root))
        record.output_sha256 = sha256_file(output)
    else:
        record.status = RunStatus.REPAIR_FAILED
        record.error = "no repair candidate passed every hard constraint"
    record.write(record_path)
    return {
        "run_id": asset_id,
        "action": "repaired" if selected else "repair_failed",
        "status": record.status,
        "repair_lineage": record.repair_lineage,
    }
