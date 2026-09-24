"""Entry point of one analysis execution process (started by the harness as a non-root slot user).

Order matters and is fixed:
1. read the harness-written runtime file (read-only for this user);
2. confine the process: resource limits, CPU set, then the seccomp filter (runtime/confine.py);
3. configure the saniti helper from the workspace manifest and the approved spec, and replace
   DuckDB's connections with locked ones (memory and temp-disk limits, no external files outside
   the workspace, no extensions, no attachments, configuration locked);
4. only then seed randomness and execute analysis.py.

The process exits 0 when the code finished (outputs are in output/index.json), 3 when it raised,
and anything else means it was killed or crashed. Structured errors go to output/error.json.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

EXIT_OK, EXIT_ERROR = 0, 3
MESSAGE_MAX = 800
TRACE_FRAMES = 6


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
        if isinstance(item, MemoryError) or type(item).__name__ == "OutOfMemoryException":
            return "MEMORY_LIMIT_EXCEEDED"
        if isinstance(item, OSError) and item.errno == _errno.EFBIG:
            return "OUTPUT_LIMIT_EXCEEDED"
        if isinstance(item, OSError) and item.errno in (_errno.EPERM, _errno.EACCES):
            return "FORBIDDEN_OPERATION"  # denied by the sandbox (seccomp or file permissions)
        if type(item).__name__ in ("gaierror", "PermissionException"):
            return "FORBIDDEN_OPERATION"  # sockets are denied; DuckDB refused a file outside the workspace
    return "PYTHON_EXCEPTION"


def main(job_dir: str) -> int:
    with open(os.path.join(job_dir, "runtime.json"), encoding="utf-8") as handle:
        runtime = json.load(handle)
    output_dir = os.path.join(job_dir, "output")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import confine

    confine.apply(runtime["limits"], runtime.get("cpus"), runtime.get("require_seccomp", True))

    import saniti

    saniti._configure(runtime, job_dir)
    import random

    random.seed(saniti.SEED)
    try:
        import numpy

        numpy.random.seed(saniti.SEED)
    except ImportError:  # pragma: no cover
        pass
    saniti._lock_duckdb()

    with open(os.path.join(job_dir, "analysis.py"), encoding="utf-8") as handle:
        source = handle.read()
    # The helper module and its public names are pre-bound, so `saniti.load(...)`, `emit_table(...)` and
    # `import saniti` all work; pandas and numpy are pre-bound as pd and np (the conventional names).
    import numpy
    import pandas

    namespace = {"__name__": "__main__", "__builtins__": __builtins__, "saniti": saniti, "pd": pandas, "np": numpy,
                 **{name: getattr(saniti, name) for name in saniti.__all__}}
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
    finally:
        saniti._flush()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
