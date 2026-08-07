import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.settings import Settings

PIPELINE_DIR_PATTERN = re.compile(r"^pipeline-[A-Za-z0-9_-]{8}-[A-Za-z0-9_-]+$")
DOWNLOAD_FILE_PATTERN = re.compile(r"^[0-9a-f]{32}\.(?:json|mid|musicxml|wav)$")


@dataclass(frozen=True)
class TempCleanupResult:
    deleted: int
    failed: int


def cleanup_job_temp_files(settings: Settings, job_id: str) -> TempCleanupResult:
    root = settings.temp_path
    prefix = f"pipeline-{job_id[:8]}-"
    if not root.is_dir():
        return TempCleanupResult(0, 0)
    entries = [
        entry
        for entry in root.iterdir()
        if entry.name.startswith(prefix) and PIPELINE_DIR_PATTERN.fullmatch(entry.name)
    ]
    return _delete_entries(entries)


def cleanup_stale_temp_files(
    settings: Settings, *, now: datetime | None = None
) -> TempCleanupResult:
    root = settings.temp_path
    if not root.is_dir():
        return TempCleanupResult(0, 0)
    cutoff = (now or datetime.now(UTC)).timestamp() - settings.temp_file_ttl_seconds
    entries = [
        entry
        for entry in root.iterdir()
        if PIPELINE_DIR_PATTERN.fullmatch(entry.name) and _older_than(entry, cutoff)
    ]
    downloads = root / "downloads"
    if downloads.is_dir():
        entries.extend(
            entry
            for entry in downloads.iterdir()
            if DOWNLOAD_FILE_PATTERN.fullmatch(entry.name) and _older_than(entry, cutoff)
        )
    return _delete_entries(entries)


def _older_than(path: Path, cutoff: float) -> bool:
    try:
        return path.lstat().st_mtime <= cutoff
    except OSError:
        return False


def _delete_entries(entries: list[Path]) -> TempCleanupResult:
    deleted = 0
    failed = 0
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_dir():
                entry.unlink(missing_ok=True)
            else:
                shutil.rmtree(entry)
            deleted += 1
        except OSError:
            failed += 1
    return TempCleanupResult(deleted, failed)
