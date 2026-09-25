"""One persistent analysis session: a long-lived, confined Python process that keeps its namespace between
executions (variables, functions, intermediate results), so the model can load, inspect, define, call, revise and
rerun code against one governed bundle.

Started by the harness as the session's dedicated non-root user, with a constructed environment and no inherited
secrets. Before reading any command it lowers its resource limits (the session's whole CPU budget, virtual memory,
file size, process count), pins its CPUs and installs the seccomp filter (no sockets, no new processes). It then
reads one JSON command per line on stdin and writes one JSON answer per line to the response pipe; the code's own
print() output is captured and bounded, never mixed into the protocol.

    {"op": "execute", "seq": n, "execution_id": "...", "code": "..."}
        -> {"status": OK | SCRIPT_ERROR | INSUFFICIENT_INPUT_DATA | TIMEOUT, stdout, error, outputs, access,
            variables}
    {"op": "inspect", "seq": n, "names": [...], "max_rows": k}  -> {"variables": [...]}
    {"op": "ping", "seq": n}                                    -> {"status": "OK"}

A wall-clock limit is enforced by the harness with SIGINT (KeyboardInterrupt here, the session survives) and, if
the code does not yield, SIGKILL (the session ends). Anything the code reports about itself is kept only as
bounded diagnostics.
"""
from __future__ import annotations

import io
import json
import os
import sys
import traceback

STDOUT_MAX = 4000
MESSAGE_MAX = 800
FRAMES = 8


class _Bounded(io.TextIOBase):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.dropped = 0

    def write(self, text: str) -> int:
        if self.size < self.limit * 4:
            self.parts.append(text)
            self.size += len(text)
        else:
            self.dropped += len(text)
        return len(text)

    def value(self) -> str:
        text = "".join(self.parts)
        if len(text) > self.limit:
            text = "...[earlier output truncated]\n" + text[-self.limit:]
        return text


def _field(exc: BaseException) -> str | None:
    """The missing key, attribute or name an error is about (e.g. a column the code expected)."""
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])[:200]
    for attribute in ("name", "obj"):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and isinstance(exc, (AttributeError, NameError)):
            return value[:200]
    return None


def _error(exc: BaseException) -> dict:
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__):
        if frame.filename.startswith("<execution_"):
            frames.append({"execution": frame.filename.strip("<>"), "line": frame.lineno,
                           "code": (frame.line or "")[:200]})
    last = frames[-1] if frames else None
    return {"error_type": type(exc).__name__, "message": f"{exc}"[:MESSAGE_MAX], "line": last["line"] if last else None,
            "field": _field(exc), "traceback": frames[-FRAMES:],
            "exception": "".join(traceback.format_exception_only(type(exc), exc))[-MESSAGE_MAX:]}


def _describe(name: str, value, max_rows: int) -> dict:
    """A bounded, JSON-safe description of one variable."""
    kind = type(value).__name__
    entry: dict = {"name": name, "type": f"{type(value).__module__}.{kind}"}
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            entry.update(shape=list(value.shape), columns=[str(c) for c in value.columns[:100]],
                         dtypes={str(c): str(t) for c, t in list(value.dtypes.items())[:100]},
                         head=json.loads(value.head(max_rows).to_json(orient="records", date_format="iso",
                                                                      default_handler=str))[:max_rows])
            return entry
        if isinstance(value, pd.Series):
            entry.update(length=len(value), dtype=str(value.dtype),
                         head=json.loads(value.head(max_rows).to_json(date_format="iso", default_handler=str)))
            return entry
    except Exception:  # noqa: BLE001 - description is best effort
        pass
    shape = getattr(value, "shape", None)
    if shape is not None and hasattr(value, "dtype"):
        entry.update(shape=list(shape), dtype=str(value.dtype))
        return entry
    if callable(value):
        import inspect

        try:
            entry["signature"] = f"{name}{inspect.signature(value)}"
        except (TypeError, ValueError):
            pass
        doc = (getattr(value, "__doc__", None) or "").strip().splitlines()
        entry["doc"] = doc[0][:200] if doc else None
        return entry
    text = repr(value)
    entry["repr"] = text[:1000] + ("..." if len(text) > 1000 else "")
    if hasattr(value, "__len__"):
        try:
            entry["length"] = len(value)
        except TypeError:
            pass
    return entry


HIDDEN = {"__name__", "__builtins__", "saniti", "pd", "np", "__doc__", "__loader__", "__spec__", "__package__"}


def main(session_dir: str, response_fd: str) -> int:
    with open(os.path.join(session_dir, "session.json"), encoding="utf-8") as handle:
        session = json.load(handle)
    runtime = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, runtime)
    import confine

    confine.apply(session["limits"], session.get("cpus"), session.get("require_seccomp", True))
    out = os.fdopen(int(response_fd), "w", encoding="utf-8", buffering=1)
    import linecache
    import random

    import numpy
    import pandas
    import saniti_session as saniti

    sys.modules["saniti"] = saniti  # `import saniti` gives the session helpers
    saniti._configure(session, session_dir)
    random.seed(saniti.SEED)
    numpy.random.seed(saniti.SEED)
    saniti._lock_duckdb()
    namespace = {"__name__": "__main__", "__builtins__": __builtins__, "saniti": saniti, "pd": pandas, "np": numpy,
                 **{name: getattr(saniti, name) for name in saniti.__all__}}
    base = set(namespace)
    helper_ids = {id(v) for v in namespace.values()}

    def reply(payload: dict) -> None:
        out.write(json.dumps(payload, default=str, separators=(",", ":")) + "\n")
        out.flush()

    reply({"seq": 0, "status": "READY", "pid": os.getpid()})
    while True:
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:  # an interrupt that arrived between executions
            continue
        if not line:
            return 0
        try:
            message = json.loads(line)
        except ValueError:
            continue
        seq = message.get("seq")
        op = message.get("op")
        if op == "ping":
            reply({"seq": seq, "status": "OK"})
            continue
        if op == "inspect":
            names = message.get("names") or [n for n in namespace if n not in base and not n.startswith("_")
                                               and id(namespace[n]) not in helper_ids]
            rows = max(0, min(int(message.get("max_rows") or 5), 20))
            variables = []
            for name in names[:50]:
                if name not in namespace:
                    variables.append({"name": name, "missing": True})
                else:
                    variables.append(_describe(name, namespace[name], rows if message.get("names") else 0))
            reply({"seq": seq, "status": "OK", "variables": variables})
            continue
        if op != "execute":
            reply({"seq": seq, "status": "UNKNOWN_OP"})
            continue
        filename = f"<{message['execution_id']}>".replace("<exe_", "<execution_")
        source = message.get("code") or ""
        linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
        before = {name: id(value) for name, value in namespace.items()}
        captured = _Bounded(STDOUT_MAX)
        saniti._begin()
        status, error, insufficient = "OK", None, None
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = captured
        try:
            code = compile(source, filename, "exec")
            exec(code, namespace)  # noqa: S102 - this process *is* the isolated session
        except KeyboardInterrupt:
            status = "TIMEOUT"
        except saniti.InsufficientInputData as exc:
            status = "INSUFFICIENT_INPUT_DATA"
            insufficient = {"data_request_id": exc.data_request_id, "range_id": exc.range_id,
                            "requirement": exc.requirement, "reason": exc.reason}
        except SystemExit as exc:
            if exc.code not in (None, 0):
                status, error = "SCRIPT_ERROR", _error(exc)
        except BaseException as exc:  # noqa: BLE001 - every failure is reported as a structured error
            status, error = "SCRIPT_ERROR", _error(exc)
            if isinstance(exc, MemoryError):
                error["error_type"] = "MemoryError"
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        changed = sorted(n for n, v in namespace.items() if n not in base and not n.startswith("_")
                         and before.get(n) != id(v))
        recorded = saniti._end()
        reply({"seq": seq, "status": status, "stdout": captured.value(), "error": error,
               "insufficient": insufficient, "outputs": recorded["outputs"], "access": recorded["access"],
               "warnings": recorded["warnings"], "variables": changed[:50]})


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
