from fa_qem_bench.process import _gnu_time_metrics


def test_run_measured_wsl_preserves_nonzero_process_result(monkeypatch, tmp_path):
    from fa_qem_bench.process import ProcessResult, run_measured_wsl

    failed = ProcessResult(
        command=["wsl.exe"],
        returncode=1,
        wall_seconds=0.1,
        cpu_seconds=0.0,
        peak_rss_bytes=10,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        resource_source="psutil_process_tree",
    )
    failed.stderr_path.write_text("WSL failed before GNU time started", encoding="utf-8")
    monkeypatch.setattr("fa_qem_bench.process.run_measured", lambda *_args, **_kwargs: failed)
    assert run_measured_wsl(["wsl.exe", "true"], tmp_path, tmp_path).returncode == 1


def test_gnu_time_metrics_parser() -> None:
    stderr = """
Command being timed: "example"
User time (seconds): 1.25
System time (seconds): 0.75
Maximum resident set size (kbytes): 4096
"""

    cpu_seconds, peak_rss_bytes = _gnu_time_metrics(stderr)

    assert cpu_seconds == 2.0
    assert peak_rss_bytes == 4 * 1024 * 1024
