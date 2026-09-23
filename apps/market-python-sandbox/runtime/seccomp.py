"""Kernel-enforced syscall filter for the analysis process (x86_64 Linux, seccomp-bpf).

Installed by runner.py before any model code runs and before any library can start a thread
(and with SECCOMP_FILTER_FLAG_TSYNC in case one did). A seccomp filter cannot be removed and is
inherited by every thread, so model code cannot undo it.

What it enforces:
- no sockets at all: socket() fails with EACCES (no TCP/UDP/DNS, no raw, netlink, or Unix-domain
  sockets, so no network egress and no access to internal services); only an anonymous
  AF_UNIX socketpair() is allowed.
- no new programs or processes: execve/execveat, fork/vfork, and clone() without CLONE_THREAD
  fail with EPERM; clone3 fails with ENOSYS so the C library falls back to clone() for threads.
- no process inspection or kernel-surface escalation: ptrace, process_vm_*, pidfd_getfd, bpf,
  perf_event_open, io_uring, keyrings, (u)mount and the new mount API, namespaces, module
  loading, kexec, handle-based opens, userfaultfd, and similar calls fail with EPERM.
- any other architecture or the x32 ABI kills the process.

This is not a network namespace: Railway does not permit namespaces inside a container (probed on
dev, see README). It denies socket creation to this one process tree instead.
"""
from __future__ import annotations

import ctypes
import errno
import struct

AUDIT_ARCH_X86_64 = 0xC000003E
X32_SYSCALL_BIT = 0x40000000
CLONE_THREAD = 0x00010000
AF_UNIX = 1

SYS_SOCKET, SYS_SOCKETPAIR, SYS_CLONE, SYS_CLONE3 = 41, 53, 56, 435
SYS_FORK, SYS_VFORK, SYS_EXECVE, SYS_EXECVEAT = 57, 58, 59, 322

# x86_64 syscall numbers denied with EPERM.
DENIED = {
    SYS_FORK: "fork", SYS_VFORK: "vfork", SYS_EXECVE: "execve", SYS_EXECVEAT: "execveat",
    101: "ptrace", 310: "process_vm_readv", 311: "process_vm_writev", 312: "kcmp", 438: "pidfd_getfd",
    440: "process_madvise", 321: "bpf", 298: "perf_event_open", 323: "userfaultfd",
    425: "io_uring_setup", 426: "io_uring_enter", 427: "io_uring_register",
    248: "add_key", 249: "request_key", 250: "keyctl",
    165: "mount", 166: "umount2", 155: "pivot_root", 161: "chroot", 428: "open_tree", 429: "move_mount",
    430: "fsopen", 431: "fsconfig", 432: "fsmount", 433: "fspick", 442: "mount_setattr",
    272: "unshare", 308: "setns", 175: "init_module", 313: "finit_module", 176: "delete_module",
    246: "kexec_load", 320: "kexec_file_load", 169: "reboot", 167: "swapon", 168: "swapoff",
    163: "acct", 179: "quotactl", 303: "name_to_handle_at", 304: "open_by_handle_at",
    300: "fanotify_init", 133: "mknod", 259: "mknodat", 135: "personality",
}

# BPF opcodes
LD_W_ABS = 0x20
JEQ_K = 0x15
JGE_K = 0x35
JSET_K = 0x45
RET_K = 0x06

RET_ALLOW = 0x7FFF0000
RET_KILL_PROCESS = 0x80000000
RET_ERRNO = 0x00050000

PR_SET_NO_NEW_PRIVS = 38
SECCOMP_SET_MODE_FILTER = 1
SECCOMP_FILTER_FLAG_TSYNC = 1
SYS_SECCOMP = 317


def _stmt(code: int, k: int) -> bytes:
    return struct.pack("HBBI", code, 0, 0, k)


def _jump(code: int, k: int, jt: int, jf: int) -> bytes:
    return struct.pack("HBBI", code, jt, jf, k)


def build_filter() -> list[bytes]:
    eperm, eacces, enosys = RET_ERRNO | errno.EPERM, RET_ERRNO | errno.EACCES, RET_ERRNO | errno.ENOSYS
    prog = [
        _stmt(LD_W_ABS, 4),                                   # arch
        _jump(JEQ_K, AUDIT_ARCH_X86_64, 1, 0),
        _stmt(RET_K, RET_KILL_PROCESS),
        _stmt(LD_W_ABS, 0),                                   # syscall number
        _jump(JGE_K, X32_SYSCALL_BIT, 0, 1),
        _stmt(RET_K, RET_KILL_PROCESS),
        _jump(JEQ_K, SYS_SOCKET, 0, 1),
        _stmt(RET_K, eacces),
        _jump(JEQ_K, SYS_CLONE3, 0, 1),
        _stmt(RET_K, enosys),
    ]
    for number in sorted(DENIED):
        prog += [_jump(JEQ_K, number, 0, 1), _stmt(RET_K, eperm)]
    prog += [
        _jump(JEQ_K, SYS_CLONE, 0, 4),                        # clone: threads only
        _stmt(LD_W_ABS, 16),                                  # args[0] (flags), low 32 bits
        _jump(JSET_K, CLONE_THREAD, 0, 1),
        _stmt(RET_K, RET_ALLOW),
        _stmt(RET_K, eperm),
        _jump(JEQ_K, SYS_SOCKETPAIR, 0, 4),                   # socketpair: AF_UNIX only
        _stmt(LD_W_ABS, 16),
        _jump(JEQ_K, AF_UNIX, 0, 1),
        _stmt(RET_K, RET_ALLOW),
        _stmt(RET_K, eacces),
        _stmt(RET_K, RET_ALLOW),
    ]
    return prog


class _SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


def install() -> None:
    """Install the filter on every thread of the calling process. Raises OSError on failure."""
    import platform

    if platform.machine() != "x86_64":
        raise OSError(errno.ENOTSUP, f"seccomp filter supports x86_64 only, not {platform.machine()}")
    libc = ctypes.CDLL(None, use_errno=True)
    prog = build_filter()
    buffer = ctypes.create_string_buffer(b"".join(prog))
    fprog = _SockFprog(len(prog), ctypes.cast(buffer, ctypes.c_void_p))
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        code = ctypes.get_errno()
        raise OSError(code, f"PR_SET_NO_NEW_PRIVS failed: {errno.errorcode.get(code)}")
    libc.syscall.restype = ctypes.c_long
    result = libc.syscall(ctypes.c_long(SYS_SECCOMP), ctypes.c_long(SECCOMP_SET_MODE_FILTER),
                          ctypes.c_long(SECCOMP_FILTER_FLAG_TSYNC), ctypes.byref(fprog))
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code or errno.EPERM, f"seccomp install failed (result {result}, {errno.errorcode.get(code)})")


def active_filters() -> int:
    for line in open("/proc/self/status"):
        if line.startswith("Seccomp_filters:"):
            return int(line.split(":", 1)[1])
    return 0
