"""Run with --once (scheduler) or --loop (dedicated Test billing worker)."""

import argparse
import time

from sqlalchemy import select

from app.database import create_db_engine, create_session_factory
from app.models import BillingWebhookEvent
from app.observability import configure_logging, log_event
from app.services.billing_events import process_pending, reconcile_known
from app.services.creem_client import CreemClient
from app.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Process durable Creem Test events")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--replay-id", help="Local inbox ID to replay after correcting its cause")
    args = parser.parse_args()
    settings = get_settings()
    if (
        not settings.creem_enabled
        or settings.billing_environment != "test"
        or settings.environment == "production"
    ):
        raise SystemExit("Creem Test billing is not enabled")
    configure_logging()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    provider = CreemClient(settings)
    try:
        if args.replay_id:
            from datetime import UTC, datetime

            with factory() as session:
                row = session.scalar(
                    select(BillingWebhookEvent)
                    .where(
                        BillingWebhookEvent.id == args.replay_id,
                        BillingWebhookEvent.environment == "test",
                    )
                    .with_for_update()
                )
                if row is None:
                    raise SystemExit("Inbox record not found")
                row.status = "pending"
                row.next_attempt_at = datetime.now(UTC)
                session.commit()
        while True:
            count = process_pending(factory, provider)
            if args.reconcile:
                reconcile_known(factory, provider)
            log_event("billing_cycle", events=count)
            if not args.loop:
                break
            time.sleep(15)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
