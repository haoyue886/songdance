"""Local signed JWT/PG isolation of two synthetic paid customer bindings."""

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
from app.models import BillingAccount, PaidPeriod, UsagePeriod
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from app.settings import Settings
from tests import test_auth_real_services as real_services
from tests.conftest import RecordingQueue
from tests.test_auth_ownership import auth_settings
from tests.test_creem_billing import FakeProvider
from tests.test_entitlements import grant

postgres = real_services.postgres
pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; payment provider stays offline",
)


@pytest.mark.parametrize("postgres", ["songdance_auth"], indirect=True)
def test_two_paid_customer_summaries_and_portals_stay_with_authenticated_owner(postgres, tmp_path):
    admin, reader = postgres
    api = Path(__file__).resolve().parents[1]
    subprocess.run([str(api / ".venv/bin/alembic"), "upgrade", "head"], cwd=api,
        env={**os.environ, "SONGDANCE_DATABASE_URL": admin, "SONGDANCE_AUTH_ENABLED": "false"},
        check=True, capture_output=True)
    settings = Settings(_env_file=None, **{
        **auth_settings(tmp_path).model_dump(),
        "database_url": admin.replace("postgresql://", "postgresql+psycopg://"),
        "auth_session_database_url": SecretStr(reader), "auth_session_schema": "songdance_auth",
        "auto_create_schema": False, "usage_enabled": True, "paid_usage_enabled": True,
        "creem_enabled": True, "billing_environment": "test", "creem_product_id": "prod_test",
        "creem_api_key": SecretStr("creem_test_offline"),
        "creem_webhook_secret": SecretStr("offline-webhook-secret-for-tests"),
        "creem_success_url": "http://localhost:3000/billing/return",
    })
    app = create_app(settings, LocalObjectStorage(settings.local_storage_path),
                     RecordingQueue(), MemoryJobQuota(settings))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app.state.auth_verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))

    class TwoCustomerProvider(FakeProvider):
        def create_portal(self, customer_id):
            assert customer_id in {"cust_alice", "cust_bob"}
            self.portal_calls.append(customer_id)
            return {"customer_portal_link": "https://www.creem.io/test/portal/" + customer_id}

    provider = TwoCustomerProvider()
    app.state.creem_client = provider
    subjects = {label: (uuid4(), uuid4()) for label in ("alice", "bob")}
    with psycopg.connect(admin) as connection:
        for subject, sid in subjects.values():
            connection.execute("INSERT INTO auth.users(id,email_confirmed_at) VALUES(%s,now())",
                               (subject,))
            connection.execute("INSERT INTO auth.sessions VALUES(%s,%s,now(),now(),NULL)",
                               (sid, subject))
    headers = {label: {"Authorization": "Bearer " + jwt.encode({
        "iss": "https://auth.example/auth/v1", "aud": "authenticated", "role": "authenticated",
        "sub": str(subject), "session_id": str(sid), "email": "same@example.test",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }, key, algorithm="RS256"), "Origin": "http://localhost:3000"}
        for label, (subject, sid) in subjects.items()}

    def snapshot():
        with app.state.session_factory() as session:
            return (
                sorted((row.user_id, row.customer_id, row.blocked)
                       for row in session.scalars(select(BillingAccount))),
                sorted((row.user_id, row.transaction_id, row.status, row.usage_period_id)
                       for row in session.scalars(select(PaidPeriod))),
                sorted((row.user_id, row.consumed_units, row.reserved_units, row.limit_units)
                       for row in session.scalars(select(UsagePeriod))),
            )

    try:
        with TestClient(app) as client:
            owners = {}
            for label in subjects:
                who = client.get("/me", headers=headers[label])
                assert who.status_code == 200
                owners[label] = who.json()["id"]
            assert owners["alice"] != owners["bob"]
            consumed = {"alice": 15, "bob": 60}
            with app.state.session_factory.begin() as session:
                for label in subjects:
                    session.add(BillingAccount(id=uuid4().hex, user_id=owners[label],
                        customer_id="cust_"+label, environment="test", blocked=False))
                    paid = grant(session, owners[label], transaction_id="tx_"+label,
                                 subscription_id="sub_"+label)
                    session.get(UsagePeriod, paid.usage_period_id).consumed_units = consumed[label]
            before = snapshot()
            for label, other in (("alice", "bob"), ("bob", "alice")):
                summary = client.get("/billing/me", headers=headers[label])
                assert summary.status_code == 200
                data = summary.json()
                assert (data["owner_id"], data["plan"], data["used"], data["remaining"]) == (
                    owners[label], "pro", consumed[label], 1800-consumed[label])
                assert data["portal_available"] is True
                assert summary.headers["cache-control"] == "private, no-store"
                forged_query = {"user_id": owners[other], "customer_id": "cust_"+other}
                forged = client.get("/billing/me", headers=headers[label], params=forged_query)
                assert forged.status_code == 200 and forged.json() == data
                portal = client.post("/billing/portal", headers=headers[label], json={},
                                     params=forged_query)
                assert portal.status_code == 200
                assert portal.json()["url"].endswith("/cust_"+label)
                assert provider.portal_calls[-1] == "cust_"+label
                assert portal.headers["cache-control"] == "private, no-store"
                calls = list(provider.portal_calls)
                for body in ({"user_id": owners[other]}, {"customer_id": "cust_"+other}):
                    for path in ("/billing/portal", "/billing/checkout"):
                        response = client.post(path, headers={
                            **headers[label], "Idempotency-Key": "two-customer-isolation",
                        }, json=body)
                        assert response.status_code == 422
                        assert response.headers["cache-control"] == "private, no-store"
                assert provider.portal_calls == calls
            assert provider.portal_calls == ["cust_alice", "cust_bob"]
            assert provider.create_calls == []
            assert snapshot() == before
    finally:
        app.state.auth_verifier.engine.dispose()
        app.state.engine.dispose()
