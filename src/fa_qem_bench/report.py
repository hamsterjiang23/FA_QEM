from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .config import ExperimentConfig
from .util import atomic_json


def collect_records(config: ExperimentConfig) -> list[dict[str, Any]]:
    records = []
    run_root = config.artifacts / "runs"
    if run_root.exists():
        for path in sorted(run_root.glob("*/run.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
    return records


def build_report(config: ExperimentConfig) -> Path:
    records = collect_records(config)
    report_dir = config.artifacts / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(report_dir / "summary.json", records)
    columns = [
        "run_id",
        "method",
        "track",
        "ratio",
        "target_faces",
        "actual_faces",
        "status",
        "output_sha256",
        "error",
    ]
    with (report_dir / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in columns})
    rows = "\n".join(
        "<tr>" + "".join(f"<td>{record.get(key, '')}</td>" for key in columns) + "</tr>"
        for record in records
    )
    html = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>FA-QEM Baselines</title>
<style>
body{{font-family:system-ui;margin:2rem}}
table{{border-collapse:collapse}}
td,th{{border:1px solid #aaa;padding:.4rem}}
</style>
</head><body><h1>FA-QEM six-baseline audit</h1><table><thead><tr>
{"".join(f"<th>{key}</th>" for key in columns)}</tr></thead><tbody>{rows}</tbody></table></body></html>"""
    (report_dir / "index.html").write_text(html, encoding="utf-8")
    return report_dir / "index.html"
