from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.texture import TextureVisuals

from fa_qem_bench.render import BaseColorSource, render_contact_sheet


def test_contact_sheet_projects_source_base_color_without_target_uv(tmp_path: Path) -> None:
    vertices = np.array([[-0.3, -0.3, 0.0], [0.3, -0.3, 0.0], [0.0, 0.3, 0.0]])
    faces = np.array([[0, 1, 2]])
    source = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        visual=TextureVisuals(uv=np.array([[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]])),
        process=False,
    )
    base_color = Image.new("RGB", (4, 4), (120, 70, 25))
    base_color_path = tmp_path / "basecolor.png"
    base_color.save(base_color_path)
    source_visual = cast(Any, source.visual)
    texture_source = BaseColorSource(source, np.asarray(source_visual.uv), base_color, base_color_path)

    target = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    target_path = tmp_path / "target.obj"
    target.export(target_path)
    output_path = tmp_path / "contact.png"

    metadata = render_contact_sheet(
        target_path,
        output_path,
        center=[0.0, 0.0, 0.0],
        diagonal=1.0,
        coordinates_are_normalized=True,
        label="fixture",
        resolution=64,
        base_color_source=texture_source,
    )

    rendered = np.asarray(Image.open(output_path).convert("RGB"))
    right_panel = rendered[36:, 64:]
    colored = right_panel[np.any(right_panel < 240, axis=2)]
    assert metadata["base_color_mode"] == "projected_source_base_color"
    assert len(colored) > 0
    assert float(colored[:, 0].mean()) > float(colored[:, 2].mean())


def test_contact_sheet_binds_pinned_source_image_to_native_uv(tmp_path: Path) -> None:
    vertices = np.array([[-0.3, -0.3, 0.0], [0.3, -0.3, 0.0], [0.0, 0.3, 0.0]])
    faces = np.array([[0, 1, 2]])
    uv = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]])
    base_color = Image.new("RGB", (4, 4), (120, 70, 25))
    source = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        visual=TextureVisuals(uv=uv),
        process=False,
    )
    base_color_path = tmp_path / "basecolor.png"
    base_color.save(base_color_path)
    texture_source = BaseColorSource(source, uv, base_color, base_color_path)
    target = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        visual=TextureVisuals(uv=uv),
        process=False,
    )
    target_path = tmp_path / "target.obj"
    target.export(target_path)

    metadata = render_contact_sheet(
        target_path,
        tmp_path / "contact.png",
        center=[0.0, 0.0, 0.0],
        diagonal=1.0,
        coordinates_are_normalized=True,
        label="fixture",
        resolution=64,
        base_color_source=texture_source,
    )

    assert metadata["base_color_mode"] == "original_uv_with_source_base_color"
