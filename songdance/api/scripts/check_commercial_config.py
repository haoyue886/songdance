"""Offline commercial Test preflight; explicit file only, never prints secrets."""

from app.services.commercial_config import check, main, read_env

__all__ = ["check", "read_env"]

if __name__ == "__main__":
    main()
