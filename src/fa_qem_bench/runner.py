from __future__ import annotations

import json
from pathlib import Path

from .adapters import AdapterContext, adapter_for
from .config import ExperimentConfig
from .mesh import load_mesh, mesh_topology
from .records import RunRecord, RunStatus
from .util import environment_snapshot, sha256_file


def run_id(method: str, ratio: str, track: str = "research") -> str:
    safe_ratio = ratio.replace(".", "p")
    return f"{method}-{safe_ratio}-{track}"


def run_baseline(config: ExperimentConfig, method: str, ratio: str) -> RunRecord:
    ratio = config.ratio_key(ratio)
    target = config.target(ratio)
    identifier = run_id(method, ratio)
    run_dir = config.artifacts / "runs" / identifier
    run_dir.mkdir(parents=True, exist_ok=True)
    record_path = run_dir / "run.json"
    adapter = adapter_for(method)
    available, detail = adapter.available(config.root)
    prepared_name = (
        "attribute_unit.obj"
        if method in {"qem4vr", "robustlpm"}
        else "geometry_unit.obj"
    )
    prepared_path = config.artifacts / "prepared" / prepared_name
    record = RunRecord(
        schema_version=1,
        run_id=identifier,
        method=method,
        method_source=adapter.source,
        track="research",
        ratio=ratio,
        target_faces=target,
        status=RunStatus.BUILD_FAILURE,
        source_sha256=sha256_file(config.source),
        input_sha256=sha256_file(prepared_path),
        environment=environment_snapshot(),
        parameters={"availability": detail, "threads": int(config.data["threads"])},
    )
    if not available:
        record.error = detail
        record.write(record_path)
        return record
    try:
        result = adapter.run(
            AdapterContext(
                root=config.root,
                prepared_mesh=prepared_path,
                run_dir=run_dir,
                target_faces=target,
                threads=int(config.data["threads"]),
                parameters={"seed": config.seed},
            )
        )
        output_mesh = load_mesh(result.output, process=False)
        actual = int(len(output_mesh.faces))
        relative_error = abs(actual - target) / target
        record.actual_faces = actual
        record.status = (
            RunStatus.SUCCESS
            if relative_error <= config.tolerance
            else RunStatus.TARGET_UNREACHABLE
        )
        record.output_path = str(result.output.relative_to(config.root))
        record.output_sha256 = sha256_file(result.output)
        record.command = result.command
        record.timing = result.timing
        record.parameters.update(result.parameters)
        record.metrics["native_topology"] = mesh_topology(output_mesh)
        record.metrics["target_relative_error"] = relative_error
    except Exception as error:  # boundary records failures rather than hiding them
        record.status = RunStatus.ALGORITHM_FAILURE
        record.error = f"{type(error).__name__}: {error}"
    record.write(record_path)
    return record


def load_run_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
