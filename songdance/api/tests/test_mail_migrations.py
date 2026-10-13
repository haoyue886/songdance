import subprocess
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import Base, MailDelivery, MailEvent, MailSuppression, User
from tests.test_migrations import run_alembic

TABLES = {"mail_deliveries", "mail_events", "mail_suppressions"}


def test_upgrade_preserves_013_data_matches_models_and_empty_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'mail-migrations.sqlite3'}"
    run_alembic(url, "013", direction="upgrade")
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            session.add(User(id="legacy", email="retained@example.invalid"))
            session.commit()
        run_alembic(url, "head")
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={
                "compare_server_default": True,
                "include_object": lambda obj, name, kind, reflected, compare_to:
                    name in TABLES if kind == "table" else True,
            })
            assert compare_metadata(context, Base.metadata) == []
            assert connection.scalar(text("SELECT email FROM users")) == "retained@example.invalid"
        run_alembic(url, "013")
        assert not TABLES.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT email FROM users")) == "retained@example.invalid"
    finally:
        engine.dispose()


@pytest.mark.parametrize("table", sorted(TABLES))
def test_downgrade_preserves_every_mail_history_table(tmp_path, table):
    url = f"sqlite:///{tmp_path / 'mail-history.sqlite3'}"
    run_alembic(url, "head")
    engine = create_engine(url)
    now = datetime.now(UTC)
    rows = {
        "mail_deliveries": MailDelivery(
            id="d", request_digest="r", message_digest="m", recipient_digest="a",
            action="magiclink", next_attempt_at=now, expires_at=now,
        ),
        "mail_events": MailEvent(id="e", body_digest="b", event_type="email.delivered",
                                 provider_id="p", outcome="recorded"),
        "mail_suppressions": MailSuppression(id="s", reason="email.complained", event_id="e"),
    }
    try:
        with Session(engine) as session:
            session.add(rows[table])
            session.commit()
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_alembic(url, "013")
        assert "Cannot remove mail audit/suppression history" in error.value.stderr
        with engine.connect() as connection:
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "014"
        assert TABLES.issubset(inspect(engine).get_table_names())
    finally:
        engine.dispose()
