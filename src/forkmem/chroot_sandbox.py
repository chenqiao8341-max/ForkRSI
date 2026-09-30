"""Chroot, unprivileged UID and seccomp for namespace-restricted containers."""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

CACHE = Path("/root/autodl-tmp/forkrsi-sandbox")
SYSTEM_PYTHON = Path("/usr/bin/python3")
INNER = r"""
import ctypes, errno, os, runpy
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(38, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
sec = ctypes.CDLL("libseccomp.so.2", use_errno=True)
sec.seccomp_init.argtypes = [ctypes.c_uint32]
sec.seccomp_init.restype = ctypes.c_void_p
sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
sec.seccomp_syscall_resolve_name.restype = ctypes.c_int
sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
sec.seccomp_rule_add.restype = ctypes.c_int
sec.seccomp_load.argtypes = [ctypes.c_void_p]
sec.seccomp_load.restype = ctypes.c_int
sec.seccomp_release.argtypes = [ctypes.c_void_p]
context = sec.seccomp_init(0x7fff0000)
if not context:
    raise RuntimeError("seccomp initialization failed")
blocked = ("bind listen accept accept4 sendmsg sendmmsg "
           "fork vfork clone clone3 execve execveat ptrace process_vm_readv "
           "process_vm_writev mount umount2 pivot_root chroot unshare setns "
           "open_by_handle_at bpf perf_event_open keyctl").split()
for name in blocked:
    number = sec.seccomp_syscall_resolve_name(name.encode())
    if number >= 0 and sec.seccomp_rule_add(context, 0x50000 | errno.EPERM, number, 0) != 0:
        raise RuntimeError("seccomp rule failed: " + name)
# Unix socket pairs and destination-free sends support asyncio self-pipes.
# All external connect/bind and sends with an explicit destination stay denied.
class Argument(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]
sec.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
    ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Argument)]
sec.seccomp_rule_add_array.restype = ctypes.c_int
for name, argument, permitted in ((b"socketpair", 0, 1), (b"sendto", 4, 0)):
    number = sec.seccomp_syscall_resolve_name(name)
    condition = Argument(argument, 1, permitted, 0)  # SCMP_CMP_NE
    if sec.seccomp_rule_add_array(context, 0x50000 | errno.EPERM,
                                  number, 1, ctypes.byref(condition)) != 0:
        raise RuntimeError("seccomp argument rule failed")
connect_nr = sec.seccomp_syscall_resolve_name(b"connect")
if sec.seccomp_rule_add(context, 0x50000 | errno.ECONNREFUSED, connect_nr, 0) != 0:
    raise RuntimeError("seccomp connect rule failed")
if sec.seccomp_load(context) != 0:
    raise RuntimeError("seccomp load failed")
sec.seccomp_release(context)
os.chdir("/task")
runpy.run_path("/guard.py", run_name="__main__")
"""


def copy_readonly(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o555 if os.access(source, os.X_OK) else 0o444)


def dependencies(path: Path) -> list[Path]:
    result = subprocess.run(
        ["ldd", str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode:
        return []
    return [Path(p) for p in re.findall(r"(?:=>\s+)?(/[^\s()]+)", result.stdout)]


def prepare_cache() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    CACHE.chmod(0o700)
    with (CACHE / "build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        base = CACHE / "rootfs"
        stamp = hashlib.sha256(INNER.encode()).hexdigest()
        if (base / "READY").is_file() and (base / "READY").read_text().strip() == stamp:
            return base
        if base.exists():
            shutil.rmtree(base)
        base.mkdir()
        copy_readonly(SYSTEM_PYTHON, base / "usr/bin/python3")
        stdlib = Path(
            subprocess.check_output(
                [
                    str(SYSTEM_PYTHON),
                    "-c",
                    "import sysconfig; print(sysconfig.get_path('stdlib'))",
                ],
                text=True,
            ).strip()
        )
        target = base / str(stdlib).lstrip("/")
        shutil.copytree(
            stdlib,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "dist-packages"),
        )
        objects = [SYSTEM_PYTHON, *stdlib.rglob("*.so")]
        extra = Path("/lib/x86_64-linux-gnu/libseccomp.so.2")
        if not extra.is_file():
            raise RuntimeError("libseccomp.so.2 is required")
        objects.append(extra)
        needed = set(objects[1:])
        for obj in objects:
            needed.update(dependencies(obj))
        for source in sorted(needed):
            dest = base / str(source).lstrip("/")
            if not dest.is_file():
                copy_readonly(source, dest)
        (base / "runner.py").write_text(INNER)
        for path in base.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
            elif path.is_file():
                path.chmod(0o555 if os.access(path, os.X_OK) else 0o444)
        (base / "READY").write_text(stamp + "\n")
        return base


def parse_args(args: list[str]) -> tuple[list[tuple[Path, str]], dict[str, str]]:
    bindings: list[tuple[Path, str]] = []
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in {"--unshare-all", "--die-with-parent", "--new-session"}:
            i += 1
        elif flag == "--setenv":
            env[args[i + 1]] = args[i + 2]
            i += 3
        elif flag == "--ro-bind":
            source, target = Path(args[i + 1]), args[i + 2]
            if target not in {"/usr", "/lib", "/lib64"}:
                if target not in {
                    "/verifier.py",
                    "/guard.py",
                } and not target.startswith("/task/"):
                    raise ValueError("unsupported bind target: " + target)
                bindings.append((source, target))
            i += 3
        elif flag in {"--proc", "--dev", "--tmpfs", "--dir"}:
            expected = {
                "--proc": "/proc",
                "--dev": "/dev",
                "--tmpfs": "/tmp",
                "--dir": "/task",
            }[flag]
            if args[i + 1] != expected:
                raise ValueError("unsupported mount/directory")
            i += 2
        elif flag == "--chdir":
            if args[i + 1 :] != ["/task", "/usr/bin/python3", "-B", "/guard.py"]:
                raise ValueError("unsupported sandbox command")
            break
        else:
            raise ValueError("unsupported sandbox flag: " + flag)
    else:
        raise ValueError("missing sandbox command")
    if not {"/guard.py", "/verifier.py"} <= {t for _, t in bindings}:
        raise ValueError("missing immutable verifier/guard")
    return bindings, env


def main(args: list[str]) -> int:
    if os.geteuid() != 0:
        raise RuntimeError("chroot-seccomp backend requires privileged launcher")
    bindings, env = parse_args(args)
    base = prepare_cache()
    root = Path(tempfile.mkdtemp(prefix="run-", dir=CACHE))
    try:
        shutil.copytree(base, root, dirs_exist_ok=True, copy_function=os.link)
        root.chmod(0o755)
        for source, target in bindings:
            relative = Path(target).relative_to("/")
            if ".." in relative.parts:
                raise ValueError("unsafe sandbox target")
            copy_readonly(source, root / relative)
        for name in ("task", "tmp", "dev"):
            (root / name).mkdir(exist_ok=True)
            (root / name).chmod(0o1777 if name == "tmp" else 0o755)
        os.mknod(root / "dev/null", stat.S_IFCHR | 0o666, os.makedev(1, 3))
        (root / "dev/null").chmod(0o666)
        pid = os.fork()
        if pid == 0:
            try:
                parent = os.getppid()
                libc = ctypes.CDLL(None, use_errno=True)
                if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
                    raise OSError(ctypes.get_errno(), "PR_SET_PDEATHSIG")
                if os.getppid() != parent:
                    os._exit(126)
                os.chroot(root)
                os.chdir("/task")
                os.setgroups([])
                os.setgid(65534)
                os.setuid(65534)
                os.execve(
                    "/usr/bin/python3", ["/usr/bin/python3", "-B", "/runner.py"], env
                )
            except BaseException as exc:  # noqa: BLE001 -- infrastructure failure must be identified
                import traceback

                print(
                    "bwrap: chroot-seccomp child infrastructure failure: " + repr(exc),
                    file=sys.stderr,
                    flush=True,
                )
                traceback.print_exc()
                os._exit(126)
        _, status = os.waitpid(pid, 0)
        result = os.waitstatus_to_exitcode(status)
        return result if result >= 0 else 128 - result
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BaseException as exc:
        if isinstance(exc, SystemExit):
            raise
        print(
            "bwrap: chroot-seccomp infrastructure failure: " + repr(exc),
            file=sys.stderr,
        )
        sys.exit(126)
