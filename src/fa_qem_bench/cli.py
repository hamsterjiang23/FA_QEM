from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import SUPPORTED_METHODS, load_config
from .doctor import doctor
from .evaluate import evaluate_paths
from .mesh import prepare_source
from .repair import repair_run
from .report import build_report
from .runner import load_run_record, run_baseline
from .util import atomic_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fa-qem-bench")
    parser.add_argument("--config", default="experiment.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("prepare")
    run = subparsers.add_parser("run")
    run.add_argument("--method", required=True, choices=SUPPORTED_METHODS)
    run.add_argument("--ratio", required=True, choices=("0.5", "0.1", "0.01"))
    repair = subparsers.add_parser("repair")
    repair.add_argument("--run-id", required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--run-id", required=True)
    subparsers.add_parser("report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config_path = Path(args.config)
    config = load_config(config_path)
    if args.command == "doctor":
        print(json.dumps(doctor(config), indent=2))
        return 0
    if args.command == "prepare":
        manifest = prepare_source(
            config.source,
            config.artifacts / "prepared",
            int(config.data["source"]["expected_faces"]),
        )
        print(json.dumps(manifest, indent=2))
        return 0
    if args.command == "run":
        record = run_baseline(config, args.method, args.ratio)
        print(json.dumps(record.__dict__, indent=2, default=str))
        return 0 if record.status in {"SUCCESS", "TARGET_UNREACHABLE"} else 1
    if args.command == "repair":
        result = repair_run(config, args.run_id)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "SUCCESS" else 1
    if args.command == "evaluate":
        run_path = config.artifacts / "runs" / args.run_id / "run.json"
        record = load_run_record(run_path)
        if not record.get("output_path"):
            raise ValueError(f"run has no output: {args.run_id}")
        manifest = json.loads(
            (config.artifacts / "prepared" / "manifest.json").read_text(encoding="utf-8")
        )
        metrics = evaluate_paths(
            config.artifacts / "prepared" / "geometry_unit.obj",
            config.root / record["output_path"],
            int(config.data["evaluation"]["geometry_samples"]),
            config.seed,
            float(manifest["transform"]["diagonal"]),
        )
        record.setdefault("metrics", {}).update(metrics)
        atomic_json(run_path, record)
        print(json.dumps(metrics, indent=2))
        return 0
    if args.command == "report":
        print(build_report(config))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
