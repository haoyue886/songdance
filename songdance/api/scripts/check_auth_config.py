"""Offline auth configuration check; explicit file only, never prints secrets."""

from app.services.auth_config import check, main, read_env

__all__ = ["check", "read_env"]

if __name__ == "__main__":
    main()
