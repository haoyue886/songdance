import io
import math
import struct
import wave
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from app.settings import Settings


def wav_bytes(
    duration: float = 2.0,
    sample_rate: int = 8_000,
    frequency: float | None = None,
) -> bytes:
    frames = int(duration * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        if frequency is None:
            output.writeframes(b"\x00\x00" * frames)
        else:
            output.writeframes(
                b"".join(
                    struct.pack(
                        "<h", round(math.sin(2 * math.pi * frequency * index / sample_rate) * 8_000)
                    )
                    for index in range(frames)
                )
            )
    return buffer.getvalue()


@dataclass
class RecordingQueue:
    calls: list[tuple[str, int]] = field(default_factory=list)
    error: Exception | None = None

    def enqueue(self, job_id: str, attempt: int) -> str:
        if self.error is not None:
            raise self.error
        self.calls.append((job_id, attempt))
        return f"queued:{job_id}:{attempt}"


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[tuple[TestClient, RecordingQueue, Path]]:
    database_path = tmp_path / "jobs.sqlite3"
    storage_path = tmp_path / "storage"
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{database_path}",
        storage_backend="local",
        local_storage_path=storage_path,
        temp_path=tmp_path / "tmp",
        auto_create_schema=True,
        hourly_job_limit=100,
        client_active_job_limit=100,
        global_active_job_limit=100,
        daily_job_limit=1000,
    )
    queue = RecordingQueue()
    app = create_app(
        settings=settings,
        storage=LocalObjectStorage(storage_path),
        job_queue=queue,
        job_quota=MemoryJobQuota(settings),
    )
    with TestClient(app) as client:
        yield client, queue, storage_path
    app.state.engine.dispose()
