import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_auth_config import check, read_env

API_ROOT = Path(__file__).resolve().parents[1]


def valid_values() -> dict[str, str]:
    return {
        "SONGDANCE_ENVIRONMENT": "production",
        "NEXT_PUBLIC_SITE_URL": "https://songdance.example",
        "SONGDANCE_AUTH_API_URL": "https://api.songdance.example",
        "SONGDANCE_SUPABASE_URL": "https://test-project.supabase.co",
        "SONGDANCE_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test_only_not_a_real_key",
        "SONGDANCE_AUTH_SESSION_DATABASE_URL": (
            "postgresql://session_reader:test_only@db.example/postgres?sslmode=require"
        ),
    }


def test_valid_shape_is_not_a_production_or_provider_readiness_claim() -> None:
    result = check(valid_values())
    assert result["configuration_format_valid"] is True
    assert result["production_ready"] is False
    assert result["provider_connectivity_verified"] is False
    assert result["database_permissions_verified"] is False


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("SONGDANCE_ENVIRONMENT", "typo", "INVALID_ENVIRONMENT"),
        ("NEXT_PUBLIC_SITE_URL", "http://songdance.example", "INVALID_ORIGIN"),
        ("NEXT_PUBLIC_SITE_URL", "https://evil.example/path", "INVALID_ORIGIN"),
        ("SONGDANCE_SUPABASE_URL", "https://user:secret@host.example", "INVALID_ORIGIN"),
        ("SONGDANCE_AUTH_API_URL", "https://host.example:99999", "INVALID_ORIGIN"),
        ("SONGDANCE_AUTH_API_URL", "https://localhost", "INVALID_ORIGIN"),
        ("SONGDANCE_SUPABASE_PUBLISHABLE_KEY", "sb_secret_test_secret", "EXPECTED_PUBLISHABLE_KEY"),
        (
            "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "postgresql://u:p@h/db",
            "EXPECTED_SCOPED_TLS_POSTGRES_DSN",
        ),
        (
            "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "postgresql://postgres:p@h/db?sslmode=require",
            "EXPECTED_SCOPED_TLS_POSTGRES_DSN",
        ),
        (
            "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "postgresql://post%67res:p@h/db?sslmode=require",
            "EXPECTED_SCOPED_TLS_POSTGRES_DSN",
        ),
        ("NEXT_PUBLIC_SUPABASE_SECRET", "do_not_print_me", "SERVER_CREDENTIAL_IN_PUBLIC_VARIABLE"),
    ],
)
def test_invalid_configuration_returns_only_field_and_code(
    field: str,
    value: str,
    code: str,
) -> None:
    values = {**valid_values(), field: value}
    result = check(values)
    assert {"field": field, "code": code} in result["errors"]
    assert result["configuration_format_valid"] is False
    assert value not in json.dumps(result)


def test_empty_template_is_rejected_without_reading_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONGDANCE_SUPABASE_PUBLISHABLE_KEY", "must-not-be-loaded")
    values = read_env(API_ROOT.parent / "infra/env.auth.example")
    report = check(values)
    assert report["configuration_format_valid"] is False
    assert len(report["errors"]) == 5
    assert "must-not-be-loaded" not in json.dumps(report)


@pytest.mark.parametrize(
    "query",
    [
        "user=postgres",
        "%75ser=postgres",
        "user=",
        "password=another_secret",
        "host=another-host.example",
        "service=admin",
        "options=-crole%3Dpostgres",
        "sslmode=disable",
    ],
)
def test_dsn_cannot_override_authority_or_tls_through_query(query: str) -> None:
    values = valid_values()
    values["SONGDANCE_AUTH_SESSION_DATABASE_URL"] += "&" + query
    result = check(values)
    assert result["configuration_format_valid"] is False
    assert result["errors"] == [
        {
            "field": "SONGDANCE_AUTH_SESSION_DATABASE_URL",
            "code": "EXPECTED_SCOPED_TLS_POSTGRES_DSN",
        }
    ]


@pytest.mark.parametrize(
    "text",
    ["BAD LINE", "KEY=a\nKEY=b", "KEY=$(command)", "KEY=`command`"],
)
def test_env_parser_rejects_ambiguous_or_executable_input(tmp_path: Path, text: str) -> None:
    config = tmp_path / "auth.env"
    config.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        read_env(config)


def test_cli_reports_error_without_echoing_credentials(tmp_path: Path) -> None:
    config = tmp_path / "auth.env"
    values = valid_values()
    values["SONGDANCE_SUPABASE_PUBLISHABLE_KEY"] = "sb_secret_NEVER_ECHO_123"
    config.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_auth_config", "--env-file", str(config)],
        cwd=API_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "NEVER_ECHO" not in result.stdout + result.stderr
    assert json.loads(result.stdout)["configuration_format_valid"] is False
