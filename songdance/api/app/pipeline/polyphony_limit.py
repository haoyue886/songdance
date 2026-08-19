from dataclasses import dataclass, replace

from app.pipeline.harmony import NotationGroup
from app.pipeline.voicing import assign_voices

RESONANT_POLYPHONY_VERSION = "resonant-polyphony-limit-v1"
RESONANT_POLYPHONY_TRIMMED = "RESONANT_POLYPHONY_TRIMMED"


@dataclass(frozen=True)
class PolyphonyLimitResult:
    groups: list[NotationGroup]
    applied: bool
    trimmed_group_count: int
    voice_count_before: int
    voice_count_after: int
    reason_codes: tuple[str, ...]

    def summary(self) -> dict[str, object]:
        return {
            "version": RESONANT_POLYPHONY_VERSION,
            "applied": self.applied,
            "trimmed_group_count": self.trimmed_group_count,
            "voice_count_before": self.voice_count_before,
            "voice_count_after": self.voice_count_after,
            "reason_codes": self.reason_codes,
        }


def limit_resonant_polyphony(
    groups: list[NotationGroup],
    *,
    evidence_available: bool,
    maximum_voices: int = 2,
) -> PolyphonyLimitResult:
    voices_before = len(assign_voices(groups))
    if not evidence_available or voices_before <= maximum_voices:
        return PolyphonyLimitResult(
            groups=groups,
            applied=False,
            trimmed_group_count=0,
            voice_count_before=voices_before,
            voice_count_after=voices_before,
            reason_codes=(),
        )

    pitches_by_start: dict[int, set[int]] = {}
    for group in groups:
        pitches_by_start.setdefault(group.start_units, set()).update(group.pitches)
    starts = sorted(pitches_by_start)
    limited = []
    trimmed = 0
    for group in groups:
        future = [start for start in starts if group.start_units < start < group.end_units]
        independent_overlap_count = sum(
            all(
                abs(pitch - other) >= 12
                for pitch in group.pitches
                for other in pitches_by_start[start]
            )
            for start in future
        )
        if not future or independent_overlap_count >= 3:
            limited.append(group)
            continue
        limited.append(replace(group, end_units=future[0]))
        trimmed += 1

    voices_after = len(assign_voices(limited))
    applied = trimmed > 0
    return PolyphonyLimitResult(
        groups=limited,
        applied=applied,
        trimmed_group_count=trimmed,
        voice_count_before=voices_before,
        voice_count_after=voices_after,
        reason_codes=(RESONANT_POLYPHONY_TRIMMED,) if applied else (),
    )
