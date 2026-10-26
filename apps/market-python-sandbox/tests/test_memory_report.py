"""FUTURE_PLAN U1 (2026-10-26): the janitor's read-only memory report."""
from __future__ import annotations

import os
from pathlib import Path

from app import memory_report


def fake_proc(root: Path, pid: int, name: str, rss_kib: int) -> None:
    (root / str(pid)).mkdir(parents=True)
    (root / str(pid) / "status").write_text(f"Name:\t{name}\nVmRSS:\t{rss_kib} kB\n")


def test_the_report_lists_processes_by_size_and_reads_the_cgroup(tmp_path) -> None:
    proc, cgroup = tmp_path / "proc", tmp_path / "cgroup"
    fake_proc(proc, os.getpid(), "uvicorn", 512000)
    fake_proc(proc, 99999, "python3", 102400)
    (proc / "self").mkdir()  # not a process id: ignored
    cgroup.mkdir()
    (cgroup / "memory.current").write_text(str(700 * 1048576))
    (cgroup / "memory.stat").write_text(f"anon {600 * 1048576}\nfile {80 * 1048576}\npgfault 12\n")
    report = memory_report.snapshot(proc, cgroup)
    assert report["main_rss_mb"] == 500.0 and report["process_count"] == 2
    assert [p["name"] for p in report["processes"]] == ["uvicorn", "python3"]
    assert report["cgroup_mb"] == {"current": 700.0, "anon": 600.0, "file": 80.0}
    assert set(report["main_imports"]) <= set(memory_report.DATA_LIBRARIES)


def test_a_missing_proc_or_cgroup_gives_an_empty_report_not_an_error(tmp_path) -> None:
    report = memory_report.snapshot(tmp_path / "none", tmp_path / "none")
    assert report["process_count"] == 0 and report["cgroup_mb"] == {} and report["main_rss_mb"] is None


def test_release_gives_back_freed_memory_and_never_raises() -> None:
    import pyarrow as pa
    table = pa.array(range(2_000_000))  # allocate in the Arrow pool, then free it
    del table
    result = memory_report.release()
    assert "arrow_pool" in result["steps"] and "malloc_trim" in result["steps"]
    assert result["rss_after_mb"] is not None and result["rss_before_mb"] is not None


def test_the_janitor_releases_before_it_reports() -> None:
    import inspect
    from app.service import AnalysisService
    source = inspect.getsource(AnalysisService.cleanup)
    assert source.index("memory_report.release()") < source.index("memory_report.snapshot()")
