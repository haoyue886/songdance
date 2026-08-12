import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
OSMD_VALIDATOR = WEB_ROOT / "scripts/validate-musicxml.mjs"


def validate_external_parsers(paths: list[Path]) -> dict[str, dict[str, object]]:
    resolved = [path.resolve() for path in paths]
    xml_results = {str(path): _validate_xmllint(path) for path in resolved}
    osmd_results = _validate_osmd(resolved)
    return {
        str(path): {
            "xmllint": xml_results[str(path)],
            "osmd": osmd_results[str(path)],
        }
        for path in resolved
    }


def _validate_xmllint(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["xmllint", "--noout", str(path)],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "error": completed.stderr.strip() or None,
    }


def _validate_osmd(paths: list[Path]) -> dict[str, dict[str, object]]:
    completed = subprocess.run(
        ["node", str(OSMD_VALIDATOR), *(str(path) for path in paths)],
        cwd=WEB_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=max(30, 10 * len(paths)),
    )
    if completed.returncode != 0:
        error = completed.stderr.strip() or "OSMD validation failed"
        return {str(path): {"status": "failed", "error": error} for path in paths}
    payload = json.loads(completed.stdout)
    return {str(path): payload[str(path)] for path in paths}
