import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


def run_alembic(database_url: str, revision: str, *, direction: str | None = None) -> None:
    environment = os.environ.copy()
    environment["SONGDANCE_DATABASE_URL"] = database_url
    environment["SONGDANCE_AUTH_ENABLED"] = "false"
    environment["SONGDANCE_USAGE_ENABLED"] = "false"
    environment["SONGDANCE_PAID_USAGE_ENABLED"] = "false"
    subprocess.run(
        [
            ".venv/bin/alembic",
            direction or ("upgrade" if revision == "head" else "downgrade"),
            revision,
        ],
        check=True,
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )


def test_alembic_upgrade_and_downgrade(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.sqlite3'}"
    run_alembic(database_url, "head")
    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "analytics_events",
        "artifacts",
        "source_assets",
        "transcription_jobs",
        "transcription_quality_reports",
        "transcription_results",
        "users",
        "auth_identities",
        "usage_periods",
        "usage_ledger",
        "paid_periods",
        "billing_accounts",
        "checkout_sessions",
        "billing_subscriptions",
        "billing_webhook_events",
        "billing_cancellations",
        "job_dispatches",
        "job_submissions",
        "guest_trials",
        "guest_days",
        "guest_submissions",
        "guest_ledger",
    }
    source_asset_columns = {
        column["name"] for column in inspect(engine).get_columns("source_assets")
    }
    assert "original_filename" in source_asset_columns

    run_alembic(database_url, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()


def test_008_refuses_to_rewrite_conflicting_terminal_history(tmp_path):
    url = f"sqlite:///{tmp_path / 'old-ledger.sqlite3'}"
    run_alembic(url, "007", direction="upgrade")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, active) VALUES ('u', 1)"))
            connection.execute(
                text(
                    "INSERT INTO usage_periods (id,user_id,entitlement_type,"
                    "period_key,period_start,"
                    "period_end,limit_units,reserved_units,consumed_units) "
                    "VALUES ('p','u','free_month','free:2026-10','2026-10-01','2026-11-01',1,0,1)"
                )
            )
            for event in ("reservation", "consume", "release"):
                connection.execute(
                    text(
                        "INSERT INTO usage_ledger "
                        "(id,period_id,user_id,reservation_id,event_type,units) "
                        "VALUES (:event,'p','u','r',:event,1)"
                    ),
                    {"event": event},
                )
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_alembic(url, "head")
        assert "audited reconciliation" in error.value.stderr
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM usage_ledger")) == 3
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "007"
    finally:
        engine.dispose()


def test_008_downgrade_refuses_to_drop_payment_history(tmp_path):
    from sqlalchemy.orm import Session

    from app.models import User
    from tests.test_entitlements import grant

    url = f"sqlite:///{tmp_path / 'paid-history.sqlite3'}"
    run_alembic(url, "head")
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            session.add(User(id="history-owner"))
            session.commit()
            grant(session, "history-owner")
            session.commit()
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_alembic(url, "007")
        assert "Cannot remove paid history" in error.value.stderr
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM paid_periods")) == 1
    finally:
        engine.dispose()
