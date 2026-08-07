from pathlib import Path

from fa_qem_bench.config import ExperimentConfig
from fa_qem_bench.records import RunRecord, RunStatus
from fa_qem_bench.repair import _native_hard_failure, repair_run
from fa_qem_bench.runner import load_run_record
from fa_qem_bench.util import sha256_file


def test_repair_materializes_asset_failure_when_research_has_no_output(tmp_path: Path) -> None:
    source = tmp_path / "source.glb"
    source.write_bytes(b"fixture")
    config = ExperimentConfig(
        root=tmp_path,
        path=tmp_path / "experiment.yaml",
        data={"repair": {"tool_root": str(tmp_path / "repair-tool")}},
    )
    research_id = "cwf-0p5-research"
    research_path = tmp_path / "artifacts" / "runs" / research_id / "run.json"
    RunRecord(
        schema_version=1,
        run_id=research_id,
        method="cwf",
        method_source="official",
        track="research",
        ratio="0.5",
        target_faces=100,
        status=RunStatus.ALGORITHM_FAILURE,
        source_sha256=sha256_file(source),
        error="fixture failure",
    ).write(research_path)

    result = repair_run(config, research_id)

    assert result["status"] == RunStatus.ALGORITHM_FAILURE
    asset = load_run_record(tmp_path / "artifacts" / "runs" / "cwf-0p5-asset" / "run.json")
    assert asset["track"] == "asset"
    assert asset["repair_lineage"]["action"] == "not_possible"
    assert asset["error"] == "research output unavailable: ALGORITHM_FAILURE"


def test_external_hard_gate_can_override_clean_internal_topology() -> None:
    record = {
        "metrics": {
            "native_topology": {
                "boundary_edges": 0,
                "nonmanifold_edges": 0,
                "degenerate_faces": 0,
                "finite_vertices": True,
                "winding_consistent": True,
            },
            "external_inspection": {"hard_constraints": {"passed": False, "failed": ["DEGENERATE"]}},
        }
    }
    assert _native_hard_failure(record) is True
