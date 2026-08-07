import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.database import create_db_engine
from app.settings import Settings


def run_alembic(database_url: str, revision: str) -> None:
    environment = os.environ.copy()
    environment["SONGDANCE_DATABASE_URL"] = database_url
    subprocess.run(
        [".venv/bin/alembic", "upgrade" if revision == "head" else "downgrade", revision],
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
    }

    run_alembic(database_url, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_sqlite_engine_enables_concurrent_process_pragmas(tmp_path: Path) -> None:
    engine = create_db_engine(Settings(database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}"))

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
        assert connection.scalar(text("PRAGMA busy_timeout")) == 30_000

    engine.dispose()
