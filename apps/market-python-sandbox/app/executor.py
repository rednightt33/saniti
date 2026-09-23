"""Runs one analysis in a fresh, isolated process and watches it.

The child is started directly by the C-level subprocess implementation (no preexec_fn) as a
dedicated non-root slot user, in its own process group, with a constructed environment (nothing
inherited from this process, which holds the service keys), closed file descriptors, and a
private working directory. runtime/runner.py then lowers its resource limits, pins its CPU set,
and installs the seccomp filter before any model code runs.

This watchdog enforces the wall-clock limit, the resident-memory limit (sampled every 100 ms; the
child also has a hard RLIMIT_AS virtual-memory ceiling), and the job disk quota, and kills the
whole process group on any breach. Seccomp forbids fork, so the group is a single process.
"""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings

POLL_SECONDS = 0.1
DISK_CHECK_SECONDS = 1.0
MAX_WALK_ENTRIES = 20000


@dataclass
class Outcome:
    kind: str  # OK | ERROR | TIMEOUT | MEMORY | DISK | CPU | FORBIDDEN | CRASH
    returncode: int | None
    runtime_ms: int
    cpu_seconds: float = 0.0
    max_rss_mb: float = 0.0
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: dict[str, Any] | None = None
    notes: dict[str, Any] = field(default_factory=dict)


def child_environment(settings: Settings, home: Path, tmp: Path) -> dict[str, str]:
    threads = str(settings.threads_per_job)
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(tmp),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC", "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "PYTHONNOUSERSITE": "1",
        "OMP_NUM_THREADS": threads, "OPENBLAS_NUM_THREADS": threads, "MKL_NUM_THREADS": threads,
        "NUMEXPR_MAX_THREADS": threads, "POLARS_MAX_THREADS": threads, "RAYON_NUM_THREADS": threads,
        "MPLBACKEND": "Agg", "MPLCONFIGDIR": str(home / ".matplotlib"), "XDG_CACHE_HOME": str(home / ".cache"),
    }


def _tail(path: Path, chars: int) -> str:
    if chars <= 0 or not path.exists():
        return ""
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - chars * 4))
        text = handle.read().decode("utf-8", errors="replace")
    return text[-chars:]


def _rss_mb(pid: int) -> float:
    try:
        with open(f"/proc/{pid}/status") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        pass
    return 0.0


def disk_usage(root: Path) -> int:
    total, seen, stack = 0, 0, [str(root)]
    while stack and seen < MAX_WALK_ENTRIES:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    seen += 1
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(entry.path)
                    else:
                        total += info.st_blocks * 512
        except OSError:
            continue
    return total


def read_child_json(path: Path, uid: int | None, max_bytes: int) -> Any:
    """Read a small JSON file written by the analysis process without following links."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes or (uid is not None and info.st_uid != uid):
            raise ValueError("unexpected file")
        with os.fdopen(os.dup(fd), "rb") as handle:
            return json.loads(handle.read(max_bytes + 1))
    finally:
        os.close(fd)


class Executor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.drop_privileges = os.geteuid() == 0

    def run(self, job_dir: Path, uid: int, *, script: str = "runner.py", args: tuple[str, ...] = (),
            cwd: Path | None = None, home: Path | None = None, tmp: Path | None = None,
            quotas: dict[Path, int] | None = None, deadline_seconds: int | None = None, memory_mb: int | None = None,
            cpu_seconds: int | None = None, error_dir: Path | None = None, log_name: str = "analysis",
            on_start: Callable[[int], None] | None = None) -> Outcome:
        """Start runtime/<script> as `uid` on this job and watch time, resident memory, and disk quotas."""
        s = self.settings
        cwd = cwd or job_dir / "intermediate"
        home = home or cwd / "home"
        tmp = tmp or cwd / "tmp"
        quotas = quotas if quotas is not None else {job_dir / "intermediate": s.max_intermediate_bytes,
                                                    job_dir / "output": s.max_output_dir_bytes}
        error_dir = error_dir or job_dir / "output"
        memory_limit = memory_mb or s.max_memory_mb
        cpu_limit = cpu_seconds or s.cpu_seconds
        stdout_path, stderr_path = job_dir / f"{log_name}.stdout.log", job_dir / f"{log_name}.stderr.log"
        entry = str(Path(s.runtime_dir) / script)
        limit = deadline_seconds or s.max_runtime_seconds
        kwargs: dict[str, Any] = {}
        if self.drop_privileges:
            kwargs.update(user=uid, group=uid, extra_groups=[])
        with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
            started = time.monotonic()
            process = subprocess.Popen(
                [s.python_executable, "-s", "-B", entry, str(job_dir), *args],
                cwd=str(cwd), env=child_environment(s, home, tmp), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                close_fds=True, process_group=0, umask=0o077, **kwargs)
        if on_start is not None:
            on_start(process.pid)
        reason, peak_rss, next_disk, disk_note = None, 0.0, started + DISK_CHECK_SECONDS, None
        peak_disk: dict[str, int] = {}
        status, usage = None, None
        while True:
            pid, raw_status, raw_usage = os.wait4(process.pid, os.WNOHANG)
            if pid:
                status, usage = raw_status, raw_usage
                break
            now = time.monotonic()
            rss = _rss_mb(process.pid)
            peak_rss = max(peak_rss, rss)
            if now - started > limit:
                reason = "TIMEOUT"
            elif rss > memory_limit:
                reason = "MEMORY"
            elif now >= next_disk:
                next_disk = now + DISK_CHECK_SECONDS
                for path, quota in quotas.items():
                    used = disk_usage(path)
                    peak_disk[path.name] = max(peak_disk.get(path.name, 0), used)
                    if used > quota:
                        reason, disk_note = "DISK", path.name
                        break
            if reason:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, usage = os.wait4(process.pid, 0)
                break
            time.sleep(POLL_SECONDS)
        for path in quotas:
            peak_disk[path.name] = max(peak_disk.get(path.name, 0), disk_usage(path))
        process.returncode = os.waitstatus_to_exitcode(status)
        runtime_ms = round((time.monotonic() - started) * 1000)
        outcome = Outcome(
            kind="OK", returncode=process.returncode, runtime_ms=runtime_ms,
            cpu_seconds=round(usage.ru_utime + usage.ru_stime, 3) if usage else 0.0,
            max_rss_mb=round(max(peak_rss, (usage.ru_maxrss / 1024) if usage else 0.0), 1),
            stdout_tail=_tail(stdout_path, s.diagnostics_chars), stderr_tail=_tail(stderr_path, s.diagnostics_chars),
            notes={"peak_disk_bytes": peak_disk, **({"disk_quota_exceeded": disk_note} if disk_note else {})})
        code = process.returncode
        if reason:
            outcome.kind = reason
        elif code == 0:
            outcome.kind = "OK"
        elif code == 3:
            outcome.kind = "ERROR"
            try:
                outcome.error = read_child_json(error_dir / "error.json", uid if self.drop_privileges else None, 65536)
            except (OSError, ValueError):
                outcome.error = None
        elif code in (-signal.SIGXCPU, -signal.SIGKILL) and outcome.cpu_seconds >= cpu_limit - 1:
            outcome.kind = "CPU"
        elif code == -signal.SIGSYS:
            outcome.kind = "FORBIDDEN"
        else:
            outcome.kind = "CRASH"
        return outcome
