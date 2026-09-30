from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.auth_coordination import AuthCoordinator
from tests.test_auth_ownership import auth_settings
from tests.test_auth_ownership import protected_client as protected_client


def test_otp_budgets_and_one_time_challenge(tmp_path, monkeypatch):
    coordinator = AuthCoordinator(auth_settings(tmp_path))
    clock = [10000.0]
    monkeypatch.setattr("app.services.auth_coordination.time.time", lambda: clock[0])
    token = coordinator.start_otp("a@example.test", "127.0.0.1")["challenge"]
    with pytest.raises(HTTPException):
        coordinator.start_otp("a@example.test", "127.0.0.1")
    with pytest.raises(HTTPException):
        coordinator.attempt_otp(token, "other@example.test")
    for _ in range(5):
        coordinator.attempt_otp(token, "a@example.test")
    with pytest.raises(HTTPException):
        coordinator.attempt_otp(token, "a@example.test")
    coordinator.attempt_otp(token, "a@example.test", consume=True)
    with pytest.raises(HTTPException):
        coordinator.attempt_otp(token, "a@example.test")
    for _ in range(4):
        clock[0] += 61
        coordinator.start_otp("a@example.test", "127.0.0.1")
    clock[0] += 61
    with pytest.raises(HTTPException):
        coordinator.start_otp("a@example.test", "127.0.0.1")
    clock[0] += 3600
    fresh = coordinator.start_otp("a@example.test", "127.0.0.1")["challenge"]
    clock[0] += 601
    with pytest.raises(HTTPException):
        coordinator.attempt_otp(fresh, "a@example.test")


def test_concurrent_refresh_uses_one_upstream_request_and_encrypted_cache(tmp_path, monkeypatch):
    coordinator = AuthCoordinator(auth_settings(tmp_path))
    calls = []
    payload = {
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "expires_in": 3600,
    }

    def post(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: payload)

    monkeypatch.setattr("app.services.auth_coordination.requests.post", post)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(coordinator.refresh, ["old-refresh-secret"] * 4))
    assert results == [payload] * 4 and len(calls) == 1
    assert calls[0]["allow_redirects"] is False
    assert "refresh-secret" not in repr(coordinator.memory)
    assert "access-secret" not in repr(coordinator.memory)


def test_provider_failure_is_not_cached_or_reported_as_success(tmp_path, monkeypatch):
    coordinator = AuthCoordinator(auth_settings(tmp_path))
    monkeypatch.setattr(
        "app.services.auth_coordination.requests.post",
        lambda *a, **k: SimpleNamespace(status_code=401),
    )
    with pytest.raises(HTTPException) as error:
        coordinator.refresh("private-token")
    assert error.value.status_code == 401
    assert coordinator.memory == {}


def test_bridge_requires_server_secret_and_hides_invalid_payload(protected_client):
    # Reuse the isolated ownership fixture.
    client = protected_client
    secret = client.app.state.settings.auth_bridge_secret.get_secret_value()
    assert client.post("/auth/bridge/refresh", json={"refresh_token": "secret"}).status_code == 404
    result = client.post(
        "/auth/bridge/refresh",
        headers={"X-Auth-Bridge": secret},
        json={"refresh_token": {"secret": "NEVER_ECHO"}},
    )
    assert result.status_code == 400 and "NEVER_ECHO" not in result.text
