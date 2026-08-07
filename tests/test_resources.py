from pathlib import Path

from fa_qem_bench.resources import read_wsl_monitor


def test_read_wsl_monitor_marks_late_peak_as_lower_bound(tmp_path: Path) -> None:
    monitor = tmp_path / "monitor.csv"
    monitor.write_text(
        "timestamp_utc,pid,elapsed_seconds,cpu_percent,rss_kib,vsz_kib,cpu_time,disk_bytes\n"
        "2026-08-07T00:00:00Z,12,180,50,100,200,00:01:30,10\n"
        "2026-08-07T00:01:00Z,12,240,60,120,220,00:02:00,20\n",
        encoding="utf-8",
    )
    result = read_wsl_monitor(monitor)
    assert result["algorithm_wall_seconds"] == 240.0
    assert result["cpu_seconds"] == 120.0
    assert result["peak_rss_bytes"] == 120 * 1024
    assert result["peak_rss_is_lower_bound"] is True
