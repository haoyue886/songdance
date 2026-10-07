"""Run with --once (scheduler) or --loop (dedicated Test billing worker)."""

import argparse
import time

from sqlalchemy import select

from app.database import create_db_engine, create_session_factory
from app.models import BillingCancellation, BillingWebhookEvent
from app.observability import configure_logging, log_event
from app.services.billing_cancellations import process_cancellations
from app.services.billing_events import process_pending, reconcile_known
from app.services.creem_client import CreemClient
from app.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Process durable Creem Test events")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--loop", action="store_true")
    mode.add_argument("--once", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--reconcile-interval", type=int, default=86400)
    parser.add_argument("--max-reconcile-pages", type=int, default=100)
    parser.add_argument("--replay-id", help="Local inbox ID to replay after correcting its cause")
    parser.add_argument(
        "--replay-cancellation-id", help="Retry a reviewed refund cancellation; use --option=ID"
    )
    args = parser.parse_args()
    if args.reconcile_interval < 60 or not 1 <= args.max_reconcile_pages <= 1000:
        parser.error("Reconciliation interval must be >=60s and pages must be 1-1000")
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
        if args.replay_cancellation_id:
            from datetime import UTC, datetime

            with factory.begin() as session:
                row = session.scalar(
                    select(BillingCancellation)
                    .where(
                        BillingCancellation.id == args.replay_cancellation_id,
                        BillingCancellation.environment == "test",
                    )
                    .with_for_update()
                )
                if row is None or row.status == "verified":
                    raise SystemExit("Cancellation not found or already verified")
                row.status = "pending"
                row.next_attempt_at = datetime.now(UTC)
        next_reconcile = 0.0
        while True:
            count = process_pending(factory, provider)
            reconcile_failed = False
            if args.reconcile and time.monotonic() >= next_reconcile:
                report = reconcile_known(factory, provider, max_pages=args.max_reconcile_pages)
                reconcile_failed = bool(
                    report["failed"] or report["scan_failed"] or not report["scan_complete"]
                )
                next_reconcile = time.monotonic() + args.reconcile_interval
                count += process_pending(factory, provider)
            cancellations = process_cancellations(factory, provider)
            log_event("billing_cycle", events=count, cancellations=cancellations)
            if not args.loop:
                if reconcile_failed:
                    raise SystemExit("Billing reconciliation was incomplete; inspect the report")
                break
            time.sleep(15)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
