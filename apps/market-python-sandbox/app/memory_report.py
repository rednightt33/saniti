"""Read-only memory report of the sandbox container (FUTURE_PLAN U1, user go 2026-10-26: "Boleh juga dijalankan untuk
pilihan satu"). The service held about 0.6-0.7 GB while idle (railway metrics, 2026-10-22..25) and Railway SSH cannot be
reached from the operator's session, so the janitor logs where that memory sits: the resident size of each process,
the container's cgroup counters, and which data libraries the main process has imported. It changes nothing."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

DATA_LIBRARIES = ("duckdb", "pyarrow", "pandas", "numpy", "polars", "talib")
CGROUP_FIELDS = ("anon", "file", "kernel", "shmem", "sock")


def _status(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            key, _, value = line.partition(":")
            fields[key] = value.strip()
    except OSError:
        pass
    return fields


def _kib(value: str | None) -> int | None:
    try:
        return int(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def snapshot(proc: Path = Path("/proc"), cgroup: Path = Path("/sys/fs/cgroup"), top: int = 8) -> dict[str, Any]:
    """{main_rss_mb, processes: [{pid, name, rss_mb}], process_count, cgroup_mb: {...}, main_imports: [...]}."""
    processes = []
    for entry in proc.glob("[0-9]*"):
        status = _status(entry / "status")
        rss = _kib(status.get("VmRSS"))
        if rss is not None:
            processes.append({"pid": int(entry.name), "name": status.get("Name", "?"), "rss_mb": round(rss / 1024, 1)})
    processes.sort(key=lambda p: p["rss_mb"], reverse=True)
    own = _kib(_status(proc / str(os.getpid()) / "status").get("VmRSS"))
    report: dict[str, Any] = {
        "main_rss_mb": round(own / 1024, 1) if own is not None else None,
        "process_count": len(processes),
        "processes_rss_mb_total": round(sum(p["rss_mb"] for p in processes), 1),
        "processes": processes[:top],
        "main_imports": [name for name in DATA_LIBRARIES if name in sys.modules],
    }
    cgroup_mb: dict[str, float] = {}
    try:
        cgroup_mb["current"] = round(int((cgroup / "memory.current").read_text()) / 1048576, 1)
        for line in (cgroup / "memory.stat").read_text().splitlines():
            key, _, value = line.partition(" ")
            if key in CGROUP_FIELDS:
                cgroup_mb[key] = round(int(value) / 1048576, 1)
    except (OSError, ValueError):
        pass
    report["cgroup_mb"] = cgroup_mb
    return report


def release() -> dict[str, Any]:
    """Return freed heap of the main process to the operating system (FUTURE_PLAN U1, measured 2026-10-26: the main
    process grew 187 -> 481 MB after two analyses and kept it while idle, with duckdb and pandas imported; the session
    workers had exited). Covers every main-process data path at the allocator, not one call site: the Arrow pool
    (mimalloc) gives back unused pages and glibc trims its heap. Imported library code is not released. Never raises."""
    before = _kib(_status(Path("/proc/self/status")).get("VmRSS"))
    steps: list[str] = []
    if "pyarrow" in sys.modules:
        try:
            sys.modules["pyarrow"].default_memory_pool().release_unused()
            steps.append("arrow_pool")
        except Exception:  # noqa: BLE001 - an older or different pool
            pass
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        steps.append("malloc_trim")
    except Exception:  # noqa: BLE001 - not glibc
        pass
    after = _kib(_status(Path("/proc/self/status")).get("VmRSS"))
    return {"steps": steps,
            "rss_before_mb": round(before / 1024, 1) if before is not None else None,
            "rss_after_mb": round(after / 1024, 1) if after is not None else None}
