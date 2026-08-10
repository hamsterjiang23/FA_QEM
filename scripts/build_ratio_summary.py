from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "report"
RATIO_CONFIG = {
    "0.5": {"target_faces": 82_470, "slug": "0p5", "percent": "50%"},
    "0.1": {"target_faces": 16_494, "slug": "0p1", "percent": "10%"},
    "0.01": {"target_faces": 1_649, "slug": "0p01", "percent": "1%"},
}
METHODS = (
    ("qem", "QEM"),
    ("qem4vr", "QEM4VR"),
    ("robustlpm", "RobustLPM"),
    ("ice", "ICE"),
    ("stmw", "STMW"),
    ("cwf", "CWF"),
    ("fa-qem", "FA-QEM"),
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    )
    for name in names:
        path = Path(name)
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: Any) -> None:
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = box[0] + (box[2] - box[0] - width) // 2
    y = box[1] + (box[3] - box[1] - height) // 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=(26, 31, 38))


def _tight_model_crop(panel: Image.Image) -> Image.Image:
    rgb = np.asarray(panel.convert("RGB"), dtype=np.int16)
    background_delta = np.max(np.abs(rgb - np.array([245, 245, 245], dtype=np.int16)), axis=2)
    rows, columns = np.nonzero(background_delta > 12)
    if len(rows) == 0:
        return panel
    padding = 12
    left = max(0, int(columns.min()) - padding)
    top = max(0, int(rows.min()) - padding)
    right = min(panel.width, int(columns.max()) + padding + 1)
    bottom = min(panel.height, int(rows.max()) + padding + 1)
    return panel.crop((left, top, right, bottom))


def _fit_panel(panel: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = ImageOps.contain(_tight_model_crop(panel), size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (250, 250, 250))
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def _collect_records(ratio: str) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    records = json.loads((REPORT / "summary.json").read_text(encoding="utf-8"))
    indexed = {
        (str(record["method"]), str(record["track"])): record
        for record in records
        if record["ratio"] == ratio
    }
    research = [indexed[(method, "research")] for method, _ in METHODS]
    return research, indexed


def build_figure(
    records: list[dict[str, Any]],
    ratio: str,
    percent: str,
    output_image: Path,
) -> None:
    margin = 36
    title_height = 70
    header_height = 54
    row_height = 220
    footer_height = 42
    column_widths = (220, 470, 470)
    grid_width = sum(column_widths)
    width = margin * 2 + grid_width
    height = margin + title_height + header_height + row_height * len(METHODS) + footer_height + margin
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    title_font = _font(30, bold=True)
    header_font = _font(20, bold=True)
    method_font = _font(24, bold=True)
    note_font = _font(15)

    _centered_text(
        draw,
        (margin, margin, margin + grid_width, margin + title_height),
        f"Ratio {ratio}：七种网格简化方法预览",
        title_font,
    )
    grid_top = margin + title_height
    x_positions = [margin]
    for column_width in column_widths:
        x_positions.append(x_positions[-1] + column_width)
    headers = ("方法", "中性材质几何", "正确 Base Color")
    for column, header in enumerate(headers):
        box = (x_positions[column], grid_top, x_positions[column + 1], grid_top + header_height)
        draw.rectangle(box, fill=(236, 239, 243))
        _centered_text(draw, box, header, header_font)

    for row, ((_method, display_name), record) in enumerate(zip(METHODS, records, strict=True)):
        row_top = grid_top + header_height + row * row_height
        row_bottom = row_top + row_height
        fill = (255, 255, 255) if row % 2 == 0 else (247, 248, 250)
        draw.rectangle((margin, row_top, margin + grid_width, row_bottom), fill=fill)
        _centered_text(draw, (x_positions[0], row_top, x_positions[1], row_bottom), display_name, method_font)

        contact_path = REPORT / str(record["contact_sheet"])
        contact = Image.open(contact_path).convert("RGB")
        panel_width = contact.width // 2
        header = 36
        neutral = contact.crop((0, header, panel_width, contact.height))
        base_color = contact.crop((panel_width, header, contact.width, contact.height))
        panel_size = (column_widths[1] - 24, row_height - 20)
        neutral = _fit_panel(neutral, panel_size)
        base_color = _fit_panel(base_color, panel_size)
        canvas.paste(neutral, (x_positions[1] + 12, row_top + 10))
        canvas.paste(base_color, (x_positions[2] + 12, row_top + 10))

    grid_bottom = grid_top + header_height + row_height * len(METHODS)
    for x in x_positions:
        draw.line((x, grid_top, x, grid_bottom), fill=(190, 196, 204), width=1)
    draw.line((margin, grid_top, margin + grid_width, grid_top), fill=(190, 196, 204), width=1)
    draw.line(
        (margin, grid_top + header_height, margin + grid_width, grid_top + header_height),
        fill=(190, 196, 204),
        width=1,
    )
    for row in range(1, len(METHODS) + 1):
        y = grid_top + header_height + row * row_height
        draw.line((margin, y, margin + grid_width, y), fill=(210, 214, 220), width=1)
    _centered_text(
        draw,
        (margin, grid_bottom, margin + grid_width, grid_bottom + footer_height),
        f"统一使用 {percent} 科研轨几何；右栏显示锁定源纹理或对应的源表面投影。",
        note_font,
    )
    output_image.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_image, optimize=True)


def _metric(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record
    for key in keys:
        value = value.get(key, {})
    return value


def build_markdown(
    records: list[dict[str, Any]],
    indexed: dict[tuple[str, str], dict[str, Any]],
    ratio: str,
    percent: str,
    target_faces: int,
    output_image: Path,
    output_markdown: Path,
) -> None:
    hausdorff_values = [
        float(_metric(record, "metrics", "geometry", "normalized_unit_diagonal", "hausdorff_symmetric_sampled"))
        for record in records
    ]
    chamfer_values = [
        float(_metric(record, "metrics", "geometry", "normalized_unit_diagonal", "chamfer_mean_squared_symmetric"))
        for record in records
    ]
    wall_values = [float(_metric(record, "timing", "algorithm_wall_seconds")) for record in records]
    rgb_values = [
        float(value)
        for method, _ in METHODS
        if isinstance(
            (value := _metric(indexed[(method, "asset")], "metrics", "texture", "symmetric_mean_rgb_l2")),
            (int, float),
        )
    ]
    rows = []
    for (method, display_name), research in zip(METHODS, records, strict=True):
        asset = indexed[(method, "asset")]
        actual_faces = int(research["actual_faces"])
        deviation = abs(actual_faces - target_faces) / target_faces * 100.0
        hausdorff = float(
            _metric(research, "metrics", "geometry", "normalized_unit_diagonal", "hausdorff_symmetric_sampled")
        )
        chamfer = float(
            _metric(research, "metrics", "geometry", "normalized_unit_diagonal", "chamfer_mean_squared_symmetric")
        )
        wall = float(_metric(research, "timing", "algorithm_wall_seconds"))
        topology = _metric(research, "metrics", "topology", "geometry_view")
        topology_text = (
            "watertight"
            if topology.get("watertight")
            else f"non-watertight; NM={topology.get('nonmanifold_edges')}"
        )
        rgb_value = _metric(asset, "metrics", "texture", "symmetric_mean_rgb_l2")
        hausdorff_text = f"{hausdorff:.8f}"
        chamfer_text = f"{chamfer:.3e}"
        wall_text = f"{wall:,.2f}"
        if hausdorff == min(hausdorff_values):
            hausdorff_text = f"**{hausdorff_text}**"
        if chamfer == min(chamfer_values):
            chamfer_text = f"**{chamfer_text}**"
        if wall == min(wall_values):
            wall_text = f"**{wall_text}**"
        if isinstance(rgb_value, (int, float)):
            rgb_text = f"{float(rgb_value):.6f}"
            if float(rgb_value) == min(rgb_values):
                rgb_text = f"**{rgb_text}**"
        else:
            rgb_text = "—"
        rows.append(
            f"| {display_name} | {actual_faces:,} | {deviation:.3f}% | {hausdorff_text} | "
            f"{chamfer_text} | {wall_text} | {topology_text} | {asset['status']} | {rgb_text} |"
        )
    content = f"""# Ratio {ratio}：七种网格简化方法汇总

![Ratio {ratio} 七种方法汇总](assets/{output_image.name})

## 关键指标

| 方法 | 实际面数 | 目标偏差 | H ↓ | C ↓ | Wall time (s) ↓ | 科研轨拓扑 | 资产轨状态 | RGB L2 ↓ |
|---|---:|---:|---:|---:|---:|---|---|---:|
""" + "\n".join(rows) + (
        "\n\n指标口径：`H` 为单位包围盒对角线坐标下的双向 sampled Hausdorff；"
        f"`C` 为 mean-squared symmetric Chamfer；几何指标和时间来自 {percent} 科研轨，"
        "RGB L2 来自对应的兼容资产轨。`—` 表示资产轨未通过硬门禁，"
        "因而没有可报告的纹理指标。数值越小越好。\n"
    )
    output_markdown.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratio", choices=tuple(RATIO_CONFIG), default="0.5")
    args = parser.parse_args()
    config = RATIO_CONFIG[args.ratio]
    slug = str(config["slug"])
    output_image = ROOT / "docs" / "assets" / f"ratio-{slug}-seven-methods.png"
    output_markdown = ROOT / "docs" / f"ratio-{slug}-seven-method-summary.md"
    records, indexed = _collect_records(args.ratio)
    build_figure(records, args.ratio, str(config["percent"]), output_image)
    build_markdown(
        records,
        indexed,
        args.ratio,
        str(config["percent"]),
        int(config["target_faces"]),
        output_image,
        output_markdown,
    )
    print(output_image)
    print(output_markdown)


if __name__ == "__main__":
    main()
