#!/usr/bin/env python3
"""Run explicit local checks. Requires Python 3.11+; never installs dependencies."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
PROFILES = {
    "harness": ("harness",),
    "web": ("web",),
    "api": ("api",),
    "full": ("harness", "web", "api"),
    "e2e": ("e2e",),
}
HARNESS_RUNNER = """import sys, unittest
suite = unittest.defaultTestLoader.discover('.codex/scripts/tests', pattern='test_*.py')
if suite.countTestCases() == 0:
    print('ERROR: no harness tests discovered', file=sys.stderr)
    sys.exit(2)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""


def build_plan(profile):
    """Return ordered (working directory, argv) pairs and required paths."""
    commands, required = [], []
    for group in PROFILES[profile]:
        if group == "harness":
            required.append((ROOT / ".codex/scripts/tests", True))
            commands.append((ROOT, [sys.executable, "-c", HARNESS_RUNNER]))
        elif group in ("web", "e2e"):
            cwd = ROOT / "songdance/web"
            required.extend([(cwd, True), (cwd / "package.json", False)])
            scripts = ("test:e2e",) if group == "e2e" else ("lint", "typecheck", "test", "build")
            commands.extend((cwd, ["pnpm", script]) for script in scripts)
        else:
            cwd = ROOT / "songdance/api"
            required.extend([(cwd, True), (cwd / "pyproject.toml", False),
                             (cwd / "app", True), (cwd / "tests", True)])
            python = str(cwd / ".venv/bin/python")
            commands.extend([(cwd, [python, "-m", "ruff", "check", "app", "tests"]),
                             (cwd, [python, "-m", "pytest"])])
    return commands, required


def main(argv=None):
    if sys.version_info < (3, 11):
        print("ERROR: Python 3.11 or newer is required.", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", choices=PROFILES, default="harness",
                        help="default: harness; full = harness + web + api (excludes e2e)")
    parser.add_argument("--dry-run", action="store_true", help="validate and print; do not execute")
    args = parser.parse_args(argv)
    commands, required = build_plan(args.profile)
    for path, is_directory in required:
        exists = path.is_dir() if is_directory else path.is_file()
        if not exists:
            kind = "directory" if is_directory else "file"
            print(f"ERROR: required {kind} is missing: {path}", file=sys.stderr)
            return 2
    for _, command in commands:
        executable = command[0]
        if not shutil.which(executable):
            print(f"ERROR: executable is missing or not executable: {executable}", file=sys.stderr)
            return 2
    for cwd, command in commands:
        print(json.dumps({"cwd": str(cwd), "argv": command}, ensure_ascii=False), flush=True)
        if args.dry_run:
            continue
        try:
            result = subprocess.run(command, cwd=cwd, shell=False)
        except OSError as error:
            print(f"ERROR: could not execute {command[0]}: {error}", file=sys.stderr)
            return 2
        if result.returncode:
            print(f"ERROR: check failed with exit code {result.returncode}", file=sys.stderr)
            return result.returncode if result.returncode > 0 else 128 - result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
