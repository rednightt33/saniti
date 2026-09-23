"""Source pre-checks: syntax, and a defense-in-depth screen for clearly dangerous imports and calls.

This screen is NOT the security boundary. It exists to give the model an early, explicit error
for code that could never work in the sandbox. The boundary is the execution process itself: a
non-root user with no credentials, resource limits, and a kernel seccomp filter that denies
sockets, program execution, and process creation (see runtime/seccomp.py).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass

FORBIDDEN_MODULES = {
    "subprocess", "socket", "ssl", "socketserver", "asyncio", "selectors", "requests", "httpx", "urllib",
    "urllib3", "aiohttp", "http", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "webbrowser",
    "multiprocessing", "pty", "pexpect", "ctypes", "cffi", "resource", "signal", "pip", "ensurepip", "venv",
    "importlib", "psycopg", "psycopg2", "sqlalchemy", "boto3", "botocore", "paramiko", "docker", "shutil",
}
FORBIDDEN_OS_CALLS = {
    "system", "popen", "fork", "forkpty", "kill", "killpg", "execv", "execve", "execl", "execle", "execlp",
    "execlpe", "execvp", "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp",
    "spawnvpe", "posix_spawn", "posix_spawnp", "setuid", "setgid", "chroot", "unshare", "setns", "putenv",
    "unsetenv", "environ", "getenv", "environb",
}
FORBIDDEN_BUILTINS = {"__import__", "breakpoint", "input"}


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    line: int | None


def check_source(source: str) -> Violation | None:
    try:
        tree = ast.parse(source, filename="<analysis>", mode="exec")
    except SyntaxError as exc:
        return Violation("SYNTAX_ERROR", f"SyntaxError: {exc.msg} (line {exc.lineno})", exc.lineno)
    except (ValueError, RecursionError, MemoryError) as exc:
        return Violation("SYNTAX_ERROR", f"The code could not be parsed: {type(exc).__name__}.", None)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    return Violation("FORBIDDEN_IMPORT", f"Importing {alias.name!r} is not allowed in the sandbox.",
                                     node.lineno)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level == 0 and root in FORBIDDEN_MODULES:
                return Violation("FORBIDDEN_IMPORT", f"Importing from {node.module!r} is not allowed in the sandbox.",
                                 node.lineno)
            if root == "os" and any(a.name in FORBIDDEN_OS_CALLS for a in node.names):
                return Violation("FORBIDDEN_OPERATION", "Process, environment, and privilege operations from 'os' "
                                                        "are not allowed in the sandbox.", node.lineno)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr in FORBIDDEN_OS_CALLS:
                return Violation("FORBIDDEN_OPERATION", f"os.{node.attr} is not allowed in the sandbox.", node.lineno)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_BUILTINS:
            return Violation("FORBIDDEN_OPERATION", f"{node.id}() is not allowed in the sandbox.", node.lineno)
    return None
