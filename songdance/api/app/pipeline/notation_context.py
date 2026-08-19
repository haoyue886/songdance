from dataclasses import dataclass


@dataclass(frozen=True)
class NotationContext:
    key_signature: str | None = None
    key_signature_source: str | None = None
    key_signature_confidence: float | None = None
    measure_offset_units: int | None = None
    measure_offset_source: str | None = None
    quantization_divisions_per_quarter: int | None = None
    quantization_source: str | None = None

    def __post_init__(self) -> None:
        if self.key_signature is None and (
            self.key_signature_source is not None
            or self.key_signature_confidence is not None
        ):
            raise ValueError("notation key source and confidence require a key signature")
        if self.key_signature is not None and self.key_signature_source is None:
            raise ValueError("notation key signature requires a source")
        if self.measure_offset_units is None and self.measure_offset_source is not None:
            raise ValueError("notation measure offset source requires an offset")
        if self.quantization_divisions_per_quarter is None and self.quantization_source is not None:
            raise ValueError("quantization source requires a fixed resolution")
        if self.quantization_divisions_per_quarter is not None and self.quantization_source is None:
            raise ValueError("fixed quantization resolution requires a source")


@dataclass(frozen=True)
class ResolvedNotationContext:
    local_tonal_center: str
    local_tonal_center_confidence: float
    local_tonal_center_source: str
    key_signature: str
    key_signature_source: str
    key_signature_confidence: float
    measure_offset_units: int
    measure_offset_source: str

    def summary(self) -> dict[str, object]:
        return {
            "local_tonal_center": self.local_tonal_center,
            "local_tonal_center_confidence": self.local_tonal_center_confidence,
            "local_tonal_center_source": self.local_tonal_center_source,
            "notation_key_signature": self.key_signature,
            "notation_key_signature_source": self.key_signature_source,
            "notation_key_signature_confidence": self.key_signature_confidence,
            "measure_offset_units": self.measure_offset_units,
            "measure_offset_source": self.measure_offset_source,
        }
