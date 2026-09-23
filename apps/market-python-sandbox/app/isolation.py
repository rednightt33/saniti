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
def duck_denied(name, fn, expected):
    # Only DuckDB's own refusal counts: a network failure would mean the configuration allowed the attempt.
    try:
        fn()
        checks[name] = "FAIL: allowed"
    except Exception as exc:
        checks[name] = "PASS" if type(exc).__name__ == expected else f"FAIL: {type(exc).__name__}"
refused = "PermissionException"
duck_denied("duckdb_outside_file_denied", lambda: duckdb.sql("SELECT * FROM read_text('/etc/hostname')").fetchall(),
            refused)
duck_denied("duckdb_config_locked", lambda: duckdb.sql("SET enable_external_access = true"), "InvalidInputException")
duck_denied("duckdb_extension_install_denied", lambda: duckdb.sql("INSTALL httpfs"), refused)
duck_denied("duckdb_extension_load_denied", lambda: duckdb.sql("LOAD httpfs"), refused)
duck_denied("duckdb_attach_denied", lambda: duckdb.sql("ATTACH '/tmp/saniti-selftest.duckdb'"), refused)
second = duckdb.connect()
duck_denied("duckdb_new_connection_locked", lambda: second.sql("SELECT * FROM read_text('/etc/hostname')").fetchall(),
            refused)
value, unit = duckdb.sql("SELECT current_setting('memory_limit')").fetchone()[0].split()
mib = float(value) * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "TiB": 1024 * 1024}.get(unit, 0)
checks["duckdb_memory_limit"] = "PASS" if abs(mib * 1.048576 - DUCKDB_MB) < 2 else f"FAIL: {value} {unit}"
with open(os.path.join(OUTPUT_DIR, "selftest.json"), "w") as handle:
    json.dump({"checks": checks, "versions": versions}, handle)
'''
UID_CHECKS = {"uid_non_root", "parent_environment_unreadable", "pid1_environment_unreadable",
              "validator_uid_non_root"}


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
    from .service import _write_readonly, prepare_workspace  # local import avoids a cycle

    drop = executor.drop_privileges
    home = job_dir / "intermediate" / "home"
    allowed = sorted(child_environment(settings, home, job_dir / "intermediate" / "tmp"))
    code = (f"ALLOWED_ENV = {json.dumps(json.dumps(allowed))}\nOUTPUT_DIR = {json.dumps(str(job_dir / 'output'))}\n"
            f"DUCKDB_MB = {settings.duckdb_memory_mb}\n" + SELFTEST_CODE)
    prepare_workspace(settings, job_dir, uid if drop else None, settings.validator_uid if drop else None,
                      manifest={"logical_datasets": {}}, analysis_spec={"spec": {}}, code=code)
    _write_readonly(job_dir / "runtime.json", {
        "limits": settings.child_limits(), "cpus": cpus, "threads": settings.threads_per_job, "require_seccomp": True,
        "seed": settings.random_seed, "expected_outputs": [], "inputs": {}, "analysis_period": {},
        "duckdb": {"memory_limit_mb": settings.duckdb_memory_mb, "threads": settings.threads_per_job,
                   "temp_directory": str(job_dir / "intermediate" / ".duckdb_tmp"), "max_temp_directory_mb": 64,
                   "allowed_directories": [str(job_dir / "input") + "/", str(job_dir / "intermediate") + "/"]}})
    report = IsolationReport()
    try:
        outcome = executor.run(job_dir, uid, deadline_seconds=max(60, settings.max_runtime_seconds))
        if outcome.kind != "OK":
            detail = (outcome.error or {}).get("message") or outcome.stderr_tail[-300:]
            report.failure = f"self-test process ended with {outcome.kind}: {detail}"
            return report
        result = read_child_json(job_dir / "output" / "selftest.json", uid if drop else None, 65536)
        report.checks, report.versions = result["checks"], result["versions"]
        validator_home = job_dir / "validation" / "home"
        _write_readonly(job_dir / "validation" / "request.json", {
            "mode": "selftest", "limits": settings.validator_limits(), "cpus": cpus, "require_seccomp": True})
        checked = executor.run(job_dir, settings.validator_uid, script="validator.py", args=("selftest",),
                               cwd=validator_home, home=validator_home, tmp=validator_home / "tmp",
                               quotas={validator_home: 16 << 20}, deadline_seconds=60,
                               memory_mb=settings.validator_memory_mb,
                               error_dir=job_dir / "validation" / "result", log_name="validator-selftest")
        if checked.kind != "OK":
            report.failure = f"validator self-test ended with {checked.kind}: {checked.stderr_tail[-300:]}"
            return report
        validator = read_child_json(job_dir / "validation" / "result" / "selftest.json",
                                    settings.validator_uid if drop else None, 65536)
        if validator.get("validator_error"):
            report.failure = f"validator self-test failed: {validator['validator_error'][:200]}"
            return report
        report.checks.update({f"validator_{k}": v for k, v in validator["checks"].items()})
        mandatory = {k: v for k, v in report.checks.items()
                     if settings.require_isolation or k not in UID_CHECKS}
        failed = sorted(k for k, v in mandatory.items() if v != "PASS")
        report.ok = not failed and (drop or not settings.require_isolation)
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
