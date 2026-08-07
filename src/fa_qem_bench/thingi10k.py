from __future__ import annotations

import csv
import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .evaluate import evaluate_paths
from .mesh import normalization_transform, normalized_vertices
from .process import run_measured_wsl
from .util import atomic_json, environment_snapshot, sha256_file

THINGI10K_METADATA_COMMIT = "aaae0bb650cf464eb6c7d86d5ce39597cb71e106"
THINGI10K_INDIVIDUAL_NPZ_COMMIT = "901c950e67abfafbc1718ab3e3cd480d51cc003e"
THINGI10K_ARCHIVE_SHA256 = "0a9e3e7f0df0393c9f12959b5c3691ec01a4032a9c5c13ee9cc9a6e3f3d11e0c"
CORRUPT_FILE_IDS = frozenset({49911, 74463, 77942, 81313, 286163})
STRATA = ("clean_closed", "nonmanifold", "open_manifold", "multi_or_intersecting")


@dataclass(frozen=True)
class Thingi10KSelection:
    file_id: int
    split: str
    stratum: str
    num_vertices: int
    num_faces: int
    license: str
    original_url: str


def _integer(row: dict[str, str], key: str) -> int:
    value = row.get(key, "")
    return int(float(value)) if value else 0


def _stratum(row: dict[str, str]) -> str | None:
    nonmanifold = _integer(row, "vertex_manifold") != 1 or _integer(row, "edge_manifold") != 1
    open_mesh = _integer(row, "num_boundary_edges") > 0
    multi_or_intersecting = (
        _integer(row, "num_connected_components") > 1 or _integer(row, "num_self_intersections") > 0
    )
    clean = (
        not nonmanifold
        and not open_mesh
        and not multi_or_intersecting
        and _integer(row, "oriented") == 1
        and _integer(row, "num_geometrical_degenerated_faces") == 0
        and _integer(row, "num_combinatorial_degenerated_faces") == 0
    )
    if clean:
        return "clean_closed"
    if nonmanifold:
        return "nonmanifold"
    if open_mesh:
        return "open_manifold"
    if multi_or_intersecting:
        return "multi_or_intersecting"
    return None


def select_thingi10k_subset(
    metadata_dir: Path,
    *,
    seed: int,
    per_split_per_stratum: int = 2,
    minimum_faces: int = 5_000,
    maximum_faces: int = 200_000,
) -> list[Thingi10KSelection]:
    with (metadata_dir / "geometry_data.csv").open(encoding="utf-8-sig", newline="") as stream:
        geometry = {int(row["file_id"]): row for row in csv.DictReader(stream)}
    with (metadata_dir / "input_summary.csv").open(encoding="utf-8-sig", newline="") as stream:
        summary = {int(row["ID"]): row for row in csv.DictReader(stream)}

    candidates: dict[str, list[tuple[str, int]]] = {name: [] for name in STRATA}
    for file_id, row in geometry.items():
        if file_id in CORRUPT_FILE_IDS or file_id not in summary:
            continue
        num_faces = _integer(row, "num_faces")
        if not minimum_faces <= num_faces <= maximum_faces:
            continue
        stratum = _stratum(row)
        if stratum is None:
            continue
        digest = hashlib.sha256(f"{seed}:{file_id}".encode()).hexdigest()
        candidates[stratum].append((digest, file_id))

    selections: list[Thingi10KSelection] = []
    count_per_stratum = 2 * per_split_per_stratum
    for stratum in STRATA:
        ranked = sorted(candidates[stratum])
        if len(ranked) < count_per_stratum:
            raise ValueError(f"not enough models in {stratum}: {len(ranked)}")
        for index, (_, file_id) in enumerate(ranked[:count_per_stratum]):
            row = geometry[file_id]
            context = summary[file_id]
            selections.append(
                Thingi10KSelection(
                    file_id=file_id,
                    split="validation" if index < per_split_per_stratum else "holdout",
                    stratum=stratum,
                    num_vertices=_integer(row, "num_vertices"),
                    num_faces=_integer(row, "num_faces"),
                    license=context.get("License", "unknown") or "unknown",
                    original_url=context.get("Link", ""),
                )
            )
    return selections


def write_thingi10k_manifest(
    metadata_dir: Path,
    dataset_root: Path,
    output_path: Path,
    *,
    seed: int,
    per_split_per_stratum: int = 2,
) -> dict[str, Any]:
    selections = select_thingi10k_subset(
        metadata_dir,
        seed=seed,
        per_split_per_stratum=per_split_per_stratum,
    )
    metadata_hashes = {
        path.name: sha256_file(path) for path in sorted(metadata_dir.glob("*.csv")) if path.is_file()
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset": "Thingi10K npz",
        "metadata_repository_commit": THINGI10K_METADATA_COMMIT,
        "npz_repository_commit": THINGI10K_INDIVIDUAL_NPZ_COMMIT,
        "full_archive_sha256": THINGI10K_ARCHIVE_SHA256,
        "dataset_root": str(dataset_root.resolve()),
        "selection": {
            "seed": seed,
            "algorithm": "sort each topology stratum by sha256(f'{seed}:{file_id}')",
            "per_split_per_stratum": per_split_per_stratum,
            "minimum_faces": 5_000,
            "maximum_faces": 200_000,
            "strata": list(STRATA),
            "metadata_sha256": metadata_hashes,
        },
        "models": [item.__dict__ for item in selections],
    }
    atomic_json(output_path, manifest)
    return manifest


def fetch_thingi10k_subset(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_root = Path(manifest["dataset_root"])
    npz_root = dataset_root / "npz"
    npz_root.mkdir(parents=True, exist_ok=True)
    commit = str(manifest["npz_repository_commit"])
    downloads: dict[str, dict[str, Any]] = {}
    for model in manifest["models"]:
        file_id = int(model["file_id"])
        target = npz_root / f"{file_id}.npz"
        url = f"https://huggingface.co/datasets/Thingi10K/Thingi10K/resolve/{commit}/npz/{file_id}.npz"
        if not target.is_file():
            temporary = target.with_suffix(".npz.part")
            request = urllib.request.Request(url, headers={"User-Agent": "fa-qem-bench/0.1"})
            with urllib.request.urlopen(request, timeout=300) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        mesh = _npz_mesh(target)
        downloads[str(file_id)] = {
            "url": url,
            "sha256": sha256_file(target),
            "bytes": target.stat().st_size,
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
        }
    manifest["downloads"] = downloads
    atomic_json(manifest_path, manifest)
    return downloads


def _npz_mesh(path: Path) -> trimesh.Trimesh:
    with np.load(path) as payload:
        if "vertices" not in payload or "facets" not in payload:
            raise ValueError(f"Thingi10K NPZ is missing vertices/facets: {path}")
        vertices = np.asarray(payload["vertices"], dtype=np.float64)
        faces = np.asarray(payload["facets"], dtype=np.int64)
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError(f"Thingi10K model is not triangular: {path}")
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    suffix = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{suffix}"


def _published_command(executable: Path, source: Path, output: Path, target_faces: int) -> list[str]:
    return [
        "wsl.exe",
        _wsl_path(executable),
        "--method",
        "fa-qem",
        "--input",
        _wsl_path(source),
        "--output",
        _wsl_path(output),
        "--target-faces",
        str(target_faces),
        "--area-weight",
        "100",
        "--boundary-weight",
        "500",
        "--uv-weight",
        "5000",
        "--normal-weight",
        "0.01",
        "--plane-area-weight",
        "1",
        "--virtual-radius",
        "0.01",
    ]


def run_thingi10k_subset(
    root: Path,
    manifest_path: Path,
    *,
    split: str,
    ratios: tuple[float, ...] = (0.1, 0.01),
    samples: int = 100_000,
    seed: int = 20240801,
    variant: str = "published",
) -> dict[str, Any]:
    if split not in {"validation", "holdout"}:
        raise ValueError("split must be validation or holdout")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_root = Path(manifest["dataset_root"])
    executable = root / "build-wsl" / "bin" / "paper_simplify"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    if variant not in {"published", "paper-topology", "adaptive-topology", "final-topology"}:
        raise ValueError("unsupported Thingi10K implementation variant")
    output_root = root / "artifacts" / "thingi10k" / variant / split
    result_path = output_root / "results.json"
    results: dict[str, Any]
    if result_path.is_file():
        results = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        results = {
            "schema_version": 1,
            "split": split,
            "variant": variant,
            "samples_per_direction": samples,
            "seed": seed,
            "manifest_sha256": sha256_file(manifest_path),
            "environment": environment_snapshot(root),
            "runs": [],
        }
    completed = {
        (int(run["file_id"]), float(run["ratio"]))
        for run in results["runs"]
        if run.get("status") in {"SUCCESS", "TARGET_UNREACHABLE"}
    }
    selected = [model for model in manifest["models"] if model["split"] == split]
    for model in selected:
        file_id = int(model["file_id"])
        npz_path = dataset_root / "npz" / f"{file_id}.npz"
        for ratio in ratios:
            if (file_id, ratio) in completed:
                continue
            run_dir = output_root / str(file_id) / f"ratio-{ratio:g}"
            run_dir.mkdir(parents=True, exist_ok=True)
            record: dict[str, Any] = {
                "file_id": file_id,
                "split": split,
                "stratum": model["stratum"],
                "license": model["license"],
                "ratio": ratio,
                "source_npz": str(npz_path),
            }
            try:
                source_mesh = _npz_mesh(npz_path)
                transform = normalization_transform(source_mesh)
                source_mesh.vertices = normalized_vertices(source_mesh.vertices, transform)
                source_path = run_dir / "source_unit.obj"
                source_mesh.export(source_path)
                target_faces = max(1, round(len(source_mesh.faces) * ratio))
                output_path = run_dir / "native.obj"
                command = _published_command(executable, source_path, output_path, target_faces)
                measured = run_measured_wsl(command, root, run_dir / "logs")
                record.update(
                    {
                        "input_faces": int(len(source_mesh.faces)),
                        "target_faces": target_faces,
                        "source_sha256": sha256_file(npz_path),
                        "command": measured.command,
                        "wall_seconds": measured.wall_seconds,
                        "cpu_seconds": measured.cpu_seconds,
                        "peak_rss_bytes": measured.peak_rss_bytes,
                        "resource_measurement": measured.resource_source,
                    }
                )
                if measured.returncode not in {0, 2} or not output_path.is_file():
                    record.update({"status": "ALGORITHM_FAILURE", "returncode": measured.returncode})
                else:
                    output_mesh = trimesh.load_mesh(output_path, process=False)
                    actual_faces = int(len(output_mesh.faces))
                    record.update(
                        {
                            "status": (
                                "SUCCESS"
                                if abs(actual_faces - target_faces) / target_faces <= 0.02
                                else "TARGET_UNREACHABLE"
                            ),
                            "returncode": measured.returncode,
                            "actual_faces": actual_faces,
                            "output_sha256": sha256_file(output_path),
                            "metrics": evaluate_paths(
                                source_path,
                                output_path,
                                count=samples,
                                seed=seed + file_id,
                            ),
                        }
                    )
            except Exception as error:  # noqa: BLE001 - every model failure is a benchmark result
                record.update({"status": "ALGORITHM_FAILURE", "error": f"{type(error).__name__}: {error}"})
            results["runs"] = [
                previous
                for previous in results["runs"]
                if (int(previous["file_id"]), float(previous["ratio"])) != (file_id, ratio)
            ]
            results["runs"].append(record)
            atomic_json(result_path, results)
    results["summary"] = summarize_thingi10k_runs(results["runs"])
    atomic_json(result_path, results)
    return results


def summarize_thingi10k_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for ratio in sorted({float(run["ratio"]) for run in runs}):
        selected = [run for run in runs if float(run["ratio"]) == ratio]
        successful = [run for run in selected if run.get("status") == "SUCCESS" and "metrics" in run]
        normalized = [run["metrics"]["geometry"]["normalized_unit_diagonal"] for run in successful]
        summary[f"{ratio:g}"] = {
            "total": len(selected),
            "success": len(successful),
            "success_rate": len(successful) / len(selected) if selected else 0.0,
            "mean_hausdorff_symmetric_sampled": (
                float(np.mean([item["hausdorff_symmetric_sampled"] for item in normalized])) if normalized else None
            ),
            "mean_chamfer_mean_squared_symmetric": (
                float(np.mean([item["chamfer_mean_squared_symmetric"] for item in normalized])) if normalized else None
            ),
            "mean_wall_seconds": (
                float(np.mean([run["wall_seconds"] for run in successful])) if successful else None
            ),
            "status_counts": {
                status: sum(run.get("status") == status for run in selected)
                for status in sorted({str(run.get("status")) for run in selected})
            },
        }
    return summary
