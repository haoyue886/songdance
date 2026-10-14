"""Shared auth configuration validation; never connects or prints secrets."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*\Z")
URL_FIELDS = ("NEXT_PUBLIC_SITE_URL", "SONGDANCE_AUTH_API_URL", "SONGDANCE_SUPABASE_URL")
PUBLISHABLE_KEY = "SONGDANCE_SUPABASE_PUBLISHABLE_KEY"
SESSION_DSN = "SONGDANCE_AUTH_SESSION_DATABASE_URL"
DSN_QUERY_KEYS = frozenset({"sslmode", "sslrootcert", "connect_timeout", "application_name"})


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not KEY_PATTERN.fullmatch(key) or key in values:
            raise ValueError(f"INVALID_ENV_LINE_{number}")
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        if "$" in value or "`" in value:
            raise ValueError(f"UNSUPPORTED_EXPANSION_LINE_{number}")
        values[key] = value
    return values


def check(values: dict[str, str]) -> dict[str, object]:
    errors: list[dict[str, str]] = []

    def reject(field: str, code: str) -> None:
        errors.append({"field": field, "code": code})

    environment = values.get("SONGDANCE_ENVIRONMENT", "")
    if environment not in {"development", "test", "production"}:
        reject("SONGDANCE_ENVIRONMENT", "INVALID_ENVIRONMENT")
    production = environment == "production"
    if values.get("SONGDANCE_AUTH_SESSION_SCHEMA", "auth") not in {"auth", "songdance_auth"}:
        reject("SONGDANCE_AUTH_SESSION_SCHEMA", "EXPECTED_SESSION_SCHEMA")
    if values.get("SONGDANCE_AUTH_ENABLED") == "true":
        bridge = values.get("SONGDANCE_AUTH_BRIDGE_SECRET", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", bridge):
            reject("SONGDANCE_AUTH_BRIDGE_SECRET", "EXPECTED_SERVER_BRIDGE_SECRET")
    for field in URL_FIELDS:
        value = values.get(field, "")
        if not value:
            reject(field, "REQUIRED")
            continue
        try:
            url = urlsplit(value)
            port = url.port  # Force validation, without logging input on failure.
            local = url.hostname in {"localhost", "127.0.0.1", "::1"}
            allowed_scheme = url.scheme == "https" or (
                not production and local and url.scheme == "http"
            )
            valid = (
                allowed_scheme
                and bool(url.hostname)
                and not (production and local)
                and not url.username
                and not url.password
                and url.path in {"", "/"}
                and not url.query
                and not url.fragment
                and (port is None or 1 <= port <= 65535)
                and not any(character.isspace() for character in value)
            )
        except ValueError:
            valid = False
        if not valid:
            reject(field, "INVALID_ORIGIN")
    key = values.get(PUBLISHABLE_KEY, "")
    if not key:
        reject(PUBLISHABLE_KEY, "REQUIRED")
    elif not re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]+", key):
        reject(PUBLISHABLE_KEY, "EXPECTED_PUBLISHABLE_KEY")
    dsn = values.get(SESSION_DSN, "")
    if not dsn:
        reject(SESSION_DSN, "REQUIRED")
    else:
        try:
            url = urlsplit(dsn)
            query = parse_qs(url.query, keep_blank_values=True)
            valid = (
                url.scheme in {"postgresql", "postgresql+psycopg"}
                and bool(url.hostname)
                and bool(url.username)
                and bool(url.password)
                and url.path not in {"", "/"}
                and not url.fragment
                and unquote(url.username) not in {"postgres", "supabase_admin", "service_role"}
                and not unquote(url.username).startswith("postgres.")
                and (url.port is None or 1 <= url.port <= 65535)
                and set(query) <= DSN_QUERY_KEYS
                and all(len(items) == 1 and items[0] for items in query.values())
            )
            if production:
                valid = valid and query.get("sslmode") in (
                    ["require"],
                    ["verify-ca"],
                    ["verify-full"],
                )
        except ValueError:
            valid = False
        if not valid:
            reject(SESSION_DSN, "EXPECTED_SCOPED_TLS_POSTGRES_DSN")
    for field, value in values.items():
        if (
            field.startswith("NEXT_PUBLIC_")
            and value
            and (
                any(word in field for word in ("SECRET", "PASSWORD", "SERVICE_ROLE", "DATABASE"))
                or value.startswith("sb_secret_")
            )
        ):
            reject(field, "SERVER_CREDENTIAL_IN_PUBLIC_VARIABLE")
    return {
        "configuration_format_valid": not errors,
        "provider_connectivity_verified": False,
        "database_permissions_verified": False,
        "smtp_oauth_verified": False,
        "production_ready": False,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        values = read_env(args.env_file)
    except UnicodeError:
        print(
            json.dumps({"configuration_format_valid": False, "error": "ENV_FILE_INVALID_ENCODING"})
        )
        raise SystemExit(2) from None
    except OSError:
        print(json.dumps({"configuration_format_valid": False, "error": "ENV_FILE_UNREADABLE"}))
        raise SystemExit(2) from None
    except ValueError as error:
        print(json.dumps({"configuration_format_valid": False, "error": str(error)}))
        raise SystemExit(2) from None
    report = check(values)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["configuration_format_valid"] else 2)


if __name__ == "__main__":
    main()
