"""Dedicated durable task dispatcher; database state survives process/Redis restarts."""

import argparse
import time

from app.database import create_db_engine, create_session_factory
from app.observability import configure_logging, log_event
from app.services.dispatch import dispatch_pending
from app.services.queue import create_job_queue
from app.services.quota import create_job_quota
from app.services.storage import create_storage
from app.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover durable task dispatches")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    queue, storage, quota = (
        create_job_queue(settings),
        create_storage(settings),
        create_job_quota(settings),
    )
    try:
        while True:
            log_event(
                "dispatch_cycle",
                processed=dispatch_pending(factory, settings, queue, storage, quota),
            )
            if not args.loop:
                break
            time.sleep(5)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
