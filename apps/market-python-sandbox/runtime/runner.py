"""Entry point of one analysis execution process (started by the harness as a non-root slot user).

Order matters and is fixed:
1. read the harness-written job file (read-only for this user);
2. lower resource limits and pin the CPU set (irreversible for a non-root process);
3. install the seccomp filter while the process is still single-threaded;
4. only then import analytical libraries, seed randomness, and execute the model's code.

The process exits 0 when the code finished (outputs are in output/index.json), 3 when it raised,
and anything else means it was killed or crashed. Structured errors go to output/error.json.
"""
from __future__ import annotations

import json
import os
import resource
import signal
import sys
import traceback

EXIT_OK, EXIT_ERROR = 0, 3
MESSAGE_MAX = 800
TRACE_FRAMES = 6


def _limit(which: int, value: int) -> None:
    resource.setrlimit(which, (value, value))


def _write_error(output_dir: str, code: str, exc: BaseException | None, message: str | None = None) -> None:
    frames = []
    if exc is not None:
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename == "<analysis>":  # only the model's own code; no library or harness paths
                frames.append({"line": frame.lineno, "code": (frame.line or "")[:200]})
    text = message if message is not None else f"{type(exc).__name__}: {exc}"
    payload = {"code": code, "exception_type": type(exc).__name__ if exc is not None else None,
               "message": text[:MESSAGE_MAX], "analysis_frames": frames[-TRACE_FRAMES:]}
    path = os.path.join(output_dir, "error.json")
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.replace(path + ".tmp", path)


def _chain(exc: BaseException):
    """The exception, its causes/contexts, and wrapped reasons (e.g. URLError.reason)."""
    seen: set[int] = set()
    stack = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen or len(seen) > 20:
            continue
        seen.add(id(current))
        yield current
        stack.extend(x for x in (current.__cause__, current.__context__, getattr(current, "reason", None))
                     if isinstance(x, BaseException))


def _classify(exc: BaseException) -> str:
    import errno as _errno

    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.isupper() and type(exc).__module__ == "saniti":
        return code
    if isinstance(exc, SyntaxError):
        return "SYNTAX_ERROR"
    for item in _chain(exc):
        if isinstance(item, MemoryError):
            return "MEMORY_LIMIT_EXCEEDED"
        if isinstance(item, OSError) and item.errno == _errno.EFBIG:
            return "OUTPUT_LIMIT_EXCEEDED"
        if isinstance(item, OSError) and item.errno in (_errno.EPERM, _errno.EACCES):
            return "FORBIDDEN_OPERATION"  # denied by the sandbox (seccomp or file permissions)
        if type(item).__name__ == "gaierror":
            return "FORBIDDEN_OPERATION"  # name resolution needs a socket, which is denied
    return "PYTHON_EXCEPTION"


def main(job_dir: str) -> int:
    with open(os.path.join(job_dir, "job.json"), encoding="utf-8") as handle:
        job = json.load(handle)
    output_dir = os.path.join(job_dir, "output")
    limits = job["limits"]

    mib = 1 << 20
    _limit(resource.RLIMIT_AS, int(limits["virtual_memory_mb"]) * mib)
    _limit(resource.RLIMIT_CPU, int(limits["cpu_seconds"]))
    _limit(resource.RLIMIT_FSIZE, int(limits["max_artifact_bytes"]))
    _limit(resource.RLIMIT_NOFILE, 256)
    _limit(resource.RLIMIT_NPROC, int(limits["max_threads"]))
    _limit(resource.RLIMIT_CORE, 0)
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)  # oversized writes fail with EFBIG instead of killing
    if job.get("cpus"):
        os.sched_setaffinity(0, set(job["cpus"]))

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import seccomp

    if job.get("require_seccomp", True):
        seccomp.install()

    import saniti

    saniti._configure(job, output_dir)
    import random

    random.seed(saniti.SEED)
    try:
        import numpy

        numpy.random.seed(saniti.SEED)
    except ImportError:  # pragma: no cover
        pass
    try:
        import duckdb

        threads = int(job.get("threads", 1))
        duckdb.default_connection().execute(f"SET threads = {threads}")
        _connect = duckdb.connect

        def connect(database=":memory:", read_only=False, config=None, **kwargs):
            config = dict(config or {})
            config.setdefault("threads", threads)  # resource default, not a security control
            return _connect(database, read_only, config, **kwargs)

        duckdb.connect = connect
    except ImportError:  # pragma: no cover
        pass

    source = job["code"]
    namespace = {"__name__": "__main__", "__builtins__": __builtins__, "DATASETS": dict(saniti.DATASETS),
                 "SEED": saniti.SEED}
    import linecache

    linecache.cache["<analysis>"] = (len(source), None, source.splitlines(True), "<analysis>")
    try:
        code = compile(source, "<analysis>", "exec")
        exec(code, namespace)  # noqa: S102 - this process *is* the isolated sandbox
    except SystemExit as exc:
        if exc.code not in (None, 0):
            _write_error(output_dir, "PYTHON_EXCEPTION", exc, f"The analysis exited with status {exc.code!r}.")
            return EXIT_ERROR
    except BaseException as exc:  # noqa: BLE001 - every failure is reported as a structured error
        _write_error(output_dir, _classify(exc), exc)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
