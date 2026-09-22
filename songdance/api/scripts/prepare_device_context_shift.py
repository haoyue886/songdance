import json

import numpy as np
import soundfile as sf

from scripts.piano_comparison_cases import BATCH_ROOT, file_sha256

r = BATCH_ROOT / "10-device"
out = r / "context-shift-4s"
out.mkdir(exist_ok=False)
src = r / "basic-pitch/normalized.wav"
y, sr = sf.read(src, dtype="int16")
sf.write(
    out / "padded.wav",
    np.concatenate([np.zeros(4 * sr, dtype="int16"), y, np.zeros(sr, dtype="int16")]),
    sr,
    subtype="PCM_16",
)
z, _ = sf.read(out / "padded.wav", dtype="int16")
assert np.array_equal(y, z[4 * sr : 4 * sr + len(y)])
(out / "input.json").write_text(
    json.dumps(
        {
            "source_sha256": file_sha256(src),
            "padded_sha256": file_sha256(out / "padded.wav"),
            "prefix_seconds": 4,
            "suffix_seconds": 1,
            "original_frames": len(y),
            "sample_rate": sr,
            "production_eligible": False,
            "original_samples_preserved": True,
        },
        indent=2,
    )
)
print(out)
