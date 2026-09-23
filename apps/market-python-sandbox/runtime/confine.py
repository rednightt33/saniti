"""Irreversible confinement of an analysis or validator process, applied before any untrusted work.

Resource limits and the CPU set are lowered first (a non-root process cannot raise them again),
then the seccomp filter is installed while the process is still single-threaded.
"""
from __future__ import annotations

import os
import resource
import signal


def _limit(which: int, value: int) -> None:
    resource.setrlimit(which, (value, value))


def apply(limits: dict, cpus: list[int] | None, require_seccomp: bool = True) -> None:
    mib = 1 << 20
    _limit(resource.RLIMIT_AS, int(limits["virtual_memory_mb"]) * mib)
    _limit(resource.RLIMIT_CPU, int(limits["cpu_seconds"]))
    _limit(resource.RLIMIT_FSIZE, int(limits["max_file_bytes"]))
    _limit(resource.RLIMIT_NOFILE, 256)
    _limit(resource.RLIMIT_NPROC, int(limits["max_threads"]))
    _limit(resource.RLIMIT_CORE, 0)
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)  # oversized writes fail with EFBIG instead of killing
    if cpus:
        os.sched_setaffinity(0, set(cpus))
    import seccomp

    if require_seccomp:
        seccomp.install()
