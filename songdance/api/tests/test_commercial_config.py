import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.commercial_config import FEATURE_FLAGS
from scripts.check_commercial_config import check, read_env

API_ROOT = Path(__file__).resolve().parents[1]


def valid_values() -> dict[str, str]:
    return {
        "SONGDANCE_ENVIRONMENT": "test",
        **{flag: "true" for flags in FEATURE_FLAGS.values() for flag in flags},
        "NEXT_PUBLIC_SITE_URL": "http://localhost:3000",
        "NEXT_PUBLIC_API_URL": "http://localhost:8000",
        "SONGDANCE_AUTH_API_URL": "http://localhost:8000",
        "SONGDANCE_CORS_ORIGINS": "http://localhost:3000",
        "SONGDANCE_SUPABASE_URL": "https://test-project.supabase.example",
        "SONGDANCE_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_synthetic_offline_key",
        "SONGDANCE_AUTH_SESSION_DATABASE_URL": (
            "postgresql://session_reader:synthetic_offline_password@db.example/postgres"
            "?sslmode=require"
        ),
        "SONGDANCE_AUTH_BRIDGE_SECRET": "TEST_ONLY_BRIDGE_SECRET_NOT_A_REAL_KEY_123",
        "SONGDANCE_REDIS_URL": "redis://localhost:6379/15",
        "SONGDANCE_QUOTA_BACKEND": "redis",
        "SONGDANCE_QUOTA_NAMESPACE": "commercial-config-test",
        "SONGDANCE_DATABASE_URL": "sqlite:///.data/commercial-config-test.db",
        "SONGDANCE_DOWNLOAD_SIGNING_SECRET": "TEST_ONLY_DOWNLOAD_SECRET_NOT_A_REAL_KEY_123",
        "SONGDANCE_GUEST_SIGNING_SECRET": "TEST_ONLY_GUEST_SECRET_NOT_A_REAL_KEY_123",
        "SONGDANCE_FREE_MONTHLY_JOB_LIMIT": "1",
        "SONGDANCE_BILLING_ENVIRONMENT": "test",
        "SONGDANCE_CREEM_API_KEY": "creem_test_synthetic_offline_key",
        "SONGDANCE_CREEM_WEBHOOK_SECRET": "TEST_ONLY_WEBHOOK_SECRET_NOT_A_REAL_KEY_123",
        "SONGDANCE_CREEM_PRODUCT_ID": "prod_synthetic_offline",
        "SONGDANCE_CREEM_SUCCESS_URL": "http://localhost:3000/billing/return",
        "SONGDANCE_CREEM_PLAN_VERSION": "pro-test-v1",
        "SONGDANCE_SUPPORT_EMAIL": "support@example.com",
    }


def diagnostics(report: dict[str, object]) -> list[dict[str, str]]:
    return report["errors"] + [
        item for feature in report["features"].values() for item in feature["errors"]
    ]


def write_env(path: Path, values: dict[str, str], mode: int = 0o600) -> None:
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8")
    path.chmod(mode)


def run_cli(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.check_commercial_config", "--env-file", str(path)],
        cwd=API_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_complete_shape_does_not_claim_supplier_or_live_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline checker must not connect")

    monkeypatch.setattr(socket, "create_connection", reject_connection)
    values = valid_values()
    original = dict(values)
    report = check(values)
    assert values == original
    assert report["configuration_format_valid"] is True
    assert report["commercial_test_configuration_valid"] is True
    assert all(feature["prerequisites_configured"] for feature in report["features"].values())
    assert not report["errors"]
    assert report["current_contract"] == {
        "free_monthly_successes": 1,
        "free_max_clip_seconds": 90,
        "pro_test_max_clip_seconds": 90,
        "guest_max_clip_seconds": 30,
        "live_supported": False,
    }
    for field in (
        "provider_connectivity_verified",
        "database_permissions_verified",
        "smtp_oauth_verified",
        "merchant_product_verified",
        "workers_running_verified",
        "production_ready",
    ):
        assert report[field] is False
    assert "price" not in json.dumps(report)


def test_closed_empty_template_is_valid_format_but_incomplete() -> None:
    values = {
        "SONGDANCE_ENVIRONMENT": "test",
        "SONGDANCE_BILLING_ENVIRONMENT": "test",
        **{flag: "false" for flags in FEATURE_FLAGS.values() for flag in flags},
    }
    report = check(values)
    assert report["configuration_format_valid"] is True
    assert report["commercial_test_configuration_valid"] is False
    assert all(not feature["enabled"] for feature in report["features"].values())
    assert all(not feature["prerequisites_configured"] for feature in report["features"].values())
    assert {"field": "SONGDANCE_CREEM_API_KEY", "code": "REQUIRED"} in diagnostics(report)


def test_explicit_mapping_never_uses_or_changes_process_and_dotenv_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ambient = valid_values()
    for field, value in ambient.items():
        monkeypatch.setenv(field, value)
    monkeypatch.setenv("SONGDANCE_MODEL_ONSET_THRESHOLD", "ambient-invalid-value")
    write_env(tmp_path / ".env", ambient)
    monkeypatch.chdir(tmp_path)
    environment_before = dict(os.environ)
    assert check(valid_values())["commercial_test_configuration_valid"] is True
    values = valid_values()
    values.pop("SONGDANCE_AUTH_BRIDGE_SECRET")
    values.pop("SONGDANCE_CREEM_API_KEY")
    report = check(values)
    assert report["commercial_test_configuration_valid"] is False
    assert {"field": "SONGDANCE_AUTH_BRIDGE_SECRET", "code": "EXPECTED_SERVER_BRIDGE_SECRET"} in (
        diagnostics(report)
    )
    assert {"field": "SONGDANCE_CREEM_API_KEY", "code": "REQUIRED"} in diagnostics(report)
    assert dict(os.environ) == environment_before


@pytest.mark.parametrize(
    "field",
    [flag for flags in FEATURE_FLAGS.values() for flag in flags],
)
def test_full_test_combination_requires_each_explicit_flag(field: str) -> None:
    values = valid_values()
    values.pop(field)
    report = check(values)
    assert report["commercial_test_configuration_valid"] is False
    assert {"field": field, "code": "FEATURE_DISABLED"} in diagnostics(report)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("SONGDANCE_ENVIRONMENT", "unknown", "INVALID_ENVIRONMENT"),
        ("SONGDANCE_BILLING_ENVIRONMENT", "live", "CREEM_TEST_ONLY"),
        ("SONGDANCE_FREE_MONTHLY_JOB_LIMIT", "2", "CURRENT_FREE_LIMIT_MUST_BE_ONE"),
        ("SONGDANCE_FREE_MONTHLY_JOB_LIMIT", "0", "CURRENT_FREE_LIMIT_MUST_BE_ONE"),
        ("NEXT_PUBLIC_AUTH_ENABLED", "1", "EXPECTED_TRUE_OR_FALSE"),
        ("NEXT_PUBLIC_AUTH_ENABLED", "false", "AUTH_FLAGS_MUST_MATCH"),
        ("NEXT_PUBLIC_API_URL", "https://other.example", "API_ORIGINS_MUST_MATCH"),
        ("SONGDANCE_CORS_ORIGINS", "https://other.example", "MUST_INCLUDE_SITE_ORIGIN"),
        (
            "SONGDANCE_CREEM_SUCCESS_URL",
            "https://other.example/billing/return",
            "EXPECTED_SITE_BILLING_RETURN_URL",
        ),
        (
            "SONGDANCE_CREEM_SUCCESS_URL",
            "http://localhost:3000/billing/return?paid=true",
            "EXPECTED_SITE_BILLING_RETURN_URL",
        ),
        (
            "SONGDANCE_CREEM_SUCCESS_URL",
            "http://localhost:3000/unexpected",
            "EXPECTED_SITE_BILLING_RETURN_URL",
        ),
        ("SONGDANCE_AUTH_BRIDGE_SECRET", "too-short", "EXPECTED_SERVER_BRIDGE_SECRET"),
        (
            "SONGDANCE_SUPABASE_PUBLISHABLE_KEY",
            "sb_secret_NOT_FOR_BROWSER",
            "EXPECTED_PUBLISHABLE_KEY",
        ),
        (
            "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "postgresql://postgres:secret@db.example/db",
            "EXPECTED_SCOPED_TLS_POSTGRES_DSN",
        ),
        (
            "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "postgresql://post%67res:secret@db.example/db",
            "EXPECTED_SCOPED_TLS_POSTGRES_DSN",
        ),
        (
            "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "postgresql://reader:secret@db.example/db?options=-crole%3Dpostgres",
            "EXPECTED_SCOPED_TLS_POSTGRES_DSN",
        ),
        ("SONGDANCE_GUEST_SIGNING_SECRET", "too-short", "EXPECTED_RANDOM_SIGNING_SECRET"),
        (
            "SONGDANCE_DOWNLOAD_SIGNING_SECRET",
            "development-only-download-secret-change-me",
            "EXPECTED_RANDOM_SIGNING_SECRET",
        ),
        ("SONGDANCE_CREEM_WEBHOOK_SECRET", "too-short", "EXPECTED_WEBHOOK_SECRET"),
        ("SONGDANCE_CREEM_PRODUCT_ID", "not_a_product", "EXPECTED_TEST_PRODUCT_ID"),
        ("SONGDANCE_CREEM_PLAN_VERSION", "unsafe plan", "EXPECTED_PLAN_VERSION"),
        ("SONGDANCE_DATABASE_URL", "sqlite:///:memory:", "EXPECTED_PERSISTENT_DATABASE_DSN"),
        ("SONGDANCE_REDIS_URL", "invalid-redis", "INVALID_SETTING"),
        ("SONGDANCE_MODEL_ONSET_THRESHOLD", "0.6", "SETTINGS_CONSTRAINT"),
        ("SONGDANCE_MAX_CLIP_SECONDS", "600", "UNSUPPORTED_SETTING"),
        ("NEXT_PUBLIC_SERVER_SECRET", "do-not-publish", "SERVER_CREDENTIAL_IN_PUBLIC_VARIABLE"),
    ],
)
def test_invalid_configuration_has_only_static_diagnostics(
    field: str, value: str, code: str
) -> None:
    report = check({**valid_values(), field: value})
    expected_field = (
        field
        if field
        not in {
            "SONGDANCE_MAX_CLIP_SECONDS",
            "NEXT_PUBLIC_SERVER_SECRET",
            "SONGDANCE_MODEL_ONSET_THRESHOLD",
        }
        else "ENV_FILE"
    )
    assert {"field": expected_field, "code": code} in diagnostics(report)
    assert report["configuration_format_valid"] is False
    assert report["commercial_test_configuration_valid"] is False
    assert all(set(item) == {"field", "code"} for item in diagnostics(report))


def test_production_is_not_a_creem_test_target() -> None:
    values = valid_values()
    values["SONGDANCE_ENVIRONMENT"] = "production"
    report = check(values)
    assert report["commercial_test_configuration_valid"] is False
    assert {"field": "SONGDANCE_ENVIRONMENT", "code": "CREEM_TEST_ONLY"} in diagnostics(report)


def test_signing_secrets_are_independent() -> None:
    values = valid_values()
    values["SONGDANCE_GUEST_SIGNING_SECRET"] = values["SONGDANCE_AUTH_BRIDGE_SECRET"]
    report = check(values)
    assert {
        "field": "SONGDANCE_GUEST_SIGNING_SECRET",
        "code": "EXPECTED_INDEPENDENT_SIGNING_SECRET",
    } in diagnostics(report)
    assert report["commercial_test_configuration_valid"] is False


def test_origin_matching_normalizes_host_and_default_ports() -> None:
    values = valid_values()
    values["NEXT_PUBLIC_SITE_URL"] = "https://SITE.example:443/"
    values["SONGDANCE_CORS_ORIGINS"] = "https://site.example:443"
    values["NEXT_PUBLIC_API_URL"] = "https://api.example:443/"
    values["SONGDANCE_AUTH_API_URL"] = "https://api.example"
    values["SONGDANCE_CREEM_SUCCESS_URL"] = "https://site.example:443/billing/return"
    report = check(values)
    assert report["commercial_test_configuration_valid"] is True


def test_cli_omitted_values_are_not_filled_from_process_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for field, value in valid_values().items():
        monkeypatch.setenv(field, value)
    path = tmp_path / "config.env"
    write_env(path, {"SONGDANCE_ENVIRONMENT": "test"})
    result = run_cli(path)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["configuration_format_valid"] is True
    assert report["commercial_test_configuration_valid"] is False
    assert {"field": "SONGDANCE_CREEM_API_KEY", "code": "REQUIRED"} in diagnostics(report)


def test_cli_rejects_non_regular_files_before_reading(tmp_path: Path) -> None:
    path = tmp_path / "config.fifo"
    os.mkfifo(path)
    result = run_cli(path)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"] == "ENV_FILE_UNREADABLE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("SONGDANCE_AUTH_BRIDGE_SECRET", "NEVER_ECHO_BRIDGE_123456789012345678901234\nSECRET"),
        (
            "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "postgresql://reader:NEVER_ECHO_PASSWORD@db.example:99999/db",
        ),
        ("SONGDANCE_REDIS_URL", "redis://user:NEVER_ECHO_REDIS@[invalid-ipv6"),
        ("SONGDANCE_CREEM_SUCCESS_URL", "https://user:NEVER_ECHO_URL@[invalid-ipv6"),
        ("SONGDANCE_SUPABASE_URL", "https://NEVER_ECHO_PROVIDER@[invalid-ipv6"),
        ("SONGDANCE_GUEST_SIGNING_SECRET", "NEVER_ECHO_GUEST_123456789012345678901234\nSECRET"),
        ("SONGDANCE_SUPPORT_EMAIL", "NEVER_ECHO_EMAIL@invalid\nsecret"),
        ("NEXT_PUBLIC_NEVER_ECHO_SECRET", "sb_secret_NEVER_ECHO_PUBLISHABLE"),
    ],
)
def test_sensitive_invalid_values_and_exception_inputs_never_appear(field: str, value: str) -> None:
    report = check({**valid_values(), field: value})
    assert report["commercial_test_configuration_valid"] is False
    assert "NEVER_ECHO" not in json.dumps(report)


@pytest.mark.parametrize(
    "content,code",
    [
        ("BAD NEVER_ECHO_INPUT", "INVALID_ENV_LINE_1"),
        ("KEY=NEVER_ECHO_FIRST\nKEY=NEVER_ECHO_SECOND", "INVALID_ENV_LINE_2"),
        ("KEY=$(NEVER_ECHO_COMMAND)", "UNSUPPORTED_EXPANSION_LINE_1"),
        ("KEY=`NEVER_ECHO_COMMAND`", "UNSUPPORTED_EXPANSION_LINE_1"),
        ("SONGDANCE_CREEM_API_KEY=NEVER_ECHO_KEY\nNEVER_ECHO_SECRET", "INVALID_ENV_LINE_2"),
    ],
)
def test_cli_reuses_locked_parser_without_echoing_input(
    tmp_path: Path, content: str, code: str
) -> None:
    path = tmp_path / "config.env"
    path.write_text(content, encoding="utf-8")
    result = run_cli(path)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"] == code
    assert "NEVER_ECHO" not in result.stdout + result.stderr


def test_cli_requires_an_explicit_readable_file(tmp_path: Path) -> None:
    missing = run_cli(tmp_path / "NEVER_ECHO_FILE.env")
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["error"] == "ENV_FILE_UNREADABLE"
    assert "NEVER_ECHO" not in missing.stdout + missing.stderr
    invalid = tmp_path / "config.env"
    invalid.write_bytes(b"KEY=\xffNEVER_ECHO_ENCODING")
    result = run_cli(invalid)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"] == "ENV_FILE_INVALID_ENCODING"
    assert "NEVER_ECHO" not in result.stdout + result.stderr


def test_cli_checks_private_permissions_and_does_not_modify_file(tmp_path: Path) -> None:
    path = tmp_path / "config.env"
    write_env(path, valid_values(), mode=0o644)
    original = path.read_bytes()
    result = run_cli(path)
    assert result.returncode == 2
    assert {"field": "ENV_FILE", "code": "ENV_FILE_PRIVATE_PERMISSIONS_REQUIRED"} in (
        json.loads(result.stdout)["errors"]
    )
    assert path.read_bytes() == original
    assert path.stat().st_mode & 0o777 == 0o644
    path.chmod(0o600)
    result = run_cli(path)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["commercial_test_configuration_valid"] is True
    for field, value in valid_values().items():
        if "SECRET" in field or "KEY" in field or "DATABASE_URL" in field:
            assert value not in result.stdout + result.stderr


def test_cli_closed_template_reports_incomplete_without_mutation(tmp_path: Path) -> None:
    values = {
        "SONGDANCE_ENVIRONMENT": "test",
        "SONGDANCE_BILLING_ENVIRONMENT": "test",
        **{flag: "false" for flags in FEATURE_FLAGS.values() for flag in flags},
    }
    path = tmp_path / "closed.env"
    write_env(path, values, mode=0o644)
    original = path.read_bytes()
    result = run_cli(path)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["configuration_format_valid"] is True
    assert report["commercial_test_configuration_valid"] is False
    assert read_env(path) == values
    assert path.read_bytes() == original


def test_cli_invalid_provider_url_cannot_echo_password(tmp_path: Path) -> None:
    values = valid_values()
    values["SONGDANCE_SUPABASE_URL"] = "https://user:NEVER_ECHO_PASSWORD@[invalid-ipv6"
    path = tmp_path / "config.env"
    write_env(path, values)
    result = run_cli(path)
    assert result.returncode == 2
    assert "NEVER_ECHO" not in result.stdout + result.stderr
    assert json.loads(result.stdout)["configuration_format_valid"] is False
