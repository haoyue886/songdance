"""Run one signed Test callback from an explicit private commercial env file."""

import argparse
import json
import stat
from pathlib import Path

import uvicorn
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.billing_hook import create_billing_hook_app
from app.services.commercial_config import KNOWN_FIELDS, SETTING_FIELDS, read_env
from app.settings import Settings


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
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError("PRIVATE_ENV_FILE_REQUIRED")
    values = read_env(path)
    if set(values) - KNOWN_FIELDS:
        raise ValueError("UNSUPPORTED_BILLING_SETTING")
    if (
        values.get("SONGDANCE_ENVIRONMENT") != "test"
        or values.get("SONGDANCE_BILLING_ENVIRONMENT") != "test"
        or values.get("SONGDANCE_AUTO_CREATE_SCHEMA") != "false"
        or not values.get("SONGDANCE_DATABASE_URL")
    ):
        raise ValueError("EXPLICIT_TEST_DATABASE_REQUIRED")
    return FileSettings(_env_file=None, **{
        SETTING_FIELDS[key]: value for key, value in values.items() if key in SETTING_FIELDS
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8025)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    try:
        settings = load_settings(args.env_file)
    except (OSError, ValueError):
        print(json.dumps({"error": "BILLING_TEST_CONFIGURATION_INVALID"}))
        raise SystemExit(2) from None
    uvicorn.run(create_billing_hook_app(settings), host="127.0.0.1", port=args.port,
                access_log=False, proxy_headers=False, log_level="warning")


if __name__ == "__main__":
    main()
