from __future__ import annotations

from typing import Any

from .config import SUPPORTED_METHODS, ExperimentConfig
from .runner import load_run_record, run_id
from .util import sha256_file

TERMINAL_STATUSES = {
    "SUCCESS",
    "TARGET_UNREACHABLE",
    "ALGORITHM_FAILURE",
    "BUILD_FAILURE",
    "REPAIR_FAILED",
}


def audit_experiment(config: ExperimentConfig) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    records = 0
    outputs = 0
    source_hash = sha256_file(config.source)
    ratios = tuple(str(key) for key in config.data["targets"])
    for ratio in ratios:
        for method in SUPPORTED_METHODS:
            research_identifier = run_id(method, ratio)
            research_path = config.artifacts / "runs" / research_identifier / "run.json"
            if not research_path.is_file():
                missing.append(research_identifier)
                research = None
            else:
                research = load_run_record(research_path)
                records += 1
                _audit_record(config, research_identifier, research, source_hash, errors, warnings)
                _audit_research(config, research_identifier, research, errors)
                outputs += int(bool(research.get("output_path")))

            asset_identifier = run_id(method, ratio, "asset")
            asset_path = config.artifacts / "runs" / asset_identifier / "run.json"
            if not asset_path.is_file():
                missing.append(asset_identifier)
                continue
            asset = load_run_record(asset_path)
            records += 1
            _audit_record(config, asset_identifier, asset, source_hash, errors, warnings)
            _audit_asset(asset_identifier, asset, research, errors)
            outputs += int(bool(asset.get("output_path")))
    return {
        "ok": not errors and not missing,
        "expected_records": len(SUPPORTED_METHODS) * len(ratios) * 2,
        "records": records,
        "outputs": outputs,
        "missing": missing,
        "errors": errors,
        "warnings": warnings,
    }


def _audit_record(
    config: ExperimentConfig,
    identifier: str,
    record: dict[str, Any],
    source_hash: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if record.get("run_id") != identifier:
        errors.append(f"{identifier}: run_id mismatch")
    if record.get("status") not in TERMINAL_STATUSES:
        errors.append(f"{identifier}: invalid status {record.get('status')}")
    if record.get("source_sha256") != source_hash:
        errors.append(f"{identifier}: source hash mismatch")
    expected_target = config.target(str(record.get("ratio")))
    if record.get("target_faces") != expected_target:
        errors.append(f"{identifier}: target mismatch")
    output_relative = record.get("output_path")
    if output_relative:
        output = config.root / str(output_relative)
        if not output.is_file():
            errors.append(f"{identifier}: output is missing")
        elif sha256_file(output) != record.get("output_sha256"):
            errors.append(f"{identifier}: output hash mismatch")
        if (
            record.get("metrics", {}).get("external_inspection", {}).get("self_intersections", {}).get("status")
            == "not_evaluated"
        ):
            warnings.append(f"{identifier}: self-intersection not evaluated")


def _audit_research(
    config: ExperimentConfig,
    identifier: str,
    record: dict[str, Any],
    errors: list[str],
) -> None:
    if record.get("track") != "research":
        errors.append(f"{identifier}: expected research track")
    output = record.get("output_path")
    if not output:
        if record.get("status") in {"SUCCESS", "TARGET_UNREACHABLE"}:
            errors.append(f"{identifier}: successful research run has no output")
        return
    metrics = record.get("metrics", {})
    for key in ("geometry", "triangle_quality", "external_inspection"):
        if key not in metrics:
            errors.append(f"{identifier}: missing {key} metrics")
    if metrics.get("texture", {}).get("status") != "N/A":
        errors.append(f"{identifier}: research texture status is not N/A")
    actual = record.get("actual_faces")
    if actual is not None:
        relative_error = abs(int(actual) - int(record["target_faces"])) / int(record["target_faces"])
        expected_status = "SUCCESS" if relative_error <= config.tolerance else "TARGET_UNREACHABLE"
        if record.get("status") != expected_status:
            errors.append(f"{identifier}: target status is inconsistent with actual faces")
    timing = record.get("timing", {})
    if (
        record.get("method") != "cwf"
        and record.get("status") in {"SUCCESS", "TARGET_UNREACHABLE"}
        and (timing.get("warmup_runs") != 1 or timing.get("repetitions") != 3)
    ):
        errors.append(f"{identifier}: expected one warmup and three timed repetitions")


def _audit_asset(
    identifier: str,
    record: dict[str, Any],
    research: dict[str, Any] | None,
    errors: list[str],
) -> None:
    if record.get("track") != "asset":
        errors.append(f"{identifier}: expected asset track")
    if research is not None and record.get("input_sha256") != research.get("output_sha256"):
        errors.append(f"{identifier}: asset input does not match research output")
    if record.get("status") != "SUCCESS":
        if not record.get("error"):
            errors.append(f"{identifier}: failed asset has no explanation")
        return
    if not record.get("output_path"):
        errors.append(f"{identifier}: successful asset has no output")
        return
    metrics = record.get("metrics", {})
    if metrics.get("rebake", {}).get("resolution") != 2048:
        errors.append(f"{identifier}: successful asset is not rebaked at 2048")
    if metrics.get("texture", {}).get("status") != "evaluated":
        errors.append(f"{identifier}: successful asset lacks texture evaluation")
    if metrics.get("external_inspection", {}).get("hard_constraints", {}).get("passed") is not True:
        errors.append(f"{identifier}: successful asset did not pass external hard constraints")
    lineage = record.get("repair_lineage", {})
    if lineage.get("action") not in {"repair", "not_required"}:
        errors.append(f"{identifier}: successful asset lacks repair lineage")
