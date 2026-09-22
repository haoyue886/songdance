"""Rebuild review fixtures in a new directory without transferring human ratings."""

import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from scripts import run_human_regression as human
from scripts import run_structure_review as structure
from scripts.human_quality_gate import file_sha256
from scripts.structure_quality_gate import bind_structure_suite

SOURCE = Path(__file__).resolve().parents[1] / "tests/fixtures/audio"


def run(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    originals = {
        name: file_sha256(SOURCE / name) for name in ("human-review.json", "structure-review.json")
    }
    state = {
        "status": "running",
        "production_eligible": False,
        "old_review_sha256": originals,
        "script_sha256": file_sha256(Path(__file__)),
        "stage": "prepare",
    }

    def save():
        (output / "rebuild.json").write_text(json.dumps(state, indent=2) + "\n")

    save()
    try:
        for name in ("manifest.json", "human-manifest.json", "human-provenance.json"):
            shutil.copyfile(SOURCE / name, output / name)
        for name in ("generated", "human-generated"):
            shutil.copytree(SOURCE / name, output / name)
        state["stage"] = "structure"
        save()

        def bind(counts, parsers):
            return bind_structure_suite(counts, parsers, output / "structure-review.json", output)

        with patch.multiple(
            structure,
            MANIFEST_PATH=output / "manifest.json",
            OUTPUT_DIR=output / "generated",
            ARTIFACT_ROOT=output / "structure-review-artifacts",
            REVIEW_PATH=output / "structure-review.json",
            bind_structure_suite=bind,
        ):
            structure.run()
        state["stage"] = "human"
        save()
        with patch.multiple(
            human,
            FIXTURE_ROOT=output,
            OUTPUT_DIR=output / "human-generated",
            REVIEW_DIR=output / "human-review-artifacts",
            REVIEW_PATH=output / "human-review.json",
        ):
            human.run()
        for name, digest in originals.items():
            if file_sha256(SOURCE / name) != digest:
                raise ValueError("original review unexpectedly changed")
        state.update(
            status="complete_pending_review",
            stage="complete",
            new_review_sha256={name: file_sha256(output / name) for name in originals},
        )
    except Exception as error:
        state.update(status="failed", error=str(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
