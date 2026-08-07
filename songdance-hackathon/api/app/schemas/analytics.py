from pydantic import BaseModel, Field


class AnalyticsEventCreate(BaseModel):
    event_name: str = Field(min_length=1, max_length=64)
    job_id: str = Field(min_length=32, max_length=64)
    properties: dict[str, object] = Field(default_factory=dict)
