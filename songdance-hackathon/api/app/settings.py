from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import AnyHttpUrl, RedisDsn, SecretStr, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from app.pipeline.analysis import AnalysisConfig
    from app.pipeline.cleanup import CleanupConfig

CALIBRATED_MODEL_THRESHOLDS = (0.5, 0.3)


class Settings(BaseSettings):
    app_name: str = "SongDance API"
    environment: Literal["development", "test", "production"] = "development"
    cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001"
    )
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    queue_name: str = "songdance"
    quota_backend: Literal["memory", "redis"] = "redis"
    quota_namespace: str = "songdance"
    database_url: str = "sqlite:///./.data/songdance.db"
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: Path = Path(".data/storage")
    temp_path: Path = Path(".data/tmp")
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "songdance"
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    auto_create_schema: bool = False
    trusted_proxy_hops: int = 0
    trusted_proxy_cidrs: str = ""
    max_request_bytes: int = 26 * 1024 * 1024
    hourly_job_limit: int = 3
    client_active_job_limit: int = 1
    global_active_job_limit: int = 8
    daily_job_limit: int = 100
    analytics_job_event_limit_per_minute: int = 10
    analytics_client_event_limit_per_minute: int = 30
    analytics_global_event_limit_per_minute: int = 1000
    analytics_daily_event_limit: int = 10000
    quota_active_ttl_seconds: int = 24 * 60 * 60
    download_url_ttl_seconds: int = 5 * 60
    download_signing_secret: SecretStr = SecretStr("development-only-download-secret-change-me")
    cleanup_interval_seconds: int = 15 * 60
    cleanup_batch_size: int = 100
    temp_file_ttl_seconds: int = 24 * 60 * 60
    upload_intent_timeout_seconds: int = 15 * 60
    model_onset_threshold: float = CALIBRATED_MODEL_THRESHOLDS[0]
    model_frame_threshold: float = CALIBRATED_MODEL_THRESHOLDS[1]
    cleanup_min_confidence: float = 0.1
    cleanup_min_duration_seconds: float = 0.04
    cleanup_adjacent_same_pitch_gap_seconds: float = 0.03
    cleanup_max_note_duration_seconds: float = 30.0
    analysis_enabled: bool = True
    analysis_sample_rate: int = 22_050
    analysis_hop_length: int = 512
    analysis_min_tempo_confidence: float = 0.2
    analysis_min_meter_confidence: float = 0.6
    analysis_min_key_confidence: float = 0.18
    analysis_timeout_seconds: float = 15.0
    youtube_enabled: bool = False
    youtube_download_timeout_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SONGDANCE_")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_postgres_driver(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("cors_origins must contain at least one HTTP(S) origin")
        adapter = TypeAdapter(AnyHttpUrl)
        for origin in origins:
            parsed = adapter.validate_python(origin)
            if (
                parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("CORS entries must be origins without paths or credentials")
        return ",".join(origins)

    @field_validator("quota_namespace")
    @classmethod
    def validate_quota_namespace(cls, value: str) -> str:
        if (
            not value
            or len(value) > 64
            or any(
                character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                for character in value
            )
        ):
            raise ValueError("quota namespace must be a safe 1-64 character identifier")
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: str) -> str:
        networks = [item.strip() for item in value.split(",") if item.strip()]
        try:
            normalized = [str(ip_network(item, strict=False)) for item in networks]
        except ValueError as error:
            raise ValueError("trusted proxy CIDRs must be valid IP networks") from error
        return ",".join(normalized)

    @model_validator(mode="after")
    def validate_service_configuration(self) -> "Settings":
        if self.storage_backend == "s3":
            required = [self.s3_endpoint_url, self.s3_access_key, self.s3_secret_key]
            if not all(required):
                raise ValueError("S3 storage requires endpoint URL, access key and secret key")
        if self.environment == "production" and self.auto_create_schema:
            raise ValueError("auto_create_schema is forbidden in production")
        positive_fields = {
            "max_request_bytes": self.max_request_bytes,
            "hourly_job_limit": self.hourly_job_limit,
            "client_active_job_limit": self.client_active_job_limit,
            "global_active_job_limit": self.global_active_job_limit,
            "daily_job_limit": self.daily_job_limit,
            "analytics_job_event_limit_per_minute": self.analytics_job_event_limit_per_minute,
            "analytics_client_event_limit_per_minute": self.analytics_client_event_limit_per_minute,
            "analytics_global_event_limit_per_minute": self.analytics_global_event_limit_per_minute,
            "analytics_daily_event_limit": self.analytics_daily_event_limit,
            "quota_active_ttl_seconds": self.quota_active_ttl_seconds,
            "download_url_ttl_seconds": self.download_url_ttl_seconds,
            "cleanup_interval_seconds": self.cleanup_interval_seconds,
            "cleanup_batch_size": self.cleanup_batch_size,
            "temp_file_ttl_seconds": self.temp_file_ttl_seconds,
            "upload_intent_timeout_seconds": self.upload_intent_timeout_seconds,
            "youtube_download_timeout_seconds": self.youtube_download_timeout_seconds,
            "analysis_timeout_seconds": self.analysis_timeout_seconds,
        }
        if any(value <= 0 for value in positive_fields.values()):
            raise ValueError("limits, TTLs and cleanup settings must be positive")
        if self.trusted_proxy_hops < 0:
            raise ValueError("trusted proxy hops cannot be negative")
        if not 0 < self.model_onset_threshold <= 1 or not 0 < self.model_frame_threshold <= 1:
            raise ValueError("model thresholds must be greater than 0 and at most 1")
        if (self.model_onset_threshold, self.model_frame_threshold) != CALIBRATED_MODEL_THRESHOLDS:
            raise ValueError("model thresholds must match the calibrated 0.5/0.3 profile")
        cleanup_ranges = {
            "cleanup_min_confidence": (self.cleanup_min_confidence, 0, 1),
            "cleanup_min_duration_seconds": (self.cleanup_min_duration_seconds, 0, 1),
            "cleanup_adjacent_same_pitch_gap_seconds": (
                self.cleanup_adjacent_same_pitch_gap_seconds,
                0,
                0.1,
            ),
            "cleanup_max_note_duration_seconds": (
                self.cleanup_max_note_duration_seconds,
                1,
                90,
            ),
        }
        if any(not lower <= value <= upper for value, lower, upper in cleanup_ranges.values()):
            raise ValueError("cleanup thresholds are outside their supported ranges")
        if not 8_000 <= self.analysis_sample_rate <= 48_000:
            raise ValueError("analysis sample rate is outside its supported range")
        if not 128 <= self.analysis_hop_length <= 4_096:
            raise ValueError("analysis hop length is outside its supported range")
        analysis_confidences = (
            self.analysis_min_tempo_confidence,
            self.analysis_min_meter_confidence,
            self.analysis_min_key_confidence,
        )
        if any(not 0 <= value <= 1 for value in analysis_confidences):
            raise ValueError("analysis confidence thresholds must be between 0 and 1")
        if self.analysis_timeout_seconds > 15:
            raise ValueError("analysis timeout must not exceed 15 seconds")
        if self.global_active_job_limit < self.client_active_job_limit:
            raise ValueError("global active limit cannot be lower than client active limit")
        if self.environment == "production":
            if self.quota_backend != "redis":
                raise ValueError("production requires Redis-backed quotas")
            secret = self.download_signing_secret.get_secret_value()
            if secret == "development-only-download-secret-change-me" or len(secret) < 32:
                raise ValueError("production requires a unique 32+ character signing secret")
            if self.trusted_proxy_hops < 1:
                raise ValueError("production requires at least one trusted proxy hop for IP limits")
            if not self.trusted_proxy_networks:
                raise ValueError("production requires trusted proxy CIDRs for IP limits")
            if any(network.prefixlen == 0 for network in self.trusted_proxy_networks):
                raise ValueError("production trusted proxy CIDRs cannot use a default route")
            if any(not origin.startswith("https://") for origin in self.cors_origin_list):
                raise ValueError("production CORS origins must use HTTPS")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins.split(",")

    @property
    def trusted_proxy_networks(self) -> list[IPv4Network | IPv6Network]:
        return [ip_network(item) for item in self.trusted_proxy_cidrs.split(",") if item]

    @property
    def note_cleanup_config(self) -> "CleanupConfig":
        from app.pipeline.cleanup import CleanupConfig

        return CleanupConfig(
            min_confidence=self.cleanup_min_confidence,
            min_duration_seconds=self.cleanup_min_duration_seconds,
            adjacent_same_pitch_gap_seconds=self.cleanup_adjacent_same_pitch_gap_seconds,
            max_note_duration_seconds=self.cleanup_max_note_duration_seconds,
        )

    @property
    def structure_analysis_config(self) -> "AnalysisConfig":
        from app.pipeline.analysis import AnalysisConfig

        return AnalysisConfig(
            enabled=self.analysis_enabled,
            sample_rate=self.analysis_sample_rate,
            hop_length=self.analysis_hop_length,
            min_tempo_confidence=self.analysis_min_tempo_confidence,
            min_meter_confidence=self.analysis_min_meter_confidence,
            min_key_confidence=self.analysis_min_key_confidence,
            timeout_seconds=self.analysis_timeout_seconds,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
