import pytest
from pydantic import ValidationError

from app.settings import CALIBRATED_MODEL_THRESHOLDS, Settings


def test_settings_reject_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONGDANCE_ENVIRONMENT", "definitely-invalid")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reject_empty_cors_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins="")


def test_settings_normalize_valid_cors_origins() -> None:
    settings = Settings(cors_origins="http://localhost:3000, https://songdance.example")

    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "https://songdance.example",
    ]


def test_settings_allow_next_development_ports_by_default() -> None:
    assert Settings().cors_origin_list == [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_settings_normalize_hosted_postgres_urls(scheme: str) -> None:
    settings = Settings(database_url=f"{scheme}://user:password@db.example/songdance")

    assert settings.database_url == ("postgresql+psycopg://user:password@db.example/songdance")


def test_settings_reject_cors_paths_and_insecure_production_defaults() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins="https://songdance.example/private")
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            cors_origins="https://songdance.example",
            trusted_proxy_hops=1,
            trusted_proxy_cidrs="10.0.0.0/8",
        )


def test_production_requires_https_redis_quota_and_unique_secret() -> None:
    settings = Settings(
        environment="production",
        cors_origins="https://songdance.example",
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="10.0.0.0/8",
        quota_backend="redis",
        download_signing_secret="a-unique-production-secret-with-32-characters",
    )
    assert settings.cors_origin_list == ["https://songdance.example"]

    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            cors_origins="https://songdance.example",
            trusted_proxy_hops=1,
            trusted_proxy_cidrs="10.0.0.0/8",
            quota_backend="memory",
            download_signing_secret="a-unique-production-secret-with-32-characters",
        )


def test_production_rejects_default_proxy_routes() -> None:
    with pytest.raises(ValidationError, match="default route"):
        Settings(
            environment="production",
            cors_origins="https://songdance.example",
            trusted_proxy_hops=1,
            trusted_proxy_cidrs="0.0.0.0/0,::/0",
            quota_backend="redis",
            download_signing_secret="a-unique-production-secret-with-32-characters",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_onset_threshold", 0),
        ("model_frame_threshold", 1.1),
        ("model_onset_threshold", 0.85),
        ("model_frame_threshold", 0.55),
    ],
)
def test_settings_reject_invalid_model_thresholds(field: str, value: float) -> None:
    with pytest.raises(ValidationError, match="model thresholds"):
        Settings(**{field: value})


def test_settings_only_allows_the_calibrated_model_profile() -> None:
    settings = Settings()

    assert (settings.model_onset_threshold, settings.model_frame_threshold) == (
        CALIBRATED_MODEL_THRESHOLDS
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("cleanup_min_confidence", -0.1),
        ("cleanup_min_confidence", 1.1),
        ("cleanup_min_duration_seconds", 1.1),
        ("cleanup_adjacent_same_pitch_gap_seconds", 0.11),
        ("cleanup_max_note_duration_seconds", 0.9),
        ("cleanup_max_note_duration_seconds", 90.1),
    ],
)
def test_settings_reject_cleanup_thresholds_outside_supported_ranges(
    field: str, value: float
) -> None:
    with pytest.raises(ValidationError, match="cleanup thresholds"):
        Settings(**{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("analysis_sample_rate", 7_999),
        ("analysis_hop_length", 64),
        ("analysis_min_tempo_confidence", -0.1),
        ("analysis_min_meter_confidence", 1.1),
        ("analysis_min_key_confidence", 1.1),
        ("analysis_timeout_seconds", 15.1),
    ],
)
def test_settings_reject_invalid_analysis_configuration(field: str, value: float) -> None:
    with pytest.raises(ValidationError, match="analysis"):
        Settings(**{field: value})
