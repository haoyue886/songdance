from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuthIdentity, TranscriptionJob, User
from app.services.auth import SupabaseVerifier, VerifiedIdentity, auth_error
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from app.settings import Settings
from tests.conftest import RecordingQueue, wav_bytes


def auth_settings(tmp_path):
    return Settings(
        _env_file=None,
        environment="test",
        auth_enabled=True,
        quota_backend="memory",
        supabase_url="https://auth.example",
        supabase_publishable_key="sb_publishable_test",
        auth_bridge_secret="a-test-bridge-secret-with-more-than-32-characters",
        auth_session_database_url="postgresql://session_reader:test@auth.example/postgres",
        database_url=f"sqlite:///{tmp_path / 'auth.sqlite3'}",
        auto_create_schema=True,
        local_storage_path=tmp_path / "storage",
        temp_path=tmp_path / "temp",
        hourly_job_limit=100,
        client_active_job_limit=100,
        global_active_job_limit=100,
    )


@dataclass
class FakeVerifier:
    subjects: dict[str, str]

    def verify(self, token):
        if token not in self.subjects:
            raise auth_error()
        return VerifiedIdentity(
            "https://auth.example/auth/v1", self.subjects[token], "same@example.test"
        )


@pytest.fixture
def protected_client(tmp_path):
    settings = auth_settings(tmp_path)
    app = create_app(
        settings,
        storage=LocalObjectStorage(settings.local_storage_path),
        job_queue=RecordingQueue(),
        job_quota=MemoryJobQuota(settings),
    )
    verifier = app.state.auth_verifier
    app.state.auth_verifier = FakeVerifier({"alice": str(uuid4()), "bob": str(uuid4())})
    with TestClient(app) as client:
        yield client
    app.state.engine.dispose()
    verifier.engine.dispose()


def create_job(client, token=None):
    return client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"} if token else {},
        files={"audio_file": ("sample.wav", wav_bytes(), "audio/wav")},
        data={"start_sec": "0", "end_sec": "2", "rights_confirmed": "true", "user_id": "spoof"},
    )


def test_owner_is_server_derived_and_every_control_route_rejects_other_users(protected_client):
    client = protected_client
    created = create_job(client, "alice")
    assert created.status_code == 201
    job = created.json()
    assert job["access_type"] == "owned" and job["guest_access_token"] is None
    owner = {"Authorization": "Bearer alice"}
    other = {"Authorization": "Bearer bob"}
    path = f"/jobs/{job['id']}"
    assert client.get(path, headers=owner).status_code == 200
    assert client.get(path).status_code == 404
    assert client.get(path, headers=other).status_code == 404
    assert client.post(path + "/retry", headers=other).status_code == 404
    assert client.delete(path, headers=other).status_code == 404
    assert client.get(path + "/download-url/source", headers=other).status_code == 404
    assert (
        client.post(
            "/events",
            headers=other,
            json={"event_name": "playback_started", "job_id": job["id"], "properties": {}},
        ).status_code
        == 404
    )
    ticket = client.get(path + "/download-url/source", headers=owner).json()["path"]
    assert client.get(ticket).status_code == 200
    assert client.delete(path, headers=owner).status_code == 204
    assert client.get(ticket).status_code == 404


def test_guest_needs_separate_secret_and_claim_is_exclusive(protected_client):
    client = protected_client
    job = create_job(client).json()
    path = f"/jobs/{job['id']}"
    guest = {"X-Job-Access": job["guest_access_token"]}
    assert job["access_type"] == "guest"
    assert client.get(path).status_code == 404
    assert client.get(path, headers=guest).status_code == 200
    assert client.get(path, headers=guest).json()["guest_access_token"] is None
    event = {"event_name": "result_viewed", "job_id": job["id"], "properties": {"view": "score"}}
    assert client.post("/events", json=event).status_code == 404
    assert (
        client.post("/events", headers={"X-Job-Access": "wrong" * 8}, json=event).status_code == 404
    )
    assert client.post("/events", headers=guest, json=event).status_code == 202
    assert (
        client.post(path + "/claim", headers={"Authorization": "Bearer alice"}).status_code == 404
    )
    first = client.post(path + "/claim", headers={**guest, "Authorization": "Bearer alice"})
    assert first.status_code == 200 and first.json()["access_type"] == "owned"
    assert first.json()["expires_at"] == job["expires_at"]
    assert client.get(path, headers=guest).status_code == 404
    assert (
        client.post(path + "/claim", headers={**guest, "Authorization": "Bearer bob"}).status_code
        == 404
    )
    assert (
        client.post(path + "/claim", headers={"Authorization": "Bearer alice"}).status_code == 200
    )


def test_bad_bearer_never_becomes_a_guest_and_email_does_not_merge_users(protected_client):
    client = protected_client
    assert create_job(client, "forged").status_code == 401
    alice = client.get("/me", headers={"Authorization": "Bearer alice"}).json()
    bob = client.get("/me", headers={"Authorization": "Bearer bob"}).json()
    assert alice["email"] == bob["email"] and alice["id"] != bob["id"]
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(AuthIdentity)).all()) == 2
        assert not session.scalars(select(TranscriptionJob)).all()
        session.get(User, alice["id"]).active = False
        session.commit()
    assert client.get("/me", headers={"Authorization": "Bearer alice"}).status_code == 403
    assert client.get("/me").status_code == 401


def test_legacy_tasks_remain_readable_but_cannot_be_claimed_by_job_id(protected_client):
    client = protected_client
    client.app.state.settings.auth_enabled = False
    job = create_job(client).json()
    client.app.state.settings.auth_enabled = True
    assert client.get(f"/jobs/{job['id']}").status_code == 200
    assert (
        client.post(
            f"/jobs/{job['id']}/claim", headers={"Authorization": "Bearer alice"}
        ).status_code
        == 404
    )


@pytest.fixture
def signed_verifier(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = SupabaseVerifier(auth_settings(tmp_path))
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key())
    )
    verifier.session_active = lambda subject, session_id: True
    claims = {
        "iss": verifier.issuer,
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "sub": str(uuid4()),
        "session_id": str(uuid4()),
        "role": "authenticated",
        "email": "a@example.test",
    }
    yield verifier, private_key, claims
    verifier.engine.dispose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("iss", "https://wrong.example"),
        ("aud", "wrong"),
        ("exp", 1),
        ("role", "service_role"),
        ("sub", "not-a-uuid"),
        ("session_id", ""),
        ("session_id", 123),
        ("session_id", []),
    ],
)
def test_jwt_signature_claims_are_required_before_session_lookup(signed_verifier, field, value):
    verifier, key, claims = signed_verifier
    token = jwt.encode({**claims, field: value}, key, algorithm="RS256")
    with pytest.raises(HTTPException) as error:
        verifier.verify(token)
    assert error.value.status_code == 401


def test_valid_signature_does_not_bypass_revoked_session(signed_verifier):
    verifier, key, claims = signed_verifier
    token = jwt.encode(claims, key, algorithm="RS256")
    assert verifier.verify(token).subject == claims["sub"]
    verifier.session_active = lambda subject, session_id: False
    with pytest.raises(HTTPException) as error:
        verifier.verify(token)
    assert error.value.detail["code"] == "AUTH_REVOKED"


def test_wrong_signature_and_hmac_algorithm_are_rejected(signed_verifier):
    verifier, key, claims = signed_verifier
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for token in (
        jwt.encode(claims, wrong, algorithm="RS256"),
        jwt.encode(claims, "x" * 40, algorithm="HS256"),
    ):
        with pytest.raises(HTTPException):
            verifier.verify(token)
