"""Run a loopback mail test listener from one private file; never print credentials."""

import argparse
import json
import stat
from pathlib import Path

import uvicorn
from pydantic import ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.mail_hook import create_mail_hook_app
from app.services.auth_config import read_env
from app.services.mail_contract import validate_mail_settings
from app.settings import Settings

SETTING_FIELDS = {"SONGDANCE_" + name.upper(): name for name in Settings.model_fields}
REQUIRED_MAIL_FIELDS = (
    "SONGDANCE_MAIL_PROJECT_REF", "SONGDANCE_SUPABASE_URL", "SONGDANCE_CORS_ORIGINS",
    "SONGDANCE_MAIL_SITE_URL", "SONGDANCE_MAIL_FROM", "SONGDANCE_MAIL_TEST_RECIPIENTS",
    "SONGDANCE_SUPPORT_EMAIL", "SONGDANCE_RESEND_API_KEY",
    "SONGDANCE_SUPABASE_EMAIL_HOOK_SECRET", "SONGDANCE_RESEND_WEBHOOK_SECRET",
    "SONGDANCE_MAIL_DIGEST_SECRET", "SONGDANCE_DATABASE_URL",
)


class FileSettings(Settings):
    @classmethod
    def settings_customise_sources(
        cls, settings_cls: type[BaseSettings], init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource, dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def load_settings(path: Path) -> Settings:
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError("PRIVATE_ENV_FILE_REQUIRED")
    values = read_env(path)
    if set(values) - SETTING_FIELDS.keys():
        raise ValueError("UNSUPPORTED_MAIL_SETTING")
    if values.get("SONGDANCE_ENVIRONMENT") != "test" or (
        values.get("SONGDANCE_AUTO_CREATE_SCHEMA") != "false"
    ) or not values.get("SONGDANCE_DATABASE_URL"):
        raise ValueError("EXPLICIT_TEST_DATABASE_REQUIRED")
    return FileSettings(_env_file=None, **{
        SETTING_FIELDS[key]: value for key, value in values.items()
    })


def preflight(path: Path) -> tuple[dict, Settings | None]:
    try:
        settings = load_settings(path)
        missing = [field for field in REQUIRED_MAIL_FIELDS
                   if not getattr(settings, SETTING_FIELDS[field])
                   or (hasattr(getattr(settings, SETTING_FIELDS[field]), "get_secret_value")
                       and not getattr(settings, SETTING_FIELDS[field]).get_secret_value())]
        try:
            validate_mail_settings(settings)
            ready = True
        except ValueError:
            ready = False
        return {
            "configuration_format_valid": True, "mail_configuration_ready": ready,
            "mail_enabled": settings.mail_enabled,
            "support_receiving_verified": settings.mail_support_verified,
            "missing_fields": missing, "database_schema_verified": False,
            "provider_connectivity_verified": False, "production_ready": False,
        }, settings
    except (OSError, ValueError, ValidationError):
        return {"configuration_format_valid": False, "mail_configuration_ready": False,
                "error": "MAIL_TEST_CONFIGURATION_INVALID"}, None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8024)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    report, settings = preflight(args.env_file)
    if args.check:
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["mail_configuration_ready"] else 2)
    if settings is None or (settings.mail_enabled and not report["mail_configuration_ready"]):
        print(json.dumps(report, indent=2))
        raise SystemExit(2)
    # Disabled is safe for preparing/probing the callback listener before provider setup.
    uvicorn.run(create_mail_hook_app(settings), host="127.0.0.1", port=args.port,
                access_log=False, proxy_headers=False, log_level="warning")


if __name__ == "__main__":
    main()
