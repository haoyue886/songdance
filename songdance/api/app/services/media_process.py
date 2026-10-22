"""Bound media subprocess resources and restrict its Linux file and socket access."""

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_CAPTURE_BYTES = 64 * 1024


def run_media(
    command: list[str],
    timeout: float,
    *,
    readable_paths: tuple[Path, ...] = (),
    writable_paths: tuple[Path, ...] = (),
) -> str:
    helper = Path(__file__).with_name("_media_limits.py")
    resolved_readable = [str(path.resolve(strict=True)) for path in readable_paths]
    resolved_writable = []
    for path in writable_paths:
        target = path.parent.resolve(strict=True) / path.name
        descriptor = os.open(
            target,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(descriptor)
        resolved_writable.append(str(target))
    # Media parsers have no reason to inherit application or cloud credentials.
    environment = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C"}
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                str(helper),
                command[0],
                json.dumps(resolved_readable),
                json.dumps(resolved_writable),
                *command[1:],
            ],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=errors,
            env=environment,
            start_new_session=True,
        )
        try:
            process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command[0])
        output.seek(0)
        payload = output.read(MAX_CAPTURE_BYTES + 1)
        if len(payload) > MAX_CAPTURE_BYTES:
            raise subprocess.SubprocessError("Media output exceeded limit")
    return payload.decode("utf-8")
