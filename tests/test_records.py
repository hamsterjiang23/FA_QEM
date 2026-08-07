from fa_qem_bench.records import RunRecord, RunStatus


def test_failure_is_a_serializable_result(tmp_path) -> None:
    record = RunRecord(
        schema_version=1,
        run_id="cwf-0p5-research",
        method="cwf",
        method_source="official",
        track="research",
        ratio="0.5",
        target_faces=100,
        status=RunStatus.BUILD_FAILURE,
        error="compiler unavailable",
    )
    path = tmp_path / "run.json"
    record.write(path)
    assert '"status": "BUILD_FAILURE"' in path.read_text(encoding="utf-8")
