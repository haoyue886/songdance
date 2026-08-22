from dataclasses import dataclass


@dataclass(frozen=True)
class NotationContext:
    key_signature: str | None = None
    key_signature_source: str | None = None
    key_signature_confidence: float | None = None
    time_signature: str | None = None
    time_signature_source: str | None = None
    time_signature_confidence: float | None = None
    measure_offset_units: int | None = None
    measure_offset_source: str | None = None
    quantization_divisions_per_quarter: int | None = None
    quantization_source: str | None = None
    ornamentation_expected: bool = False
    ornamentation_source: str | None = None

    def __post_init__(self) -> None:
        if self.key_signature is None and (
            self.key_signature_source is not None
            or self.key_signature_confidence is not None
        ):
            raise ValueError("notation key source and confidence require a key signature")
        if self.key_signature is not None and self.key_signature_source is None:
            raise ValueError("notation key signature requires a source")
        if self.time_signature is None and (
            self.time_signature_source is not None
            or self.time_signature_confidence is not None
        ):
            raise ValueError("notation time source and confidence require a time signature")
        if self.time_signature is not None and self.time_signature_source is None:
            raise ValueError("notation time signature requires a source")
        if self.measure_offset_units is None and self.measure_offset_source is not None:
            raise ValueError("notation measure offset source requires an offset")
        if self.quantization_divisions_per_quarter is None and self.quantization_source is not None:
            raise ValueError("quantization source requires a fixed resolution")
        if self.quantization_divisions_per_quarter is not None and self.quantization_source is None:
            raise ValueError("fixed quantization resolution requires a source")
        if self.ornamentation_expected and self.ornamentation_source is None:
            raise ValueError("expected ornamentation requires a source")
        if not self.ornamentation_expected and self.ornamentation_source is not None:
            raise ValueError("ornamentation source requires expected ornamentation")


@dataclass(frozen=True)
class ResolvedNotationContext:
    local_tonal_center: str
    local_tonal_center_confidence: float
    local_tonal_center_source: str
    key_signature: str
    key_signature_source: str
    key_signature_confidence: float
    time_signature: str
    time_signature_source: str
    time_signature_confidence: float
    measure_offset_units: int
    measure_offset_source: str
    ornamentation_expected: bool
    ornamentation_source: str | None

    def summary(self) -> dict[str, object]:
        return {
            "local_tonal_center": self.local_tonal_center,
            "local_tonal_center_confidence": self.local_tonal_center_confidence,
            "local_tonal_center_source": self.local_tonal_center_source,
            "notation_key_signature": self.key_signature,
            "notation_key_signature_source": self.key_signature_source,
            "notation_key_signature_confidence": self.key_signature_confidence,
            "notation_time_signature": self.time_signature,
            "notation_time_signature_source": self.time_signature_source,
            "notation_time_signature_confidence": self.time_signature_confidence,
            "measure_offset_units": self.measure_offset_units,
            "measure_offset_source": self.measure_offset_source,
            "ornamentation_expected": self.ornamentation_expected,
            "ornamentation_source": self.ornamentation_source,
        }
