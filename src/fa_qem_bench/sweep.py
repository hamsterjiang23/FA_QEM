from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import ExperimentConfig
from .evaluate import evaluate_run
from .repair import repair_run
from .report import build_report
from .runner import load_run_record, run_baseline, run_id
from .texture import rebake_run
from .util import atomic_json, sha256_file


def _record_is_valid(config: ExperimentConfig, identifier: str) -> bool:
    path = config.artifacts / "runs" / identifier / "run.json"
    if not path.is_file():
        return False
    record = load_run_record(path)
    if record.get("source_sha256") != sha256_file(config.source):
        return False
    output_relative = record.get("output_path")
    if output_relative:
        output = config.root / str(output_relative)
        return output.is_file() and sha256_file(output) == record.get("output_sha256")
    return record.get("status") in {"BUILD_FAILURE", "ALGORITHM_FAILURE", "REPAIR_FAILED"}


def _has_evaluation(record: dict[str, Any]) -> bool:
    metrics = record.get("metrics", {})
    return all(key in metrics for key in ("geometry", "triangle_quality", "external_inspection"))


def run_sweep(
    config: ExperimentConfig,
    methods: Iterable[str],
    ratios: Iterable[str],
    *,
    resume: bool = True,
    resolution: int = 2048,
) -> dict[str, Any]:
    progress_path = config.artifacts / "sweep-progress.json"
    events: list[dict[str, Any]] = []

    def note(method: str, ratio: str, stage: str, status: str, detail: str = "") -> None:
        events.append({"method": method, "ratio": ratio, "stage": stage, "status": status, "detail": detail})
        atomic_json(progress_path, {"events": events})

    for ratio in ratios:
        for method in methods:
            research_id = run_id(method, ratio)
            if resume and _record_is_valid(config, research_id):
                note(method, ratio, "research", "resumed")
            else:
                record = run_baseline(config, method, ratio)
                note(method, ratio, "research", str(record.status))
            research_path = config.artifacts / "runs" / research_id / "run.json"
            research = load_run_record(research_path)
            if research.get("output_path") and (not resume or not _has_evaluation(research)):
                evaluate_run(config, research_id)
                note(method, ratio, "research-evaluation", "complete")

            asset_id = run_id(method, ratio, "asset")
            asset_current = _record_is_valid(config, asset_id)
            if asset_current:
                asset = load_run_record(config.artifacts / "runs" / asset_id / "run.json")
                asset_current = asset.get("input_sha256") == research.get("output_sha256")
            if resume and asset_current:
                note(method, ratio, "asset", "resumed")
            else:
                repaired = repair_run(config, research_id)
                note(method, ratio, "asset", str(repaired["status"]), str(repaired["action"]))
            asset_path = config.artifacts / "runs" / asset_id / "run.json"
            asset = load_run_record(asset_path)
            if asset.get("status") == "SUCCESS" and asset.get("output_path"):
                rebake = asset.get("metrics", {}).get("rebake", {})
                did_rebake = False
                if (
                    not resume
                    or rebake.get("resolution") != resolution
                    or Path(str(asset.get("output_path"))).name != "asset-pbr.glb"
                ):
                    rebake_run(config, asset_id, resolution)
                    did_rebake = True
                    note(method, ratio, "rebake", "complete", f"resolution={resolution}")
                    asset = load_run_record(asset_path)
                if did_rebake or not resume or not _has_evaluation(asset):
                    evaluate_run(config, asset_id)
                    note(method, ratio, "asset-evaluation", "complete")
    report = build_report(config)
    result = {"events": events, "report": str(report)}
    atomic_json(progress_path, result)
    return result
