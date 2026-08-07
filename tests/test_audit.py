from pathlib import Path

from fa_qem_bench.audit import audit_experiment
from fa_qem_bench.config import ExperimentConfig
from fa_qem_bench.util import sha256_file


def test_empty_audit_reports_all_expected_records_missing(tmp_path: Path) -> None:
    source = tmp_path / "source.glb"
    source.write_bytes(b"fixture")
    config = ExperimentConfig(
        root=tmp_path,
        path=tmp_path / "experiment.yaml",
        data={
            "source": {"path": "source.glb", "sha256": sha256_file(source)},
            "targets": {"0.5": 50, "0.1": 10, "0.01": 1},
        },
    )

    result = audit_experiment(config)

    assert result["expected_records"] == 36
    assert result["records"] == 0
    assert len(result["missing"]) == 36
    assert result["errors"] == []
