from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    status: str
    size_bytes: int
    mime_type: str | None
    error_code: str | None


class TranscriptionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tempo: float | None
    time_signature: str | None
    note_count: int | None
    quality_flags: str | None
    model_version: str | None


class QualityReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_version: str
    summary: str


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    stage: str
    source_type: str
    start_sec: float
    end_sec: float
    attempt_count: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    result: TranscriptionResultResponse | None
    quality_report: QualityReportResponse | None
    artifacts: list[ArtifactResponse]


class DownloadUrlResponse(BaseModel):
    path: str
    expires_at: int
