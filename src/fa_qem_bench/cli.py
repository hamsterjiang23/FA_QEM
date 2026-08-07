from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_experiment
from .config import RUNNABLE_METHODS, SUPPORTED_METHODS, load_config
from .doctor import doctor
from .evaluate import evaluate_run
from .mesh import prepare_source
from .repair import repair_run
from .report import build_report
from .resources import recover_wsl_resources
from .runner import run_baseline
from .sweep import run_sweep
from .texture import rebake_run
from .thingi10k import fetch_thingi10k_subset, run_thingi10k_subset, write_thingi10k_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fa-qem-bench")
    parser.add_argument("--config", default="experiment.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("prepare")
    run = subparsers.add_parser("run")
    run.add_argument("--method", required=True, choices=RUNNABLE_METHODS)
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
    recover.add_argument("--repository-commit")
    recover.add_argument("--repository-dirty", action=argparse.BooleanOptionalAction, default=None)
    recover.add_argument("--provenance-note")
    sweep = subparsers.add_parser("sweep")
    sweep.add_argument("--methods", nargs="+", choices=SUPPORTED_METHODS, default=list(SUPPORTED_METHODS))
    sweep.add_argument("--ratios", nargs="+", choices=("0.5", "0.1", "0.01"), default=["0.5", "0.1", "0.01"])
    sweep.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    sweep.add_argument("--resolution", type=int, default=2048)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--allow-incomplete", action="store_true")
    subparsers.add_parser("report")
    thingi_select = subparsers.add_parser("thingi10k-select")
    thingi_select.add_argument("--metadata-dir", type=Path, required=True)
    thingi_select.add_argument("--dataset-root", type=Path, required=True)
    thingi_select.add_argument("--output", type=Path, required=True)
    thingi_select.add_argument("--per-split-per-stratum", type=int, default=2)
    thingi_fetch = subparsers.add_parser("thingi10k-fetch")
    thingi_fetch.add_argument("--manifest", type=Path, required=True)
    thingi_run = subparsers.add_parser("thingi10k-run")
    thingi_run.add_argument("--manifest", type=Path, required=True)
    thingi_run.add_argument("--split", choices=("validation", "holdout"), required=True)
    thingi_run.add_argument("--ratios", nargs="+", type=float, choices=(0.1, 0.01), default=[0.1, 0.01])
    thingi_run.add_argument("--samples", type=int, default=100_000)
    thingi_run.add_argument(
        "--variant",
        choices=("published", "paper-topology", "adaptive-topology", "final-topology"),
        default="published",
    )
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
        metrics = recover_wsl_resources(
            config,
            args.run_id,
            args.monitor,
            repository_commit=args.repository_commit,
            repository_dirty=args.repository_dirty,
            provenance_note=args.provenance_note,
        )
        print(json.dumps(metrics, indent=2))
        return 0
    if args.command == "sweep":
        result = run_sweep(config, args.methods, args.ratios, resume=args.resume, resolution=args.resolution)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "audit":
        result = audit_experiment(config)
        print(json.dumps(result, indent=2))
        complete_enough = not result["errors"] and (args.allow_incomplete or not result["missing"])
        return 0 if complete_enough else 1
    if args.command == "report":
        print(build_report(config))
        return 0
    if args.command == "thingi10k-select":
        manifest = write_thingi10k_manifest(
            args.metadata_dir,
            args.dataset_root,
            args.output,
            seed=config.seed,
            per_split_per_stratum=args.per_split_per_stratum,
        )
        print(json.dumps(manifest, indent=2))
        return 0
    if args.command == "thingi10k-run":
        result = run_thingi10k_subset(
            config.root,
            args.manifest,
            split=args.split,
            ratios=tuple(args.ratios),
            samples=args.samples,
            seed=config.seed,
            variant=args.variant,
        )
        print(json.dumps(result["summary"], indent=2))
        return 0
    if args.command == "thingi10k-fetch":
        print(json.dumps(fetch_thingi10k_subset(args.manifest), indent=2))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
