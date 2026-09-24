"""Create an offline annotation page beside existing pending clips."""

import argparse
import json
from pathlib import Path

from scripts.piano_comparison_cases import file_sha256


def build(directory: Path) -> Path:
    manifest = json.loads((directory / "manifest.json").read_text())
    labels = json.loads((directory / "labels.json").read_text())
    if labels["manifest_sha256"] != file_sha256(directory / "manifest.json"):
        raise ValueError("manifest binding changed")
    for row in manifest["candidates"]:
        path = (directory / row["clip_file"]).resolve()
        if not path.is_relative_to(directory.resolve()) or file_sha256(path) != row["clip_sha256"]:
            raise ValueError("clip binding changed")
    payload = json.dumps({"manifest": manifest, "initial": labels}, ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    template = Path(__file__).with_name("templates").joinpath("repeat_annotations.html").read_text()
    target = directory / "index.html"
    with target.open("x") as f:
        f.write(template.replace("__DATA__", payload))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(build(parser.parse_args().directory))
