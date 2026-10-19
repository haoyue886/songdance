"""Opt-in local JWT/PG integration; no hosted identities or payment provider calls."""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.main import create_app
from app.models import AuthIdentity, BillingAccount, TranscriptionJob, User
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from tests import test_auth_real_services as real_services
from tests.conftest import RecordingQueue
from tests.test_auth_ownership import auth_settings, create_job
from tests.test_creem_billing import FakeProvider

postgres = real_services.postgres

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable local PostgreSQL; no existing databases are used",
)


@pytest.mark.parametrize("postgres", ["songdance_auth"], indirect=True)
def test_same_email_unconfirmed_identity_cannot_inherit_account_tasks_or_billing(
    postgres, tmp_path
):
    admin, reader = postgres
    api = Path(__file__).resolve().parents[1]
    subprocess.run(
        [str(api / ".venv/bin/alembic"), "upgrade", "head"], cwd=api,
        env={**os.environ, "SONGDANCE_DATABASE_URL": admin, "SONGDANCE_AUTH_ENABLED": "false"},
        check=True, capture_output=True,
    )
    settings = auth_settings(tmp_path).model_copy(update={
        "database_url": admin.replace("postgresql://", "postgresql+psycopg://"),
        "auth_session_database_url": SecretStr(reader),
        "auth_session_schema": "songdance_auth", "auto_create_schema": False,
        "creem_enabled": True, "billing_environment": "test",
        "creem_api_key": SecretStr("creem_test_offline"),
        "creem_webhook_secret": SecretStr("offline-webhook-secret-for-tests"),
        "creem_product_id": "prod_test",
        "creem_success_url": "http://localhost:3000/billing/return",
    })
    app = create_app(settings, LocalObjectStorage(settings.local_storage_path),
                     RecordingQueue(), MemoryJobQuota(settings))
    verifier = app.state.auth_verifier
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    # Only JWKS retrieval is local. JWT signature/claims, confirmation and session SQL are real.
    verifier.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(
        key=key.public_key()))
    provider = FakeProvider()
    app.state.creem_client = provider
    subjects = {label: uuid4() for label in ("owner", "same_email")}
    sessions = {label: uuid4() for label in subjects}
    email = "same@example.test"
    with psycopg.connect(admin) as connection:
        for label in subjects:
            connection.execute(
                "INSERT INTO auth.users(id,email_confirmed_at) VALUES(%s,%s)",
                (subjects[label], datetime.now(UTC) if label == "owner" else None),
            )
            connection.execute(
                "INSERT INTO auth.sessions VALUES(%s,%s,now(),now(),NULL)",
                (sessions[label], subjects[label]),
            )

    def token(label, **overrides):
        return jwt.encode({
            "iss": verifier.issuer, "aud": "authenticated", "role": "authenticated",
            "sub": str(subjects[label]), "session_id": str(sessions[label]),
            "exp": datetime.now(UTC) + timedelta(minutes=5), "email": email,
            # A signed assertion of verification cannot override the database confirmation gate.
            "email_verified": True, **overrides,
        }, key, algorithm="RS256")

    def headers(label, **overrides):
        return {"Authorization": "Bearer " + token(label, **overrides),
                "Origin": "http://localhost:3000"}

    try:
        with TestClient(app) as client:
            owner_headers = headers("owner")
            owner = client.get("/me", headers=owner_headers).json()
            owned = create_job(client, token("owner"))
            assert owned.status_code == 201
            owned_path = "/jobs/" + owned.json()["id"]
            guest = create_job(client)
            assert guest.status_code == 201
            guest_path = "/jobs/" + guest.json()["id"]
            capability = {"X-Job-Access": guest.json()["guest_access_token"]}
            with app.state.session_factory.begin() as session:
                session.add(BillingAccount(id=str(uuid4()), user_id=owner["id"],
                    environment="test", customer_id="cust_owner", blocked=False))
            original_billing = client.get("/billing/me", headers=owner_headers)
            assert original_billing.status_code == 200
            assert original_billing.json()["owner_id"] == owner["id"]
            assert original_billing.json()["portal_available"] is True

            def snapshot():
                with app.state.session_factory() as session:
                    return (
                        sorted((u.id, u.email, u.active) for u in session.scalars(select(User))),
                        sorted((i.issuer, i.subject, i.user_id)
                               for i in session.scalars(select(AuthIdentity))),
                        sorted((j.id, j.owner_user_id, j.guest_secret_hash, j.status)
                               for j in session.scalars(select(TranscriptionJob))),
                        sorted((b.user_id, b.customer_id)
                               for b in session.scalars(select(BillingAccount))),
                    )

            before = snapshot()
            unconfirmed = headers("same_email")
            cases = [
                ("GET", "/me", None), ("GET", "/billing/me", None),
                ("GET", owned_path, None), ("GET", guest_path, None),
                ("GET", owned_path + "/download-url/source", None),
                ("POST", owned_path + "/claim", None),
                ("POST", guest_path + "/claim", None),
                ("POST", owned_path + "/retry", None), ("DELETE", owned_path, None),
                ("POST", "/billing/portal", {}), ("POST", "/billing/checkout", {}),
            ]
            for method, path, body in cases:
                response = client.request(method, path, json=body, headers={
                    **unconfirmed, **capability, "Idempotency-Key": "same-email-preflight",
                })
                assert response.status_code == 401, (method, path, response.status_code)
                assert response.json()["detail"]["code"] == "AUTH_REVOKED"
            # The original subject cannot borrow the other subject's otherwise live session.
            assert client.get("/me", headers=headers("owner", session_id=str(
                sessions["same_email"]))).status_code == 401
            assert snapshot() == before
            assert provider.create_calls == provider.portal_calls == []
            assert client.get(guest_path, headers=capability).status_code == 200
            assert client.get(owned_path, headers=owner_headers).status_code == 200

            # Simulated confirmation changes only auth.users; it does not link business owners.
            with psycopg.connect(admin) as connection:
                connection.execute("UPDATE auth.users SET email_confirmed_at=now() WHERE id=%s",
                                   (subjects["same_email"],))
            confirmed = client.get("/me", headers=unconfirmed)
            assert confirmed.status_code == 200
            other = confirmed.json()
            assert other["email"] == owner["email"] == email and other["id"] != owner["id"]
            assert client.get(owned_path, headers=unconfirmed).status_code == 404
            assert client.post(owned_path + "/claim", headers=unconfirmed).status_code == 404
            assert client.post(guest_path + "/claim", headers=unconfirmed).status_code == 404
            billing = client.get("/billing/me", headers=unconfirmed)
            assert billing.status_code == 200 and billing.json()["owner_id"] == other["id"]
            assert billing.json()["portal_available"] is False
            portal = client.post("/billing/portal", headers=unconfirmed, json={})
            assert portal.status_code == 409
            assert portal.json()["detail"]["code"] == "BILLING_CUSTOMER_NOT_READY"
            assert provider.create_calls == provider.portal_calls == []
            changed_email = client.get("/me", headers=headers(
                "owner", email="changed@example.test"))
            assert changed_email.status_code == 200 and changed_email.json()["id"] == owner["id"]
            after = snapshot()
            assert len(after[0]) == len(after[1]) == 2
            assert after[2:] == before[2:]
            assert {row[1]: row[2] for row in after[1]} == {
                str(subjects["owner"]): owner["id"],
                str(subjects["same_email"]): other["id"],
            }
    finally:
        verifier.engine.dispose()
        app.state.engine.dispose()
