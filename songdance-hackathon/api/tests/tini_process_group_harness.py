import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.pipeline.youtube import _run_command


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        pid_file = Path(raw) / "processes.pid"
        script = (
            "import os, subprocess, sys, time; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "open(sys.argv[1], 'w').write(f'{os.getpid()} {child.pid}'); "
            "time.sleep(60)"
        )
        try:
            _run_command([sys.executable, "-c", script, str(pid_file)], 0.5)
        except subprocess.TimeoutExpired:
            pass
        else:
            raise AssertionError("controlled process must time out")

        parent_pid, child_pid = (int(value) for value in pid_file.read_text().split())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(
            Path(f"/proc/{pid}").exists() for pid in (parent_pid, child_pid)
        ):
            time.sleep(0.05)
        remaining = [pid for pid in (parent_pid, child_pid) if Path(f"/proc/{pid}").exists()]
        if remaining:
            states = {
                pid: Path(f"/proc/{pid}/status").read_text().splitlines()[:8] for pid in remaining
            }
            raise AssertionError(f"processes were not reaped: {states}")
        print(f"reaped parent={parent_pid} child={child_pid} pid1={os.getppid()}")


if __name__ == "__main__":
    main()
