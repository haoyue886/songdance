from pydantic import BaseModel, Field


class YoutubeConfigResponse(BaseModel):
    enabled: bool


class YoutubeJobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(gt=0, allow_inf_nan=False)
    rights_confirmed: bool
