"""Offline commercial Test configuration preflight; never connects or prints values."""

import argparse
import json
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.services.auth_config import check as check_auth
from app.services.auth_config import read_env
from app.services.billing_plan import MAX_CLIP_SECONDS
from app.settings import Settings

SETTING_FIELDS = {"SONGDANCE_" + name.upper(): name for name in Settings.model_fields}
WEB_FIELDS = frozenset(
    {
        "NEXT_PUBLIC_API_URL",
        "NEXT_PUBLIC_SITE_URL",
        "NEXT_PUBLIC_AUTH_ENABLED",
        "NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION",
        "SONGDANCE_AUTH_API_URL",
    }
)
KNOWN_FIELDS = SETTING_FIELDS.keys() | WEB_FIELDS
AUTH_FLAG = "SONGDANCE_AUTH_ENABLED"
USAGE_FLAG = "SONGDANCE_USAGE_ENABLED"
QUEUE_FLAG = "SONGDANCE_RELIABLE_QUEUE_ENABLED"
PAID_FLAG = "SONGDANCE_PAID_USAGE_ENABLED"
FEATURE_FLAGS = {
    "authentication": (AUTH_FLAG, "NEXT_PUBLIC_AUTH_ENABLED"),
    "free_usage": (USAGE_FLAG,),
    "reliable_queue": (QUEUE_FLAG,),
    "paid_usage": (PAID_FLAG,),
    "guest_usage": ("SONGDANCE_GUEST_USAGE_ENABLED",),
    "creem_test": ("SONGDANCE_CREEM_ENABLED",),
    "account_deletion": ("SONGDANCE_ACCOUNT_DELETION_ENABLED",),
}
DEPENDENCIES = {
    "authentication": (),
    "free_usage": (AUTH_FLAG, QUEUE_FLAG),
    "reliable_queue": (AUTH_FLAG, USAGE_FLAG),
    "paid_usage": (AUTH_FLAG, USAGE_FLAG, QUEUE_FLAG),
    "guest_usage": (AUTH_FLAG, USAGE_FLAG, QUEUE_FLAG),
    "creem_test": (AUTH_FLAG, USAGE_FLAG, PAID_FLAG, QUEUE_FLAG),
    "account_deletion": (AUTH_FLAG, USAGE_FLAG, QUEUE_FLAG),
}
PRIVATE_FIELDS = frozenset(
    {
        "SONGDANCE_AUTH_BRIDGE_SECRET",
        "SONGDANCE_AUTH_SESSION_DATABASE_URL",
        "SONGDANCE_GUEST_SIGNING_SECRET",
        "SONGDANCE_DOWNLOAD_SIGNING_SECRET",
        "SONGDANCE_CREEM_API_KEY",
        "SONGDANCE_CREEM_WEBHOOK_SECRET",
        "SONGDANCE_S3_ACCESS_KEY",
        "SONGDANCE_S3_SECRET_KEY",
        "SONGDANCE_DATABASE_URL",
        "SONGDANCE_REDIS_URL",
    }
)


class _FileSettings(Settings):
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Do not mutate os.environ or let another source fill omitted file values.
        return (init_settings,)


def _diagnostic(field: str, code: str) -> dict[str, str]:
    return {"field": field if field in KNOWN_FIELDS else "ENV_FILE", "code": code}


def _add(errors: list[dict[str, str]], field: str, code: str) -> None:
    item = _diagnostic(field, code)
    if item not in errors:
        errors.append(item)


def _origin(value: str) -> str | None:
    try:
        url = urlsplit(value)
        port = url.port
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
            or (port is not None and not 1 <= port <= 65535)
            or any(character.isspace() for character in value)
        ):
            return None
        host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
        suffix = (
            f":{port}"
            if port is not None and port != {"http": 80, "https": 443}[url.scheme]
            else ""
        )
        return f"{url.scheme}://{host}{suffix}"
    except ValueError:
        return None


def _persistent_database(value: str) -> bool:
    if any(character.isspace() for character in value):
        return False
    try:
        url = urlsplit(value)
        if url.scheme == "sqlite":
            return (
                url.path not in {"", "/", "/:memory:"}
                and not url.netloc
                and not url.query
                and not url.fragment
            )
        return (
            url.scheme in {"postgres", "postgresql", "postgresql+psycopg"}
            and bool(url.hostname and url.username and url.password)
            and url.path not in {"", "/"}
            and not url.fragment
            and (url.port is None or 1 <= url.port <= 65535)
        )
    except ValueError:
        return False


def check(values: dict[str, str]) -> dict[str, object]:
    """Validate one explicit mapping, independent of process and dotenv sources."""
    errors: list[dict[str, str]] = []
    for field, value in values.items():
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            _add(errors, field, "CONTROL_CHARACTER")
        if field.startswith(("SONGDANCE_", "NEXT_PUBLIC_")) and field not in KNOWN_FIELDS:
            _add(errors, field, "UNSUPPORTED_SETTING")
    for flags in FEATURE_FLAGS.values():
        for flag in flags:
            if flag in values and values[flag] not in {"true", "false"}:
                _add(errors, flag, "EXPECTED_TRUE_OR_FALSE")

    auth_report = check_auth({**values, AUTH_FLAG: "true"})
    auth_errors = auth_report["errors"]
    for item in auth_errors:
        field = item["field"]
        if field == "SONGDANCE_ENVIRONMENT" or values.get(field):
            _add(errors, field, item["code"])

    try:
        settings = _FileSettings(
            _env_file=None,
            **{name: values[field] for field, name in SETTING_FIELDS.items() if field in values},
        )
    except ValidationError as error:
        settings = None
        for item in error.errors(include_input=False, include_context=False, include_url=False):
            name = item["loc"][0] if item["loc"] else None
            field = "SONGDANCE_" + name.upper() if name in Settings.model_fields else "ENV_FILE"
            _add(errors, field, "INVALID_SETTING" if name else "SETTINGS_CONSTRAINT")

    if values.get("SONGDANCE_FREE_MONTHLY_JOB_LIMIT", "1") != "1":
        _add(errors, "SONGDANCE_FREE_MONTHLY_JOB_LIMIT", "CURRENT_FREE_LIMIT_MUST_BE_ONE")
    if (
        AUTH_FLAG in values
        and "NEXT_PUBLIC_AUTH_ENABLED" in values
        and values[AUTH_FLAG] != values["NEXT_PUBLIC_AUTH_ENABLED"]
    ):
        _add(errors, "NEXT_PUBLIC_AUTH_ENABLED", "AUTH_FLAGS_MUST_MATCH")

    features: dict[str, dict[str, object]] = {}
    for feature, flags in FEATURE_FLAGS.items():
        feature_errors: list[dict[str, str]] = []
        for flag in flags:
            if values.get(flag) != "true":
                _add(feature_errors, flag, "FEATURE_DISABLED")
        for flag in DEPENDENCIES[feature]:
            if values.get(flag) != "true":
                _add(feature_errors, flag, "REQUIRES_ENABLED_DEPENDENCY")
        features[feature] = {
            "enabled": all(values.get(flag) == "true" for flag in flags),
            "errors": feature_errors,
        }

    authentication = features["authentication"]["errors"]
    for item in auth_errors:
        _add(authentication, item["field"], item["code"])
    site = _origin(values.get("NEXT_PUBLIC_SITE_URL", ""))
    api = _origin(values.get("SONGDANCE_AUTH_API_URL", ""))
    public_api = _origin(values.get("NEXT_PUBLIC_API_URL", ""))
    public_api_errors = check_auth(
        {**values, "SONGDANCE_AUTH_API_URL": values.get("NEXT_PUBLIC_API_URL", "")}
    )["errors"]
    if any(item["field"] == "SONGDANCE_AUTH_API_URL" for item in public_api_errors):
        public_api = None
    if not public_api:
        _add(authentication, "NEXT_PUBLIC_API_URL", "REQUIRED_API_ORIGIN")
        if values.get("NEXT_PUBLIC_API_URL"):
            _add(errors, "NEXT_PUBLIC_API_URL", "INVALID_ORIGIN")
    elif api and api != public_api:
        _add(authentication, "NEXT_PUBLIC_API_URL", "API_ORIGINS_MUST_MATCH")
        _add(errors, "NEXT_PUBLIC_API_URL", "API_ORIGINS_MUST_MATCH")
    cors = [_origin(item.strip()) for item in values.get("SONGDANCE_CORS_ORIGINS", "").split(",")]
    if not site or site not in cors:
        _add(authentication, "SONGDANCE_CORS_ORIGINS", "MUST_INCLUDE_SITE_ORIGIN")
        if values.get("SONGDANCE_CORS_ORIGINS") and site:
            _add(errors, "SONGDANCE_CORS_ORIGINS", "MUST_INCLUDE_SITE_ORIGIN")
    for field in ("SONGDANCE_REDIS_URL", "SONGDANCE_QUOTA_NAMESPACE"):
        if not values.get(field):
            _add(authentication, field, "REQUIRED")
    if values.get("SONGDANCE_QUOTA_BACKEND") != "redis":
        _add(authentication, "SONGDANCE_QUOTA_BACKEND", "EXPECTED_SHARED_REDIS_BACKEND")

    database = values.get("SONGDANCE_DATABASE_URL", "")
    database_valid = _persistent_database(database)
    if database and not database_valid:
        _add(errors, "SONGDANCE_DATABASE_URL", "EXPECTED_PERSISTENT_DATABASE_DSN")
    for feature in (
        "free_usage",
        "reliable_queue",
        "paid_usage",
        "guest_usage",
        "creem_test",
        "account_deletion",
    ):
        if not database_valid:
            _add(
                features[feature]["errors"],
                "SONGDANCE_DATABASE_URL",
                "EXPECTED_PERSISTENT_DATABASE_DSN" if database else "REQUIRED",
            )

    for feature, field in (
        ("reliable_queue", "SONGDANCE_DOWNLOAD_SIGNING_SECRET"),
        ("guest_usage", "SONGDANCE_GUEST_SIGNING_SECRET"),
    ):
        secret = values.get(field, "")
        valid_secret = bool(re.fullmatch(r"[A-Za-z0-9_-]{32,128}", secret)) and not (
            secret.startswith("replace-") or secret == "development-only-download-secret-change-me"
        )
        if not valid_secret:
            _add(features[feature]["errors"], field, "EXPECTED_RANDOM_SIGNING_SECRET")
            if secret:
                _add(errors, field, "EXPECTED_RANDOM_SIGNING_SECRET")
        elif secret in {
            values.get("SONGDANCE_AUTH_BRIDGE_SECRET"),
            values.get("SONGDANCE_GUEST_SIGNING_SECRET")
            if feature == "reliable_queue"
            else values.get("SONGDANCE_DOWNLOAD_SIGNING_SECRET"),
        }:
            _add(features[feature]["errors"], field, "EXPECTED_INDEPENDENT_SIGNING_SECRET")
            _add(errors, field, "EXPECTED_INDEPENDENT_SIGNING_SECRET")

    creem = features["creem_test"]["errors"]
    if values.get("SONGDANCE_ENVIRONMENT") not in {"development", "test"}:
        _add(creem, "SONGDANCE_ENVIRONMENT", "CREEM_TEST_ONLY")
    if values.get("SONGDANCE_BILLING_ENVIRONMENT") != "test":
        _add(creem, "SONGDANCE_BILLING_ENVIRONMENT", "CREEM_TEST_ONLY")
        if values.get("SONGDANCE_BILLING_ENVIRONMENT"):
            _add(errors, "SONGDANCE_BILLING_ENVIRONMENT", "CREEM_TEST_ONLY")
    for field in (
        "SONGDANCE_CREEM_API_KEY",
        "SONGDANCE_CREEM_WEBHOOK_SECRET",
        "SONGDANCE_CREEM_PRODUCT_ID",
        "SONGDANCE_CREEM_PLAN_VERSION",
    ):
        if not values.get(field, "").strip():
            _add(creem, field, "REQUIRED")
    if (
        values.get("SONGDANCE_CREEM_WEBHOOK_SECRET")
        and len(values["SONGDANCE_CREEM_WEBHOOK_SECRET"]) < 16
    ):
        _add(creem, "SONGDANCE_CREEM_WEBHOOK_SECRET", "EXPECTED_WEBHOOK_SECRET")
        _add(errors, "SONGDANCE_CREEM_WEBHOOK_SECRET", "EXPECTED_WEBHOOK_SECRET")
    product = values.get("SONGDANCE_CREEM_PRODUCT_ID", "")
    if product and (not re.fullmatch(r"prod_[A-Za-z0-9_-]+", product) or len(product) > 255):
        _add(creem, "SONGDANCE_CREEM_PRODUCT_ID", "EXPECTED_TEST_PRODUCT_ID")
        _add(errors, "SONGDANCE_CREEM_PRODUCT_ID", "EXPECTED_TEST_PRODUCT_ID")
    plan = values.get("SONGDANCE_CREEM_PLAN_VERSION", "")
    if plan and (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", plan)):
        _add(creem, "SONGDANCE_CREEM_PLAN_VERSION", "EXPECTED_PLAN_VERSION")
        _add(errors, "SONGDANCE_CREEM_PLAN_VERSION", "EXPECTED_PLAN_VERSION")
    success = values.get("SONGDANCE_CREEM_SUCCESS_URL", "")
    try:
        target = urlsplit(success)
        success_valid = (
            bool(site)
            and _origin(f"{target.scheme}://{target.netloc}") == site
            and target.path in {"/billing/return", "/account"}
            and not target.query
            and not target.fragment
            and not any(character.isspace() for character in success)
        )
    except ValueError:
        success_valid = False
    if not success_valid:
        _add(creem, "SONGDANCE_CREEM_SUCCESS_URL", "EXPECTED_SITE_BILLING_RETURN_URL")
        if success:
            _add(errors, "SONGDANCE_CREEM_SUCCESS_URL", "EXPECTED_SITE_BILLING_RETURN_URL")

    for feature in features.values():
        feature["prerequisites_configured"] = not errors and not any(
            item["code"] != "FEATURE_DISABLED" for item in feature["errors"]
        )
    return {
        "configuration_format_valid": not errors,
        "commercial_test_configuration_valid": settings is not None
        and not errors
        and all(not feature["errors"] for feature in features.values()),
        "features": features,
        "current_contract": {
            "free_monthly_successes": 1,
            "free_max_clip_seconds": 90,
            "pro_test_max_clip_seconds": MAX_CLIP_SECONDS,
            "guest_max_clip_seconds": 30,
            "live_supported": False,
        },
        "provider_connectivity_verified": False,
        "database_permissions_verified": False,
        "smtp_oauth_verified": False,
        "merchant_product_verified": False,
        "workers_running_verified": False,
        "production_ready": False,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        mode = args.env_file.stat().st_mode
        if not stat.S_ISREG(mode):
            raise OSError("not a regular file")
        values = read_env(args.env_file)
    except UnicodeError:
        failure = "ENV_FILE_INVALID_ENCODING"
    except OSError:
        failure = "ENV_FILE_UNREADABLE"
    except ValueError as error:
        code = str(error)
        failure = (
            code
            if re.fullmatch(r"(?:INVALID_ENV_LINE|UNSUPPORTED_EXPANSION_LINE)_[0-9]+", code)
            else "ENV_FILE_INVALID"
        )
    else:
        report = check(values)
        if mode & 0o077 and any(values.get(field) for field in PRIVATE_FIELDS):
            _add(report["errors"], "ENV_FILE", "ENV_FILE_PRIVATE_PERMISSIONS_REQUIRED")
            report["configuration_format_valid"] = False
            report["commercial_test_configuration_valid"] = False
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["commercial_test_configuration_valid"] else 2)
    print(json.dumps({"configuration_format_valid": False, "error": failure}))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
