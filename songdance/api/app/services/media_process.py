"""Bound media subprocess resources and output; this is not an OS security sandbox."""

import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_CAPTURE_BYTES = 64 * 1024


def run_media(command: list[str], timeout: float) -> str:
    helper = Path(__file__).with_name("_media_limits.py")
    # Media parsers have no reason to inherit application or cloud credentials.
    environment = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C"}
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [sys.executable, "-I", str(helper), *command],
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
