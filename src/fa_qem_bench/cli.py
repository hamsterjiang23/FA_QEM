from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import SUPPORTED_METHODS, load_config
from .doctor import doctor
from .evaluate import evaluate_run
from .mesh import prepare_source
from .repair import repair_run
from .report import build_report
from .resources import recover_wsl_resources
from .runner import run_baseline
from .sweep import run_sweep
from .texture import rebake_run


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
    rebake = subparsers.add_parser("rebake")
    rebake.add_argument("--run-id", required=True)
    rebake.add_argument("--resolution", type=int, default=2048)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--run-id", required=True)
    recover = subparsers.add_parser("recover-resources")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--monitor", required=True, type=Path)
    sweep = subparsers.add_parser("sweep")
    sweep.add_argument("--methods", nargs="+", choices=SUPPORTED_METHODS, default=list(SUPPORTED_METHODS))
    sweep.add_argument("--ratios", nargs="+", choices=("0.5", "0.1", "0.01"), default=["0.5", "0.1", "0.01"])
    sweep.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    sweep.add_argument("--resolution", type=int, default=2048)
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
    if args.command == "rebake":
        result = rebake_run(config, args.run_id, args.resolution)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "evaluate":
        metrics = evaluate_run(config, args.run_id)
        print(json.dumps(metrics, indent=2))
        return 0
    if args.command == "recover-resources":
        metrics = recover_wsl_resources(config, args.run_id, args.monitor)
        print(json.dumps(metrics, indent=2))
        return 0
    if args.command == "sweep":
        result = run_sweep(config, args.methods, args.ratios, resume=args.resume, resolution=args.resolution)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "report":
        print(build_report(config))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
