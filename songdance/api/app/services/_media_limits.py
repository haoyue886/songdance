"""Apply resource limits and Landlock before replacing this helper with FFmpeg."""

import ctypes
import errno
import json
import os
import platform
import resource
import shutil
import sys
from pathlib import Path

LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0
LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3
LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14
LANDLOCK_ACCESS_NET_BIND_TCP = 1 << 0
LANDLOCK_ACCESS_NET_CONNECT_TCP = 1 << 1
PR_SET_NO_NEW_PRIVS = 38
O_PATH = 0x200000
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_KILL_PROCESS = 0x80000000
BPF_LD_W_ABS = 0x20
BPF_JMP_JEQ_K = 0x15
BPF_JMP_JSET_K = 0x45
BPF_RET_K = 0x06


class SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_uint16),
        ("jt", ctypes.c_uint8),
        ("jf", ctypes.c_uint8),
        ("k", ctypes.c_uint32),
    ]


class SockFprog(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint16), ("filter", ctypes.POINTER(SockFilter))]


class RulesetAttr(ctypes.Structure):
    _fields_ = [
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    ]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def _syscall(libc, number: int, *arguments: object) -> int:
    result = libc.syscall(number, *arguments)
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return result


def _add_path_rule(libc, ruleset_fd: int, path: Path, access: int) -> None:
    descriptor = os.open(path, O_PATH | os.O_CLOEXEC)
    try:
        rule = PathBeneathAttr(access, descriptor)
        _syscall(libc, 445, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(rule), 0)
    finally:
        os.close(descriptor)


def _allow_path(libc, ruleset_fd: int, path: Path, access: int) -> None:
    resolved = path.resolve(strict=True)
    _add_path_rule(libc, ruleset_fd, resolved, access)


def _install_no_socket_filter(libc) -> None:
    machine = platform.machine()
    if machine == "aarch64":
        audit_arch, socket_syscalls = 0xC00000B7, (198, 199)
        ioctl_syscall, ptrace_syscall = 29, 117
        # set/lset/fsetxattr, remove/lremove/fremovexattr, fchmod/fchmodat,
        # fchownat/fchown, utimensat.
        metadata_syscalls = (5, 6, 7, 14, 15, 16, 52, 53, 54, 55, 88)
    elif machine == "x86_64":
        audit_arch, socket_syscalls = 0xC000003E, (41, 53)
        ioctl_syscall, ptrace_syscall = 16, 101
        # chmod/fchmod, chown/fchown/lchown, utime, set/remove xattr variants,
        # utimes, fchownat/futimesat/fchmodat, utimensat.
        metadata_syscalls = (
            90,
            91,
            92,
            93,
            94,
            132,
            188,
            189,
            190,
            197,
            198,
            199,
            235,
            260,
            261,
            268,
            280,
        )
    else:
        raise OSError(errno.ENOTSUP, "Unsupported architecture for media seccomp policy")

    instructions = [
        SockFilter(BPF_LD_W_ABS, 0, 0, 4),
        SockFilter(BPF_JMP_JEQ_K, 1, 0, audit_arch),
        SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
        SockFilter(BPF_LD_W_ABS, 0, 0, 0),
    ]
    if machine == "x86_64":
        instructions.extend(
            [
                SockFilter(BPF_JMP_JSET_K, 0, 1, 0x40000000),
                SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
            ]
        )
    # Python's script loader needs close-on-exec descriptor flags, not inode ioctls.
    instructions.extend(
        [
            SockFilter(BPF_JMP_JEQ_K, 0, 5, ioctl_syscall),
            SockFilter(BPF_LD_W_ABS, 0, 0, 24),
            SockFilter(BPF_JMP_JEQ_K, 2, 0, 0x5451),  # FIOCLEX
            SockFilter(BPF_JMP_JEQ_K, 1, 0, 0x5450),  # FIONCLEX
            SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM),
            SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW),
            SockFilter(BPF_LD_W_ABS, 0, 0, 0),
        ]
    )
    # io_uring can create sockets too; pidfd_getfd can import another process's socket.
    # Metadata APIs (including file_setattr) and ioctl attributes need separate denial.
    denied_syscalls = (
        *socket_syscalls,
        *metadata_syscalls,
        ptrace_syscall,
        425,
        426,
        427,
        438,
        452,
        463,
        466,
        469,
    )
    for syscall_number in denied_syscalls:
        instructions.extend(
            [
                SockFilter(BPF_JMP_JEQ_K, 0, 1, syscall_number),
                SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM),
            ]
        )
    instructions.append(SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW))
    filters = (SockFilter * len(instructions))(*instructions)
    program = SockFprog(len(instructions), filters)
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(program)) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _restrict_media_access(tool_path: Path, readable: list[str], writable: list[str]) -> None:
    if platform.machine() not in {"aarch64", "x86_64"}:
        raise OSError(errno.ENOTSUP, "Unsupported architecture for media isolation")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    abi = _syscall(
        libc,
        444,
        ctypes.c_void_p(),
        0,
        LANDLOCK_CREATE_RULESET_VERSION,
    )
    if abi < 4:
        raise OSError(errno.ENOTSUP, "Landlock ABI 4 is required for media isolation")

    handled_fs = (1 << 13) - 1
    if abi >= 2:
        handled_fs |= 1 << 13
    if abi >= 3:
        handled_fs |= LANDLOCK_ACCESS_FS_TRUNCATE
    if abi >= 5:
        handled_fs |= 1 << 15
    ruleset_attr = RulesetAttr(
        handled_access_fs=handled_fs,
        handled_access_net=LANDLOCK_ACCESS_NET_BIND_TCP | LANDLOCK_ACCESS_NET_CONNECT_TCP,
    )
    ruleset_fd = _syscall(libc, 444, ctypes.byref(ruleset_attr), ctypes.sizeof(ruleset_attr), 0)
    try:
        read_access = (
            LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
        )
        for runtime_path in (Path("/usr"), Path("/lib"), Path("/lib64")):
            if runtime_path.exists():
                _add_path_rule(libc, ruleset_fd, runtime_path, read_access)
        for runtime_file in (Path("/etc/ld.so.cache"), Path("/etc/localtime")):
            if runtime_file.is_file():
                _allow_path(libc, ruleset_fd, runtime_file, LANDLOCK_ACCESS_FS_READ_FILE)
        ffmpeg_config = Path("/etc/ffmpeg")
        if ffmpeg_config.is_dir():
            _add_path_rule(libc, ruleset_fd, ffmpeg_config, read_access)

        _allow_path(
            libc,
            ruleset_fd,
            tool_path,
            LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE,
        )
        for path in readable:
            _allow_path(libc, ruleset_fd, Path(path), LANDLOCK_ACCESS_FS_READ_FILE)
        for path in writable:
            _allow_path(
                libc,
                ruleset_fd,
                Path(path),
                LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_TRUNCATE,
            )

        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        _syscall(libc, 446, ruleset_fd, 0)
        _install_no_socket_filter(libc)
    finally:
        os.close(ruleset_fd)


def main() -> None:
    tool, readable_json, writable_json, *arguments = sys.argv[1:]
    if tool not in {"ffprobe", "ffmpeg"}:
        raise ValueError("Unsupported media executable")
    executable = shutil.which(tool)
    if executable is None:
        raise FileNotFoundError(tool)
    executable_path = Path(executable).resolve(strict=True)
    cpu_seconds = 10 if tool == "ffprobe" else 60
    file_bytes = 512 * 1024 if tool == "ffprobe" else 16 * 1024 * 1024
    limits = [
        (resource.RLIMIT_CPU, cpu_seconds),
        (resource.RLIMIT_FSIZE, file_bytes),
        (resource.RLIMIT_NOFILE, 64),
        (resource.RLIMIT_CORE, 0),
    ]
    # macOS rejects stack hard-limit changes and lacks Linux address-space enforcement.
    if sys.platform == "linux":
        limits += [
            (resource.RLIMIT_AS, 512 * 1024 * 1024),
            (resource.RLIMIT_STACK, 8 * 1024 * 1024),
        ]
    for kind, limit in limits:
        inherited = resource.getrlimit(kind)
        limit = min([limit, *(value for value in inherited if value != resource.RLIM_INFINITY)])
        resource.setrlimit(kind, (limit, limit))
    if sys.platform == "linux":
        _restrict_media_access(
            executable_path, json.loads(readable_json), json.loads(writable_json)
        )
    os.execv(str(executable_path), [str(executable_path), *arguments])


if __name__ == "__main__":
    main()
