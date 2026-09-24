"""Prepare pending human labels; model-derived candidates are never note truth."""

import argparse
import json
from pathlib import Path

import soundfile as sf

from scripts.piano_comparison_cases import BATCH_ROOT, case_inputs, file_sha256
from scripts.run_real_partial_probe import CASE, verify


def candidates(raw: list[dict]) -> list[dict]:
    previous = {}
    rows = []
    for index, event in enumerate(raw):
        parent = previous.get(event["pitch"])
        if parent is not None and 0.1 <= event["start_sec"] - raw[parent]["start_sec"] <= 1.2:
            rows.append(
                {
                    "id": f"event-{index:04d}",
                    "input_index": index,
                    "previous_input_index": parent,
                    "model_event": event,
                    "previous_model_event": raw[parent],
                }
            )
        previous[event["pitch"]] = index
    return rows


def prepare(output: Path) -> dict:
    baseline = BATCH_ROOT / CASE / "basic-pitch"
    _, raw = verify(baseline)
    source, _, provenance = case_inputs(CASE)
    pcm, rate = sf.read(source, dtype="int16", always_2d=True)
    output.mkdir(parents=True, exist_ok=False)
    rows = candidates(raw)
    for row in rows:
        start = max(0, int((row["previous_model_event"]["start_sec"] - 0.3) * rate))
        stop = min(len(pcm), int((row["model_event"]["start_sec"] + 0.5) * rate))
        name = row["id"] + ".wav"
        sf.write(output / name, pcm[start:stop], rate, subtype="PCM_16")
        row.update(
            clip_file=name,
            clip_sha256=file_sha256(output / name),
            start_sample=start,
            stop_sample=stop,
            candidate_local_sec=row["model_event"]["start_sec"] - start / rate,
        )
    manifest = {
        "schema_version": 1,
        "case_id": CASE,
        "production_eligible": False,
        "selection": "same-pitch model predecessor 0.1 to 1.2 seconds; biased candidate set",
        "source_sha256": file_sha256(source),
        "sample_rate": rate,
        "source_provenance": provenance,
        "raw_sha256": file_sha256(baseline / "raw.mid"),
        "code_sha256": file_sha256(Path(__file__)),
        "candidates": rows,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    labels = {
        "manifest_sha256": file_sha256(output / "manifest.json"),
        "reviewer": None,
        "labels": [
            {
                "id": row["id"],
                "judgment": "pending",
                "confirmed_pitch": None,
                "confirmed_onset_sec": None,
                "notes": "",
            }
            for row in rows
        ],
    }
    (output / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    (output / "README.md").write_text("""# 真人重复音标注草稿

这不是最终评审包。候选来自模型，不能当作正确音符；这是偏置检索集，不代表整段录音。
每个WAV保留原音频PCM，manifest列出起止采样点、模型音高、候选在片段内的位置。

请逐片听辨模型候选处是否真的再次击键，填写labels.json：
- reviewer：填写实际复核人的姓名或稳定代号，不要填写模型名称。
- judgment：restrike（确有再次击键）、no_restrike（没有再次击键）或uncertain（无法判定）。
- restrike必须填写confirmed_pitch（MIDI整数21–108）及confirmed_onset_sec。
- confirmed_onset_sec以原30秒录音片段开头为0，不能填写短WAV内的时间。
  两者差为start_sample/sample_rate。
- no_restrike和uncertain保持两个confirmed字段为null；
  no_restrike只否定再次击键，不证明应删音或属于泛音。
- 每条notes写判断依据或疑问；不确定就保留uncertain，不能猜测。

全部pending/uncertain解决前验证不会通过。即使验证通过，也仅表示人工表单完整，不能自动授权删音或声称全曲准确率。
""")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = prepare(parser.parse_args().output)
    print(f"Prepared {len(result['candidates'])} pending candidates")
