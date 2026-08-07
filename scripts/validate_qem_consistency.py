from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from fa_qem_bench.evaluate import geometry_metrics
from fa_qem_bench.mesh import load_mesh, mesh_topology
from fa_qem_bench.util import atomic_json


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    suffix = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--samples", type=int, default=100_000)
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args()
    root = args.root.resolve()
    fixture = root / "tests" / "fixtures" / "octahedron.obj"
    qslim = root / "external" / "qslim" / "qslim"
    shared = root / "build-wsl" / "bin" / "paper_simplify"
    for required in (fixture, qslim, shared):
        if not required.is_file():
            raise FileNotFoundError(required)
    output_dir = root / "artifacts" / "validation" / "qem-consistency"
    output_dir.mkdir(parents=True, exist_ok=True)
    qslim_output = output_dir / "qslim.obj"
    shared_output = output_dir / "shared-qem.obj"
    commands = [
        ["wsl.exe", _wsl_path(qslim), "-s", "4", "-o", _wsl_path(qslim_output), _wsl_path(fixture)],
        [
            "wsl.exe",
            _wsl_path(shared),
            "--method",
            "stmw",
            "--input",
            _wsl_path(fixture),
            "--output",
            _wsl_path(shared_output),
            "--target-faces",
            "4",
            "--virtual-radius",
            "0.01",
        ],
    ]
    for command in commands:
        subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)

    original = load_mesh(fixture)
    qslim_mesh = load_mesh(qslim_output)
    shared_mesh = load_mesh(shared_output)
    qslim_error = geometry_metrics(original, qslim_mesh, args.samples, 7)
    shared_error = geometry_metrics(original, shared_mesh, args.samples, 7)
    comparisons: dict[str, Any] = {}
    for metric in ("hausdorff_symmetric_sampled", "chamfer_mean_squared_symmetric"):
        first = qslim_error[metric]
        second = shared_error[metric]
        comparisons[metric] = {
            "qslim": first,
            "shared": second,
            "relative_difference": abs(first - second) / max(abs(first), abs(second), 1e-30),
        }
    qslim_topology = mesh_topology(qslim_mesh)
    shared_topology = mesh_topology(shared_mesh)
    passed = (
        len(qslim_mesh.faces) == len(shared_mesh.faces) == 4
        and qslim_topology["watertight"]
        and shared_topology["watertight"]
        and all(item["relative_difference"] <= args.tolerance for item in comparisons.values())
    )
    result = {
        "status": "SUCCESS" if passed else "FAILED",
        "samples": args.samples,
        "relative_tolerance": args.tolerance,
        "commands": commands,
        "qslim_topology": qslim_topology,
        "shared_topology": shared_topology,
        "comparisons": comparisons,
    }
    atomic_json(output_dir / "result.json", result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
