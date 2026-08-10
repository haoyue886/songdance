import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect


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
    engine.dispose()
