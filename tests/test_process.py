from fa_qem_bench.process import _gnu_time_metrics


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
