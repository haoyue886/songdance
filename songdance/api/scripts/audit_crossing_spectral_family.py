"""Measure spectral-family ambiguity for the frozen 22 candidates and 120 control WAVs."""

import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import soundfile as sf

from app.pipeline.audio import preprocess_audio
from app.pipeline.transcribe import NoteEvent
from scripts.audit_crossing_harmonics import OUTPUT as INPUT
from scripts.build_crossing_eighth_candidate import OUTPUT_DIR as BASELINE
from scripts.build_crossing_eighth_candidate import ROOT, SOURCE_WAV, file_sha256
from scripts.spectral_family_evidence import measure_spectral_family

OUTPUT = ROOT / "tests/fixtures/audio/candidates/14-hand-crossing-spectral-family"


def run(output: Path = OUTPUT) -> dict:
    source_report = INPUT / "report.json"
    audit = json.loads(source_report.read_text())
    bindings = {
        **audit["baseline_hashes"],
        **audit["baseline_pipeline_hashes"],
        **audit["audit_code_hashes"],
    }
    bindings[str(source_report.relative_to(ROOT))] = file_sha256(source_report)
    normalized = BASELINE / "normalized.wav"
    bindings[str(normalized.relative_to(ROOT))] = file_sha256(normalized)
    for name, digest in bindings.items():
        if file_sha256(ROOT / name) != digest:
            raise ValueError(f"stale spectral audit input: {name}")
    with TemporaryDirectory(prefix="crossing-spectrum-source-") as temp:
        verified = Path(temp) / "normalized.wav"
        preprocess_audio(SOURCE_WAV, verified)
        if file_sha256(verified) != file_sha256(normalized):
            raise ValueError("normalized candidate WAV does not reproduce from the frozen source")
    audio, rate = sf.read(normalized)
    events = [NoteEvent(**e) for e in json.loads((BASELINE / "raw-events.json").read_text())]
    candidates = []
    for candidate in audit["candidates"]:
        event = events[candidate["raw_event_index"]]
        candidates.append(
            {
                "raw_event_index": candidate["raw_event_index"],
                "measurement": measure_spectral_family(audio, rate, event, events),
            }
        )
    probes = []
    for probe in audit["probes"]:
        path = INPUT / probe["wav"]
        digest = file_sha256(path)
        if digest != probe["wav_sha256"]:
            raise ValueError(f"changed probe WAV: {probe['id']}")
        bindings[str(path.relative_to(ROOT))] = digest
        wave, sample_rate = sf.read(path)
        hypotheses = [NoteEvent(**e) for e in probe["candidate_events"]]
        probes.append(
            {
                "id": probe["id"],
                "truth": probe["truth"],
                "parameters": probe["parameters"],
                "measurement": measure_spectral_family(
                    wave, sample_rate, hypotheses[1], hypotheses
                ),
            }
        )
    for name, digest in bindings.items():
        if file_sha256(ROOT / name) != digest:
            raise RuntimeError("input changed during spectral audit")
    report = {
        "schema_version": 1,
        "status": "spectral_evidence_only",
        "new_deletion_count": 0,
        "production_eligible": False,
        "input_hashes": bindings,
        "code_hashes": {
            str(p.relative_to(ROOT)): file_sha256(p)
            for p in (Path(__file__), ROOT / "scripts/spectral_family_evidence.py")
        },
        "candidate_count": len(candidates),
        "probe_count": len(probes),
        "candidate_status_counts": dict(Counter(c["measurement"]["status"] for c in candidates)),
        "probe_status_counts": {
            label: dict(Counter(p["measurement"]["status"] for p in probes if p["truth"] == label))
            for label in ("natural_partial_only", "real_simultaneous_note")
        },
        "candidates": candidates,
        "probes": probes,
        "scope": "nominal pitch families and window-limited FFT; no learned piano timbre model",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "candidate_count",
                    "probe_count",
                    "candidate_status_counts",
                    "probe_status_counts",
                    "new_deletion_count",
                )
            },
            ensure_ascii=False,
        )
    )
    return report


if __name__ == "__main__":
    run()
