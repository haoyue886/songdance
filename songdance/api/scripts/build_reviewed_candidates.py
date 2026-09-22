"""Rebuild frozen reviewed candidates without changing models or approved scores."""

import argparse
import json
import shutil
from pathlib import Path

from app.pipeline.score_io import read_musicxml_structure
from scripts.piano_comparison_cases import ROOT, file_sha256
from scripts.revise_device_bass_notation import revise, timed_notes, treble_nodes

PROJECT_ROOT = ROOT.parents[1]
FEEDBACK = ROOT.parent / "docs/reviews/2026-09-16-transkun-teacher-feedback.json"


def build(output: Path, project: Path = PROJECT_ROOT, feedback: Path = FEEDBACK):
    reviews = json.loads(feedback.read_text())
    entries = {item["case_id"]: item for item in reviews["cases"]}
    sources = {}
    # Validate all inputs before writing any candidate.
    for case in ("07-soft", "10-device"):
        source = (project / entries[case]["candidate_path"]).resolve()
        if not source.is_relative_to(project.resolve()):
            raise ValueError("review input escaped project")
        if file_sha256(source) != entries[case]["candidate_sha256"]:
            raise ValueError(f"{case}: reviewed source changed")
        sources[case] = source
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "production_eligible": False,
        "status": "building",
        "model_policy": "Transkun research candidate; Basic Pitch production unchanged",
        "feedback_sha256": file_sha256(feedback),
        "builder_sha256": file_sha256(Path(__file__)),
        "revision_sha256": file_sha256(ROOT / "scripts/revise_device_bass_notation.py"),
        "musescore_validation": "not_run_no_headless_platform_plugin",
        "cases": [
            {
                "case_id": "06-sustain",
                "status": "blocked",
                "reason": "source and teacher chord reference need reconciliation",
            }
        ],
    }
    status = output / "manifest.json"
    try:
        for case in ("07-soft", "10-device"):
            folder = output / case
            folder.mkdir()
            target = folder / "score.musicxml"
            source = sources[case]
            changes = []
            if case == "07-soft":
                shutil.copyfile(source, target)
                state = "teacher_passed_reviewed_items_only"
            else:
                changes = revise(source, target)
                if timed_notes(source) != timed_notes(target) or treble_nodes(
                    source
                ) != treble_nodes(target):
                    raise ValueError("bass revision changed reviewed onsets or treble")
                state = "needs_teacher_review_and_missing_bass_fix"
            manifest["cases"].append(
                {
                    "case_id": case,
                    "status": state,
                    "source_sha256": file_sha256(source),
                    "score_sha256": file_sha256(target),
                    "path": str(target.relative_to(output)),
                    "changes": changes,
                    "structure": read_musicxml_structure(target),
                    "teacher_review_applies_to_source_only": True,
                }
            )
        manifest["status"] = "built_not_release_ready"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        raise
    finally:
        status.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


ACCEPTANCE = ROOT.parent / "docs/reviews/2026-09-16-accepted-candidates.json"


def build_accepted(output: Path, project: Path = PROJECT_ROOT, acceptance: Path = ACCEPTANCE):
    registry = json.loads(acceptance.read_text())
    if registry.get("production_eligible") is not False:
        raise ValueError("candidate acceptance cannot enable production")
    if {row["case_id"] for row in registry["cases"]} != {"06-sustain", "07-soft", "10-device"}:
        raise ValueError("unexpected accepted candidate set")
    verified = []
    for row in registry["cases"]:
        if row["status"] != "user_accepted_candidate":
            raise ValueError("candidate is not accepted")
        if set(row["files"]) != {"score.musicxml", "source.wav"}:
            raise ValueError("unexpected candidate artifacts")
        for name, artifact in row["files"].items():
            source = (project / artifact["path"]).resolve()
            if not source.is_relative_to(project.resolve()):
                raise ValueError("accepted artifact escaped project")
            if file_sha256(source) != artifact["sha256"]:
                raise ValueError(f"accepted artifact changed: {row['case_id']}/{name}")
            verified.append((row["case_id"], name, source, artifact["sha256"]))
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "production_eligible": False,
        "status": "building",
        "acceptance_sha256": file_sha256(acceptance),
        "builder_sha256": file_sha256(Path(__file__)),
        "acceptance_source": registry["confirmation_source"],
        "confirmation_text": registry["confirmation_text"],
        "musescore_validation": "user_acceptance_not_automated_validation",
        "cases": [],
    }
    try:
        for case, name, source, digest in verified:
            target = output / case / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
            if file_sha256(target) != digest:
                raise ValueError("copied artifact differs from accepted input")
        for row in registry["cases"]:
            case = row["case_id"]
            result["cases"].append(
                {
                    "case_id": case,
                    "status": row["status"],
                    "source_kind": row["source_kind"],
                    "known_limitations": row["known_limitations"],
                    "files": {
                        name: {"path": f"{case}/{name}", "sha256": artifact["sha256"]}
                        for name, artifact in row["files"].items()
                    },
                    "structure": read_musicxml_structure(output / case / "score.musicxml"),
                }
            )
        result["status"] = "accepted_candidates_frozen_not_production_release"
    except Exception as error:
        result.update(status="failed", error=str(error))
        raise
    finally:
        (output / "manifest.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("accepted", "historical"), default="accepted")
    args = parser.parse_args()
    result = build_accepted(args.output) if args.mode == "accepted" else build(args.output)
    print(result["status"])
