"""Verify a downloaded fixed GitHub archive against its Git tree before importing code."""

import argparse
import hashlib
import json
import tarfile
from pathlib import Path

COMMIT = "c5cb8370e17b4a1650b5971ba87ee4b0d208e5b6"
REPOSITORY = "https://github.com/Yujia-Yan/Transkun"
WEIGHT = "transkun/pretrained/2.0.pt"
CONFIG = "transkun/pretrained/2.0.conf"


def verify(archive_path: Path, tree_path: Path, output: Path, manifest_path: Path) -> dict:
    tree = json.loads(tree_path.read_text())
    if tree.get("sha") != COMMIT:
        raise ValueError("Git tree response must be fetched using the pinned commit")
    if tree.get("truncated"):
        raise ValueError("source tree must not be truncated")
    expected = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
    output.mkdir(parents=True, exist_ok=True)
    digests = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            relative = "/".join(member.name.split("/")[1:])
            if member.isdir() or not relative:
                continue
            if not member.isfile() or relative not in expected:
                raise ValueError(f"unexpected archive member: {relative}")
            destination = (output / relative).resolve()
            if not destination.is_relative_to(output.resolve()):
                raise ValueError("source path escapes output")
            data = archive.extractfile(member).read()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blob != expected[relative]["sha"] or len(data) != expected[relative]["size"]:
                raise ValueError(f"Git blob verification failed: {relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            digests[relative] = hashlib.sha256(data).hexdigest()
    if set(digests) != set(expected):
        raise ValueError("archive missing files from pinned tree")
    if not (output / "LICENSE").read_text().startswith("MIT License"):
        raise ValueError("unexpected upstream license")
    report = {
        "source_repository": REPOSITORY,
        "source_commit": COMMIT,
        "source_tree_sha": tree["sha"],
        "source_license": "MIT",
        "license_evidence_url": f"{REPOSITORY}/blob/{COMMIT}/LICENSE",
        "readme_evidence_url": f"{REPOSITORY}/blob/{COMMIT}/README.md",
        "checkpoint_description": "upstream default V2 No Pedal Extension",
        "weight_git_blob_sha1": expected[WEIGHT]["sha"],
        "weight_size_bytes": expected[WEIGHT]["size"],
        "weight_sha256": digests[WEIGHT],
        "config_sha256": digests[CONFIG],
        "source_files_sha256": {p: sha for p, sha in digests.items() if p != WEIGHT},
        "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "status": "offline_evaluation_only",
        "production_eligible": False,
        "license_scope": "repository MIT verified; commercial weight/data audit pending",
        "training_provenance": "upstream: MAESTRO with augmentation; deployment not approved",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps({k: report[k] for k in ("source_commit", "weight_sha256", "weight_size_bytes")})
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    verify(args.archive, args.tree, args.output, args.manifest)
