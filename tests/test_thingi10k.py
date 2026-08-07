from __future__ import annotations

import csv
from pathlib import Path

from fa_qem_bench.thingi10k import select_thingi10k_subset, summarize_thingi10k_runs


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_thingi10k_selection_is_stratified_and_deterministic(tmp_path: Path) -> None:
    geometry: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    for file_id in range(100, 116):
        group = (file_id - 100) // 4
        geometry.append(
            {
                "file_id": file_id,
                "num_vertices": 4000,
                "num_faces": 6000,
                "vertex_manifold": 0 if group == 1 else 1,
                "edge_manifold": 1,
                "num_boundary_edges": 4 if group == 2 else 0,
                "num_connected_components": 2 if group == 3 else 1,
                "num_self_intersections": 0,
                "oriented": 1,
                "num_geometrical_degenerated_faces": 0,
                "num_combinatorial_degenerated_faces": 0,
            }
        )
        summary.append({"ID": file_id, "License": "CC-BY", "Link": f"https://example.test/{file_id}.stl"})
    _write_csv(tmp_path / "geometry_data.csv", geometry)
    _write_csv(tmp_path / "input_summary.csv", summary)

    first = select_thingi10k_subset(tmp_path, seed=7, per_split_per_stratum=1)
    second = select_thingi10k_subset(tmp_path, seed=7, per_split_per_stratum=1)

    assert first == second
    assert len(first) == 8
    assert {(item.stratum, item.split) for item in first} == {
        (stratum, split)
        for stratum in ("clean_closed", "nonmanifold", "open_manifold", "multi_or_intersecting")
        for split in ("validation", "holdout")
    }


def test_thingi10k_summary_excludes_failures_from_error_mean() -> None:
    metrics = {
        "geometry": {
            "normalized_unit_diagonal": {
                "hausdorff_symmetric_sampled": 0.2,
                "chamfer_mean_squared_symmetric": 0.03,
            }
        }
    }
    summary = summarize_thingi10k_runs(
        [
            {"ratio": 0.1, "status": "SUCCESS", "wall_seconds": 2.0, "metrics": metrics},
            {"ratio": 0.1, "status": "ALGORITHM_FAILURE"},
        ]
    )
    assert summary["0.1"]["success_rate"] == 0.5
    assert summary["0.1"]["mean_hausdorff_symmetric_sampled"] == 0.2
