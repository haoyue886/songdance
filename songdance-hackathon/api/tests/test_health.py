import asyncio

import httpx

from app.main import app, create_app
from app.settings import Settings


def test_health_returns_service_status() -> None:
    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "songdance-api",
        "version": "0.3.0",
    }


def test_readiness_reports_dependency_state(monkeypatch, tmp_path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'ready.sqlite3'}",
        storage_backend="local",
        local_storage_path=tmp_path / "storage",
        temp_path=tmp_path / "tmp",
        auto_create_schema=True,
        quota_backend="memory",
    )
    test_app = create_app(settings=settings)
    monkeypatch.setattr(
        "app.main.check_readiness",
        lambda _settings: {"redis": True, "worker": False, "web": True},
    )

    async def request_ready() -> httpx.Response:
        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/ready")

    response = asyncio.run(request_ready())

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "components": {"redis": True, "worker": False, "web": True},
    }
    test_app.state.engine.dispose()
