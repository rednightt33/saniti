"""Startup self-test: proves, in a real execution process, that isolation is enforced here.

The test job goes through exactly the same path as an analysis (slot user, constructed
environment, runner, rlimits, seccomp) and then tries what model code must not be able to do.
The service reports ready only when every mandatory check passes; otherwise every analysis is
refused with SANDBOX_ISOLATION_UNAVAILABLE. It also records the library versions of the image.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .executor import Executor, child_environment, read_child_json

SELFTEST_CODE = r'''
import errno, json, os, platform, socket
checks = {}
def denied(name, fn, codes):
    try:
        fn()
        checks[name] = "FAIL: allowed"
    except OSError as exc:
        checks[name] = "PASS" if exc.errno in codes else f"FAIL: errno {exc.errno}"
def fork():
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
status = open("/proc/self/status").read()
checks["uid_non_root"] = "PASS" if os.getuid() != 0 and os.geteuid() != 0 else "FAIL: running as root"
checks["seccomp_filter_active"] = "PASS" if "Seccomp:\t2" in status else "FAIL: no seccomp filter"
checks["no_new_privs"] = "PASS" if "NoNewPrivs:\t1" in status else "FAIL: no_new_privs not set"
denied("socket_inet_denied", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM), {errno.EACCES})
denied("socket_inet6_denied", lambda: socket.socket(socket.AF_INET6, socket.SOCK_DGRAM), {errno.EACCES})
denied("socket_unix_denied", lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM), {errno.EACCES})
denied("fork_denied", fork, {errno.EPERM})
denied("execve_denied", lambda: os.execv("/bin/true", ["/bin/true"]), {errno.EPERM})
denied("parent_environment_unreadable", lambda: open(f"/proc/{os.getppid()}/environ", "rb").read(1),
       {errno.EACCES, errno.EPERM})
denied("pid1_environment_unreadable", lambda: open("/proc/1/environ", "rb").read(1), {errno.EACCES, errno.EPERM})
allowed_env = set(json.loads(ALLOWED_ENV))
checks["environment_clean"] = "PASS" if set(os.environ) <= allowed_env else "FAIL: unexpected variables"
versions = {"python": platform.python_version()}
import numpy, pandas, polars, pyarrow, duckdb, scipy, statsmodels, matplotlib, talib
for module in (numpy, pandas, polars, pyarrow, duckdb, scipy, statsmodels, matplotlib, talib):
    versions[module.__name__] = module.__version__
versions["ta-lib-c"] = talib.__ta_version__.decode().split(" ")[0] if isinstance(talib.__ta_version__, bytes) else str(talib.__ta_version__)
close = numpy.array([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61,
                     46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64], dtype=float)
rsi = talib.RSI(close, timeperiod=14)
sma = talib.SMA(close, timeperiod=5)
std = talib.STDDEV(close, timeperiod=5)
o = numpy.full(12, 10.0); h = numpy.full(12, 10.5); l = numpy.full(12, 9.8); c = numpy.full(12, 10.2)
o[-2], h[-2], l[-2], c[-2] = 10.0, 10.1, 8.9, 9.0      # bearish candle
o[-1], h[-1], l[-1], c[-1] = 8.9, 10.6, 8.8, 10.5      # bullish candle whose body engulfs it
engulf = talib.CDLENGULFING(o, h, l, c)
ok = (numpy.isnan(rsi[:14]).all() and 0 < rsi[-1] < 100 and abs(sma[-1] - close[-5:].mean()) < 1e-9
      and abs(std[-1] - close[-5:].std()) < 1e-9 and int(engulf[-1]) == 100)
checks["talib_functions"] = "PASS" if ok else "FAIL: unexpected TA-Lib results"
with open(os.path.join(os.path.dirname(DATASETS_DIR), "output", "selftest.json"), "w") as handle:
    json.dump({"checks": checks, "versions": versions}, handle)
'''
UID_CHECKS = {"uid_non_root", "parent_environment_unreadable", "pid1_environment_unreadable"}


@dataclass
class IsolationReport:
    ok: bool = False
    checks: dict[str, str] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)
    failure: str | None = None

    def public(self) -> dict[str, Any]:
        return {"isolation_enforced": self.ok, "checks": self.checks, "failure": self.failure}


def run_selftest(settings: Settings, executor: Executor, uid: int, cpus: list[int]) -> IsolationReport:
    job_dir = Path(settings.jobs_dir) / "selftest"
    shutil.rmtree(job_dir, ignore_errors=True)
    from .service import prepare_job_dir  # local import avoids a cycle

    work = job_dir / "work"
    allowed = sorted(child_environment(settings, work))
    code = (f"ALLOWED_ENV = {json.dumps(json.dumps(allowed))}\nDATASETS_DIR = {json.dumps(str(job_dir / 'input'))}\n"
            + SELFTEST_CODE)
    prepare_job_dir(settings, job_dir, uid if executor.drop_privileges else None, {
        "code": code, "datasets": {}, "seed": settings.random_seed, "limits": settings.child_limits(),
        "expected_outputs": [], "cpus": cpus, "threads": settings.threads_per_job, "require_seccomp": True})
    report = IsolationReport()
    try:
        outcome = executor.run(job_dir, uid, deadline_seconds=max(60, settings.max_runtime_seconds))
        if outcome.kind != "OK":
            detail = (outcome.error or {}).get("message") or outcome.stderr_tail[-300:]
            report.failure = f"self-test process ended with {outcome.kind}: {detail}"
            return report
        result = read_child_json(job_dir / "output" / "selftest.json",
                                 uid if executor.drop_privileges else None, 65536)
        report.checks, report.versions = result["checks"], result["versions"]
        mandatory = {k: v for k, v in report.checks.items()
                     if settings.require_isolation or k not in UID_CHECKS}
        failed = sorted(k for k, v in mandatory.items() if v != "PASS")
        report.ok = not failed and (executor.drop_privileges or not settings.require_isolation)
        if failed:
            report.failure = "failed checks: " + ", ".join(failed)
        elif not report.ok:
            report.failure = "the service is not running as root, so it cannot start analyses as a separate user"
        return report
    except (OSError, ValueError, KeyError) as exc:
        report.failure = f"self-test could not complete: {type(exc).__name__}"
        return report
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
