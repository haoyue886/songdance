"""Process existing deletion requests even while new account deletions are disabled."""

import argparse
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import create_db_engine, create_session_factory
from app.models import AccountDeletion
from app.observability import configure_logging, log_event
from app.services.account_deletion import process_account_deletions
from app.services.creem_client import CreemClient
from app.services.quota import create_job_quota
from app.services.storage import create_storage
from app.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Process SongDance account deletion requests")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    parser.add_argument("--replay-id", help="Retry a reviewed deletion; use --replay-id=ID")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    storage = create_storage(settings)
    quota = create_job_quota(settings)
    provider = CreemClient(settings) if settings.creem_enabled else None
    try:
        if args.replay_id:
            with factory.begin() as session:
                row = session.scalar(
                    select(AccountDeletion)
                    .where(AccountDeletion.id == args.replay_id)
                    .with_for_update()
                )
                if row is None or row.status != "review":
                    raise SystemExit("Reviewed deletion request not found")
                row.status, row.error_code, row.next_attempt_at = "pending", None, datetime.now(UTC)
                row.retry_failures = 0
        while True:
            handled = process_account_deletions(factory, storage, settings, provider, quota)
            log_event("account_deletion_cycle", handled=handled)
            if not args.loop:
                break
            time.sleep(15)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
