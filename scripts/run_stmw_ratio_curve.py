from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont

from fa_qem_bench.adapters.base import AdapterContext, adapter_for
from fa_qem_bench.evaluate import evaluate_paths
from fa_qem_bench.mesh import load_mesh, mesh_topology
from fa_qem_bench.texture import bake_pbr_asset
from fa_qem_bench.util import atomic_json, sha256_file

RATIOS = tuple(round(step / 10, 1) for step in range(1, 10))
REUSED_RATIOS = {0.1, 0.5}
SOURCE_FACE_COUNT = 164_940


@dataclass(frozen=True)
class CurvePaths:
    root: Path
    records: Path
    summary_json: Path
    summary_csv: Path
    summary_markdown: Path
    chart: Path


def ratio_text(ratio: float) -> str:
    return f"{ratio:.1f}"


def ratio_token(ratio: float) -> str:
    return ratio_text(ratio).replace(".", "p")


def target_faces(ratio: float) -> int:
    return round(SOURCE_FACE_COUNT * ratio)


def nested_metric(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record
    for key in keys:
        value = value[key]
    return value


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def record_path(paths: CurvePaths, ratio: float) -> Path:
    return paths.records / f"ratio-{ratio_token(ratio)}" / "run.json"


def reusable_record(root: Path, ratio: float) -> dict[str, Any]:
    token = ratio_token(ratio)
    research_path = root / "artifacts" / "runs" / f"stmw-{token}-research" / "run.json"
    asset_path = root / "artifacts" / "runs" / f"stmw-{token}-asset" / "run.json"
    research = load_json(research_path)
    asset = load_json(asset_path)
    research_output = root / str(research["output_path"])
    asset_output = root / str(asset["output_path"])
    if research["status"] != "SUCCESS" or asset["status"] != "SUCCESS":
        raise RuntimeError(f"existing STMW ratio {ratio_text(ratio)} is not successful")
    if sha256_file(research_output) != research["output_sha256"]:
        raise RuntimeError(f"existing STMW ratio {ratio_text(ratio)} research hash mismatch")
    if sha256_file(asset_output) != asset["output_sha256"]:
        raise RuntimeError(f"existing STMW ratio {ratio_text(ratio)} asset hash mismatch")
    geometry = nested_metric(research, "metrics", "geometry", "normalized_unit_diagonal")
    texture = nested_metric(asset, "metrics", "texture")
    return {
        "schema_version": 1,
        "method": "stmw",
        "ratio": ratio_text(ratio),
        "target_faces": target_faces(ratio),
        "actual_faces": int(research["actual_faces"]),
        "actual_ratio": int(research["actual_faces"]) / SOURCE_FACE_COUNT,
        "status": "SUCCESS",
        "source": "reused_full_benchmark_run",
        "research_run_json": str(research_path.relative_to(root)),
        "asset_run_json": str(asset_path.relative_to(root)),
        "research_output": str(research_output.relative_to(root)),
        "research_output_sha256": research["output_sha256"],
        "asset_output": str(asset_output.relative_to(root)),
        "asset_output_sha256": asset["output_sha256"],
        "successive_mapping": research["parameters"]["successive_mapping_path"],
        "successive_mapping_sha256": research["parameters"]["successive_mapping_sha256"],
        "timing": research["timing"],
        "metrics": {
            "hausdorff_symmetric_sampled_normalized": geometry["hausdorff_symmetric_sampled"],
            "chamfer_mean_squared_symmetric_normalized": geometry["chamfer_mean_squared_symmetric"],
            "symmetric_mean_rgb_l2": texture["symmetric_mean_rgb_l2"],
            "geometry_samples_per_direction": geometry["samples_per_direction"],
            "texture_samples_per_direction": texture["samples_per_direction"],
        },
    }


def run_ratio(
    root: Path,
    paths: CurvePaths,
    ratio: float,
    config: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    destination = record_path(paths, ratio).parent
    destination.mkdir(parents=True, exist_ok=True)
    research_dir = destination / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    prepared = root / "artifacts" / "prepared" / "geometry_unit.obj"
    adapter = adapter_for("stmw")
    available, detail = adapter.available(root)
    if not available:
        raise RuntimeError(f"STMW executable unavailable: {detail}")
    result = adapter.run(
        AdapterContext(
            root=root,
            prepared_mesh=prepared,
            run_dir=research_dir,
            target_faces=target_faces(ratio),
            threads=int(config["threads"]),
            parameters={
                "warmup_runs": int(config["timing"]["warmup_runs"]),
                "timed_repetitions": int(config["timing"]["repeats_under_seconds"]),
            },
        )
    )
    native = result.output
    successive_map = research_dir / "successive-map.bin"
    native_mesh = load_mesh(native, process=False)
    actual_faces = len(native_mesh.faces)
    research_metrics = evaluate_paths(
        prepared,
        native,
        count=int(config["evaluation"]["geometry_samples"]),
        seed=int(config["random_seed"]),
        original_diagonal=float(manifest["transform"]["diagonal"]),
        input_is_normalized=True,
    )
    topology = mesh_topology(native_mesh)
    if any(
        (
            topology["boundary_edges"],
            topology["nonmanifold_edges"],
            topology["degenerate_faces"],
        )
    ):
        raise RuntimeError(f"STMW ratio {ratio_text(ratio)} failed topology gate: {topology}")

    asset = destination / "asset-pbr.glb"
    rebake = bake_pbr_asset(
        source_glb=root / str(config["source"]["path"]),
        target_path=native,
        output_path=asset,
        center=manifest["transform"]["center"],
        diagonal=float(manifest["transform"]["diagonal"]),
        resolution=2048,
        successive_map_path=successive_map,
    )
    asset_metrics = evaluate_paths(
        root / str(config["source"]["path"]),
        asset,
        count=int(config["evaluation"]["geometry_samples"]),
        seed=int(config["random_seed"]),
        original_diagonal=float(manifest["transform"]["diagonal"]),
        input_is_normalized=False,
        texture_count=int(config["evaluation"]["texture_samples"]),
    )
    geometry = nested_metric(research_metrics, "geometry", "normalized_unit_diagonal")
    texture = nested_metric(asset_metrics, "texture")
    record = {
        "schema_version": 1,
        "method": "stmw",
        "ratio": ratio_text(ratio),
        "target_faces": target_faces(ratio),
        "actual_faces": actual_faces,
        "actual_ratio": actual_faces / SOURCE_FACE_COUNT,
        "status": "SUCCESS",
        "source": result.source,
        "command": result.command,
        "parameters": result.parameters,
        "research_output": str(native.relative_to(root)),
        "research_output_sha256": sha256_file(native),
        "asset_output": str(asset.relative_to(root)),
        "asset_output_sha256": sha256_file(asset),
        "successive_mapping": str(successive_map.relative_to(root)),
        "successive_mapping_sha256": sha256_file(successive_map),
        "timing": result.timing,
        "topology": topology,
        "rebake": rebake,
        "metrics": {
            "hausdorff_symmetric_sampled_normalized": geometry["hausdorff_symmetric_sampled"],
            "chamfer_mean_squared_symmetric_normalized": geometry["chamfer_mean_squared_symmetric"],
            "symmetric_mean_rgb_l2": texture["symmetric_mean_rgb_l2"],
            "geometry_samples_per_direction": geometry["samples_per_direction"],
            "texture_samples_per_direction": texture["samples_per_direction"],
        },
    }
    atomic_json(record_path(paths, ratio), record)
    return record


def validate_cached_record(root: Path, record: dict[str, Any]) -> bool:
    if record.get("status") != "SUCCESS":
        return False
    for path_key, hash_key in (
        ("research_output", "research_output_sha256"),
        ("asset_output", "asset_output_sha256"),
        ("successive_mapping", "successive_mapping_sha256"),
    ):
        path = root / str(record.get(path_key, ""))
        if not path.is_file() or sha256_file(path) != record.get(hash_key):
            return False
    return True


def load_or_run(
    root: Path,
    paths: CurvePaths,
    ratio: float,
    config: dict[str, Any],
    manifest: dict[str, Any],
    force: bool,
) -> dict[str, Any]:
    path = record_path(paths, ratio)
    if not force and path.is_file():
        cached = load_json(path)
        if validate_cached_record(root, cached):
            return cached
    if ratio in REUSED_RATIOS and not force:
        record = reusable_record(root, ratio)
        atomic_json(path, record)
        return record
    if force and path.parent.exists():
        shutil.rmtree(path.parent)
    return run_ratio(root, paths, ratio, config, manifest)


def metric_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ratio": float(record["ratio"]),
            "target_faces": record["target_faces"],
            "actual_faces": record["actual_faces"],
            "actual_ratio": record["actual_ratio"],
            "hausdorff_normalized": record["metrics"]["hausdorff_symmetric_sampled_normalized"],
            "chamfer_mse_normalized": record["metrics"]["chamfer_mean_squared_symmetric_normalized"],
            "texture_rgb_l2": record["metrics"]["symmetric_mean_rgb_l2"],
            "algorithm_wall_seconds": record["timing"]["algorithm_wall_seconds"],
            "source": record["source"],
        }
        for record in sorted(records, key=lambda item: float(item["ratio"]))
    ]


def write_tables(paths: CurvePaths, rows: list[dict[str, Any]]) -> None:
    paths.summary_json.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(paths.summary_json, {"schema_version": 1, "method": "stmw", "rows": rows})
    paths.summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with paths.summary_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# STMW ratio sweep",
        "",
        "Source model: `Test_Model/curved-lantern-balustrade-final.glb` (164,940 faces).",
        "Each ratio is simplified independently from the same prepared source mesh.",
        "",
        "![STMW quality metrics across simplification ratios](assets/stmw-ratio-metrics.png)",
        "",
        "| Ratio | Target faces | Actual faces | Hausdorff (normalized) | "
        "Chamfer MSE (normalized) | RGB L2 | Wall time (s) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {ratio:.1f} | {target_faces:,} | {actual_faces:,} | {hausdorff_normalized:.6e} | "
            "{chamfer_mse_normalized:.6e} | {texture_rgb_l2:.6f} | {algorithm_wall_seconds:.3f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "All geometry values use 100,000 area samples per direction; RGB L2 uses 10,000 samples per direction.",
            "Lower is better for all three quality metrics.",
        ]
    )
    paths.summary_markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def format_tick(value: float) -> str:
    if value == 0:
        return "0"
    exponent = math.floor(math.log10(abs(value)))
    return f"1e{exponent}" if abs(value / (10**exponent) - 1) < 1e-8 else f"{value:.2g}"


def draw_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    rows: list[dict[str, Any]],
    metric: str,
    title: str,
    ylabel: str,
    log_y: bool,
    color: tuple[int, int, int],
) -> None:
    left, top, right, bottom = box
    plot_left, plot_top, plot_right, plot_bottom = left + 102, top + 64, right - 34, bottom - 92
    values = [float(row[metric]) for row in rows]
    transformed = [math.log10(value) if log_y else value for value in values]
    low, high = min(transformed), max(transformed)
    if log_y:
        padding = max((high - low) * 0.12, 0.08)
    else:
        padding = max((high - low) * 0.12, max(abs(low), abs(high)) * 0.005, 1e-8)
    low -= padding
    high += padding
    title_font = font(25, bold=True)
    label_font = font(18)
    tick_font = font(16)
    draw.text((left + 12, top + 12), title, fill=(28, 34, 43), font=title_font)
    draw.rectangle((plot_left, plot_top, plot_right, plot_bottom), outline=(142, 151, 164), width=2)
    for index in range(5):
        fraction = index / 4
        y = plot_bottom - fraction * (plot_bottom - plot_top)
        draw.line((plot_left, y, plot_right, y), fill=(220, 224, 230), width=1)
        raw = 10 ** (low + fraction * (high - low)) if log_y else low + fraction * (high - low)
        text = format_tick(raw)
        bbox = draw.textbbox((0, 0), text, font=tick_font)
        draw.text((plot_left - 10 - (bbox[2] - bbox[0]), y - 9), text, fill=(72, 82, 96), font=tick_font)
    points: list[tuple[float, float]] = []
    for index, row in enumerate(rows):
        x = plot_left + index * (plot_right - plot_left) / (len(rows) - 1)
        y_value = transformed[index]
        y = plot_bottom - (y_value - low) / (high - low) * (plot_bottom - plot_top)
        points.append((x, y))
        ratio = f"{row['ratio']:.1f}"
        bbox = draw.textbbox((0, 0), ratio, font=tick_font)
        draw.text((x - (bbox[2] - bbox[0]) / 2, plot_bottom + 12), ratio, fill=(72, 82, 96), font=tick_font)
    draw.line(points, fill=color, width=5, joint="curve")
    for x, y in points:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 255, 255), outline=color, width=4)
    x_title = "Retained face ratio"
    bbox = draw.textbbox((0, 0), x_title, font=label_font)
    draw.text(
        ((plot_left + plot_right - (bbox[2] - bbox[0])) / 2, plot_bottom + 48),
        x_title,
        fill=(28, 34, 43),
        font=label_font,
    )
    draw.text((left + 12, plot_top - 30), ylabel, fill=(72, 82, 96), font=label_font)


def draw_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    width, height = 2400, 760
    image = Image.new("RGB", (width, height), (250, 251, 253))
    draw = ImageDraw.Draw(image)
    header_font = font(34, bold=True)
    note_font = font(18)
    draw.text((42, 20), "STMW quality metrics across simplification ratios", fill=(22, 29, 39), font=header_font)
    draw.text((42, 66), "Same source model; independent runs; lower is better", fill=(80, 91, 106), font=note_font)
    gap = 28
    panel_top = 102
    panel_width = (width - 84 - gap * 2) // 3
    panels = [
        ("hausdorff_normalized", "Sampled Hausdorff", "Normalized distance (log)", True, (38, 108, 191)),
        ("chamfer_mse_normalized", "Symmetric Chamfer MSE", "Normalized squared distance (log)", True, (202, 83, 50)),
        ("texture_rgb_l2", "Texture color error", "Symmetric RGB L2", False, (35, 139, 109)),
    ]
    for index, panel in enumerate(panels):
        left = 42 + index * (panel_width + gap)
        draw_panel(
            draw,
            (left, panel_top, left + panel_width, height - 30),
            rows,
            *panel,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def parse_ratios(values: list[str] | None) -> list[float]:
    if not values:
        return list(RATIOS)
    parsed = sorted({float(value) for value in values})
    invalid = [value for value in parsed if value not in RATIOS]
    if invalid:
        raise ValueError(f"ratios must be selected from {RATIOS}: {invalid}")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and plot the STMW ratio sweep on the repository test model.")
    parser.add_argument("--ratios", nargs="*", help="Subset of ratios from 0.1 through 0.9.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute selected ratios instead of using valid records.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = CurvePaths(
        root=root / "artifacts" / "ratio-curves" / "stmw",
        records=root / "artifacts" / "ratio-curves" / "stmw" / "records",
        summary_json=root / "artifacts" / "ratio-curves" / "stmw" / "summary.json",
        summary_csv=root / "docs" / "data" / "stmw-ratio-metrics.csv",
        summary_markdown=root / "docs" / "stmw-ratio-metrics.md",
        chart=root / "docs" / "assets" / "stmw-ratio-metrics.png",
    )
    config = yaml.safe_load((root / "experiment.yaml").read_text(encoding="utf-8"))
    manifest = load_json(root / "artifacts" / "prepared" / "manifest.json")
    selected = parse_ratios(args.ratios)
    for ratio in selected:
        print(f"STMW ratio {ratio_text(ratio)}: start", flush=True)
        record = load_or_run(root, paths, ratio, config, manifest, force=args.force)
        print(
            f"STMW ratio {ratio_text(ratio)}: {record['status']}, "
            f"faces={record['actual_faces']}, H={record['metrics']['hausdorff_symmetric_sampled_normalized']:.6e}",
            flush=True,
        )
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for ratio in RATIOS:
        path = record_path(paths, ratio)
        if not path.is_file():
            missing.append(ratio_text(ratio))
            continue
        record = load_json(path)
        if not validate_cached_record(root, record):
            missing.append(ratio_text(ratio))
            continue
        records.append(record)
    if missing:
        print(f"Partial sweep complete; missing valid ratios: {', '.join(missing)}", flush=True)
        return 0
    rows = metric_rows(records)
    write_tables(paths, rows)
    draw_chart(paths.chart, rows)
    print(f"Summary: {paths.summary_json}", flush=True)
    print(f"Chart: {paths.chart}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
