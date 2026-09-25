"""Configuration smoke tests; frontmatter checks intentionally are not full YAML parsing."""

import json
from pathlib import Path
import re
import tempfile
import tomllib
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[3]
LEGACY_HOOKS = {
    "auto-push.sh", "check-evolution.sh", "detect-feedback-signal.sh",
    "mark-review-needed.sh", "pre-tool-shell.sh", "stop-gate.sh",
}


def basic_frontmatter(text):
    """Check required single-line scalars; optional fields need strict YAML validation."""
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        raise ValueError("missing delimited frontmatter")
    fields = {}
    for line in match[1].splitlines():
        entry = re.fullmatch(r"(name|description):\s*(.*)", line)
        if not entry:
            continue
        if entry[1] in fields:
            raise ValueError("required fields must be unique")
        key, value = entry.groups()
        if not value.strip():
            raise ValueError("required fields must be nonempty")
        if value.startswith('"'):
            value = json.loads(value)
        elif value.startswith("'"):
            if not re.fullmatch(r"'(?:[^']|'')*'", value):
                raise ValueError("invalid single-quoted scalar")
            value = value[1:-1].replace("''", "'")
        elif value[0] in "[{&*!|>":
            raise ValueError("only simple scalar frontmatter is supported")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("frontmatter fields must be nonempty strings")
        fields[key] = value.strip()
    if set(fields) != {"name", "description"}:
        raise ValueError("frontmatter requires name and description")
    return fields


def missing_markdown_references(document, skill_root):
    """Check Markdown links and explicit skill-resource paths; ignore placeholders."""
    text = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"), flags=re.DOTALL)
    linked = re.findall(r"\[[^\]\n]+\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)", text)
    bare = re.findall(r"(?<![\w/-])(?:references|templates|assets|examples)/[A-Za-z0-9_./-]+\.md", text)
    missing = []
    for target in sorted(set(linked + bare)):
        if any(marker in target for marker in ("{", "}", "[", "]", "<", ">", "*", "$")):
            continue
        parsed = urlsplit(target)
        path = unquote(parsed.path)
        if parsed.scheme or parsed.netloc or not path or path.startswith("/"):
            continue
        if not path.lower().endswith(".md"):
            continue
        # Links resolve beside the document; bare resources are relative to SKILL.md.
        base = document.parent if target in linked else skill_root
        if not (base / path).is_file():
            missing.append(target)
    return missing


class ConfigurationTests(unittest.TestCase):
    def test_json_toml_and_empty_hook_configuration(self):
        configs = sorted((ROOT / ".codex").rglob("*.json"))
        self.assertIn(ROOT / ".codex/hooks.json", configs)
        for path in configs:
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / ".codex").rglob("*.toml")):
            with self.subTest(path=path):
                tomllib.loads(path.read_text(encoding="utf-8"))
        hooks = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(hooks), {"description", "hooks"})
        self.assertIsInstance(hooks["description"], str)
        self.assertEqual(hooks["hooks"], {})
        agents = sorted((ROOT / ".codex/agents").glob("*.toml"))
        self.assertTrue(agents, "no agent TOML files found")
        for path in agents:
            with self.subTest(path=path):
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["name"], path.stem)
                self.assertTrue(data["description"].strip())
                self.assertTrue(data["developer_instructions"].strip())

    def test_retired_hooks_and_review_marker_are_absent(self):
        for name in LEGACY_HOOKS:
            with self.subTest(name=name):
                self.assertFalse((ROOT / ".codex/hooks" / name).exists())
        self.assertFalse((ROOT / ".codex/.needs-review").exists())

    def test_skill_names_frontmatter_and_local_references(self):
        entries = sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))
        self.assertTrue(entries, "no SKILL.md files found")
        for entry in entries:
            with self.subTest(skill=entry.parent.name):
                header = basic_frontmatter(entry.read_text(encoding="utf-8"))
                self.assertEqual(header["name"], entry.parent.name)
                for document in entry.parent.rglob("*.md"):
                    self.assertEqual(missing_markdown_references(document, entry.parent), [], str(document))


class ValidatorTests(unittest.TestCase):
    def test_frontmatter_requires_fields_and_allows_optional_metadata(self):
        for text in ("name: example", "---\nname: example\n---\n",
                     "---\nname: example\nname: duplicate\ndescription: text\n---\n",
                     "---\nname: example\ndescription: \n---\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                basic_frontmatter(text)
        self.assertEqual(basic_frontmatter('---\nname: example\ndescription: "Text: detail"\n---\n'),
                         {"name": "example", "description": "Text: detail"})
        self.assertEqual(basic_frontmatter('---\nname: example\ndescription: text\n'
                                          'metadata:\n  owner: team\n---\n'),
                         {"name": "example", "description": "text"})

    def test_reference_validation_distinguishes_missing_files_from_templates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "references").mkdir()
            (root / "references/real.md").write_text("content")
            document = root / "SKILL.md"
            document.write_text("references/real.md references/missing.md\n"
                                "[valid](references/real.md#section) [gone](gone.md)\n"
                                "[external](https://example.com/missing.md)\n"
                                "[template](references/{name}.md) references/[文件]\n"
                                "```text\nreferences/example.md\n```\n")
            self.assertEqual(missing_markdown_references(document, root),
                             ["gone.md", "references/missing.md"])


if __name__ == "__main__":
    unittest.main()
