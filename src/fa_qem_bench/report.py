from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any

from .config import ExperimentConfig
from .render import render_contact_sheet
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
    manifest = json.loads((config.artifacts / "prepared" / "manifest.json").read_text(encoding="utf-8"))
    for record in records:
        output = record.get("output_path")
        if not output:
            record["contact_sheet"] = ""
            continue
        render_path = report_dir / "renders" / f"{record['run_id']}.png"
        try:
            if not render_path.is_file():
                render_contact_sheet(
                    config.root / output,
                    render_path,
                    manifest["transform"]["center"],
                    float(manifest["transform"]["diagonal"]),
                    coordinates_are_normalized=record.get("track") == "research",
                    label=str(record["run_id"]),
                    resolution=384,
                )
            record["contact_sheet"] = str(render_path.relative_to(report_dir)).replace("\\", "/")
        except Exception as error:
            record["contact_sheet"] = ""
            record["render_error"] = f"{type(error).__name__}: {error}"
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
        "wall_seconds",
        "hausdorff_normalized",
        "chamfer_mse_normalized",
        "texture_rgb_l2",
        "contact_sheet",
    ]
    with (report_dir / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            geometry = record.get("metrics", {}).get("geometry", {}).get("normalized_unit_diagonal", {})
            texture = record.get("metrics", {}).get("texture", {})
            row = {key: record.get(key) for key in columns}
            row.update(
                {
                    "wall_seconds": record.get("timing", {}).get("algorithm_wall_seconds"),
                    "hausdorff_normalized": geometry.get("hausdorff_symmetric_sampled"),
                    "chamfer_mse_normalized": geometry.get("chamfer_mean_squared_symmetric"),
                    "texture_rgb_l2": texture.get("symmetric_mean_rgb_l2"),
                }
            )
            writer.writerow(row)
    rows_list = []
    for record in records:
        geometry = record.get("metrics", {}).get("geometry", {}).get("normalized_unit_diagonal", {})
        texture = record.get("metrics", {}).get("texture", {})
        row = {key: record.get(key, "") for key in columns}
        row["wall_seconds"] = record.get("timing", {}).get("algorithm_wall_seconds", "")
        row["hausdorff_normalized"] = geometry.get("hausdorff_symmetric_sampled", "")
        row["chamfer_mse_normalized"] = geometry.get("chamfer_mean_squared_symmetric", "")
        row["texture_rgb_l2"] = texture.get("symmetric_mean_rgb_l2", "")
        cells = []
        for key in columns:
            value = row[key]
            if key == "contact_sheet" and value:
                escaped = html.escape(str(value))
                cells.append(f'<td><a href="{escaped}"><img src="{escaped}" width="240"></a></td>')
            else:
                cells.append(f"<td>{html.escape(str(value))}</td>")
        rows_list.append("<tr>" + "".join(cells) + "</tr>")
    rows = "\n".join(rows_list)
    html_text = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>FA-QEM Baselines</title>
<style>
body{{font-family:system-ui;margin:2rem}}
table{{border-collapse:collapse;font-size:12px}}
td,th{{border:1px solid #aaa;padding:.4rem}}
th{{position:sticky;top:0;background:white}}
</style>
</head><body><h1>FA-QEM six-baseline audit</h1><table><thead><tr>
{"".join(f"<th>{key}</th>" for key in columns)}</tr></thead><tbody>{rows}</tbody></table></body></html>"""
    (report_dir / "index.html").write_text(html_text, encoding="utf-8")
    return report_dir / "index.html"
