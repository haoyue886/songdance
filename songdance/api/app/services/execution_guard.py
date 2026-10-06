"""Keep duplicate queue deliveries from running the same managed attempt concurrently."""

import hashlib
from contextlib import contextmanager

from sqlalchemy import Engine, text

from app.settings import Settings


@contextmanager
def execution_guard(engine: Engine, settings: Settings, job_id: str, attempt: int):
    digest = hashlib.sha256(f"execution:{job_id}:{attempt}".encode()).digest()
    if engine.dialect.name == "postgresql":
        key = int.from_bytes(digest[:8], "big", signed=True)
        # Separate session-level lock survives the pipeline's short transactions.
        with engine.connect() as connection:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            try:
                yield bool(acquired)
            finally:
                if acquired:
                    try:
                        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    except Exception:
                        connection.invalidate()
    elif engine.dialect.name == "sqlite":
        import fcntl

        # SQLite is a local development backend; lock files must never be unlinked
        # while another process might hold the same inode.
        directory = settings.temp_path / "execution-locks"
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / digest.hex()).open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                try:
                    yield True
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
    else:
        raise RuntimeError("Reliable dispatch requires PostgreSQL or local SQLite")
