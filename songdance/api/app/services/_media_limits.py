"""Apply limits in a fresh interpreter, never preexec_fn in an API worker thread."""

import os
import resource
import shutil
import sys


def main() -> None:
    tool, *arguments = sys.argv[1:]
    if tool not in {"ffprobe", "ffmpeg"}:
        raise ValueError("Unsupported media executable")
    executable = shutil.which(tool)
    if executable is None:
        raise FileNotFoundError(tool)
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
    os.execv(executable, [executable, *arguments])


if __name__ == "__main__":
    main()
