"""Exercise the runner with isolated repositories and observable fake tools."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "check.py"
FAKE = '''import json, os, sys
from pathlib import Path
record = {"tool": Path(sys.argv[0]).name, "argv": sys.argv[1:], "cwd": os.getcwd()}
with open(os.environ["CHECK_LOG"], "a") as stream:
    stream.write(json.dumps(record) + "\\n")
print("child stdout", flush=True)
print("child stderr", file=sys.stderr, flush=True)
sys.exit(23 if sys.argv[1:] == json.loads(os.environ.get("FAIL_ARGS", "null")) else 0)
'''
HARNESS = '''import json, os, unittest
class FixtureCheck(unittest.TestCase):
    def test_record(self):
        with open(os.environ["CHECK_LOG"], "a") as stream:
            stream.write(json.dumps({"tool": "harness", "argv": [], "cwd": os.getcwd()}) + "\\n")
'''


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "repo with spaces; touch SHELL_WAS_USED"
        self.script = self.root / ".codex/scripts/check.py"
        tests = self.script.parent / "tests"
        tests.mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.script)
        (tests / "test_fixture.py").write_text(HARNESS)
        self.web = self.root / "songdance/web"
        self.api = self.root / "songdance/api"
        self.web.mkdir(parents=True)
        (self.web / "package.json").write_text("{}")
        (self.api / "app").mkdir(parents=True)
        (self.api / "tests").mkdir()
        (self.api / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
        self.bin = self.base / "bin"
        self.bin.mkdir()
        for executable in (self.bin / "pnpm", self.api / ".venv/bin/python"):
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text(f"#!{sys.executable}\n" + FAKE)
            executable.chmod(0o755)
        self.log = self.base / "calls.jsonl"
        self.env = {**os.environ, "PATH": str(self.bin), "CHECK_LOG": str(self.log)}
        self.env.pop("FAIL_ARGS", None)

    def run_check(self, *args, **environment):
        return subprocess.run([sys.executable, str(self.script), *args], cwd=self.base,
                              env={**self.env, **environment}, text=True, capture_output=True)

    def records(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_full_order_and_cwd_from_another_directory(self):
        result = self.run_check("full")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self.records()
        self.assertEqual([row["argv"] for row in records], [[], ["lint"], ["typecheck"],
                         ["test"], ["build"], ["-m", "ruff", "check", "app", "tests"],
                         ["-m", "pytest"]])
        self.assertEqual([row["cwd"] for row in records],
                         [str(self.root)] + [str(self.web)] * 4 + [str(self.api)] * 2)
        self.assertIn("child stdout", result.stdout)
        self.assertIn("child stderr", result.stderr)
        self.assertFalse((self.base / "SHELL_WAS_USED").exists())

    def test_default_and_e2e_are_separate(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["tool"] for row in self.records()], ["harness"])
        self.log.unlink()
        result = self.run_check("e2e")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["argv"] for row in self.records()], [["test:e2e"]])

    def test_failure_stops_remaining_checks(self):
        result = self.run_check("full", FAIL_ARGS='["typecheck"]')
        self.assertEqual(result.returncode, 23)
        self.assertEqual([row["argv"] for row in self.records()], [[], ["lint"], ["typecheck"]])

    def test_empty_or_testless_suite_fails_without_running_product_checks(self):
        fixture = self.script.parent / "tests/test_fixture.py"
        for source in (None, "VALUE = 1\n"):
            with self.subTest(source=source):
                if source is None:
                    fixture.unlink()
                else:
                    fixture.write_text(source)
                result = self.run_check("full")
                self.assertEqual(result.returncode, 2)
                self.assertIn("no harness tests discovered", result.stderr)
                self.assertEqual(self.records(), [])

    def test_failed_harness_test_stops_product_checks(self):
        fixture = self.script.parent / "tests/test_fixture.py"
        fixture.write_text("import unittest\nclass Broken(unittest.TestCase):\n"
                           "    def test_failure(self):\n        self.fail('fixture failure')\n")
        result = self.run_check("full")
        self.assertEqual(result.returncode, 1)
        self.assertIn("fixture failure", result.stderr)
        self.assertEqual(self.records(), [])

    def test_missing_tools_and_paths_fail_before_execution(self):
        cases = [(self.bin / "pnpm", "web"), (self.api / ".venv/bin/python", "api"),
                 (self.web / "package.json", "web"), (self.api / "tests", "api"),
                 (self.script.parent / "tests", "harness")]
        for path, profile in cases:
            with self.subTest(path=path):
                backup = path.with_name(path.name + ".saved")
                path.rename(backup)
                try:
                    for options in ((), ("--dry-run",)):
                        result = self.run_check(profile, *options)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("missing", result.stderr)
                        self.assertEqual(self.records(), [])
                finally:
                    backup.rename(path)

    def test_dry_run_prints_complete_plan_without_execution(self):
        result = self.run_check("full", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(plan), 7)
        self.assertTrue(all(Path(row["cwd"]).is_absolute() for row in plan))
        self.assertEqual(plan[0]["argv"][1], "-c")
        self.assertEqual(len(plan[0]["argv"]), 3)
        self.assertFalse(self.log.exists())

    def test_only_fixed_commands_are_invoked_without_shell_or_network(self):
        spec = importlib.util.spec_from_file_location("check_runner", self.script)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with patch.dict(os.environ, self.env), patch("builtins.print"), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch.object(runner.subprocess, "run") as execute:
            execute.return_value.returncode = 0
            self.assertEqual(runner.main(["full"]), 0)
        self.assertEqual(len(execute.call_args_list), 7)
        self.assertEqual([call.args[0][1:] for call in execute.call_args_list], [
            ["-c", runner.HARNESS_RUNNER],
            ["lint"], ["typecheck"], ["test"], ["build"],
            ["-m", "ruff", "check", "app", "tests"], ["-m", "pytest"],
        ])
        for call in execute.call_args_list:
            self.assertIsInstance(call.args[0], list)
            self.assertEqual(set(call.kwargs), {"cwd", "shell"})
            self.assertIs(call.kwargs["shell"], False)

    def test_invalid_profile_does_not_execute(self):
        result = self.run_check("web; touch SHELL_WAS_USED")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.records(), [])


if __name__ == "__main__":
    unittest.main()
