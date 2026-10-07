"""Disposable HTTP integration stack with real application, PostgreSQL, Redis and RQ."""

import argparse
import calendar
import hashlib
import hmac
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from uuid import uuid4

import jwt
import psycopg
import requests
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from redis import Redis
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

API_ROOT = Path(__file__).resolve().parents[2]
READER_SQL = API_ROOT.parent / "infra/supabase-session-reader.sql"
PUBLISHABLE_KEY = "sb_publishable_commercial_local"
PRODUCT_ID = "prod_commercial_local"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stop_group(process: subprocess.Popen) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def page(items: list[dict], number: int, size: int) -> dict:
    count = len(items)
    pages = (count + size - 1) // size
    return {
        "items": deepcopy(items[(number - 1) * size : number * size]),
        "pagination": {
            "total_records": count,
            "total_pages": pages,
            "current_page": number,
            "next_page": number + 1 if number < pages else None,
            "prev_page": number - 1 if number > 1 else None,
        },
    }


class CommercialStack:
    def __init__(self, root: Path, site: str, port: int):
        self.root = root.resolve()
        if (
            not self.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not self.root.name.startswith("songdance-commercial-")
            or (self.root / "cluster").exists()
        ):
            raise ValueError("A new commercial test temporary directory is required")
        self.origin = f"http://127.0.0.1:{port}"
        self.site = site
        self.secret = os.environ["SONGDANCE_COMMERCIAL_CONTROL_SECRET"]
        self.bridge = os.environ["SONGDANCE_COMMERCIAL_BRIDGE_SECRET"]
        if min(len(self.secret), len(self.bridge)) < 32:
            raise ValueError("Independent test control and bridge secrets are required")
        self.pg_started = False
        self.redis_process = None
        self.worker = None
        self.api = None
        self.resources = {"root": str(self.root), "stopped": False}
        self.save_resources()
        self.lock = RLock()
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.public_jwk.update(kid="commercial-local", use="sig", alg="RS256")
        self.auth_users: dict[str, dict] = {}
        self.refreshes: dict[str, tuple[str, str]] = {}
        self.codes: dict[str, tuple[str, str]] = {}
        self.google_email = "google@commercial.example.test"
        self.checkouts: dict[str, dict] = {}
        self.subscriptions: dict[str, dict] = {}
        self.transactions: dict[str, dict] = {}
        self.checkout_posts = 0
        self.cancel_posts = 0
        self.refresh_calls = 0
        self.webhook_posts = 0
        self.faults: set[str] = set()

    def save_resources(self) -> None:
        temporary = self.root / "resources.tmp"
        temporary.write_text(json.dumps(self.resources))
        temporary.chmod(0o600)
        temporary.replace(self.root / "resources.json")

    def start(self) -> None:
        pg_port, redis_port = free_port(), free_port()
        self.admin = f"postgresql://postgres@127.0.0.1:{pg_port}/postgres"
        cluster = self.root / "cluster"
        subprocess.run(
            ["initdb", "-D", str(cluster), "-U", "postgres", "-A", "trust", "--no-sync"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "pg_ctl",
                "-D",
                str(cluster),
                "-l",
                str(self.root / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {pg_port} -c unix_socket_directories=''",
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
        )
        self.pg_started = True
        self.resources["pg_started"] = True
        self.save_resources()
        with psycopg.connect(self.admin, autocommit=True) as connection:
            connection.execute("CREATE SCHEMA auth")
            connection.execute(
                "CREATE TABLE auth.users (id uuid PRIMARY KEY, email_confirmed_at timestamptz, "
                "banned_until timestamptz, deleted_at timestamptz, encrypted_password text)"
            )
            connection.execute(
                "CREATE TABLE auth.sessions (id uuid PRIMARY KEY, user_id uuid REFERENCES "
                "auth.users(id), created_at timestamptz, refreshed_at timestamptz, "
                "not_after timestamptz)"
            )
            connection.execute(READER_SQL.read_text())
            connection.execute("CREATE ROLE session_reader LOGIN")
            connection.execute("GRANT songdance_auth_reader TO session_reader")
            connection.execute("CREATE SCHEMA commercial_e2e")
            connection.execute(
                "CREATE TABLE commercial_e2e.model_calls (job_id text, attempt integer, "
                "source_hash text, created_at timestamptz DEFAULT now())"
            )
        self.redis_log = (self.root / "redis.log").open("wb")
        self.redis_process = subprocess.Popen(
            [
                "redis-server",
                "--bind",
                "127.0.0.1",
                "--port",
                str(redis_port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                str(self.root),
            ],
            stdout=self.redis_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.resources.update(redis_pid=self.redis_process.pid, redis_port=redis_port)
        self.save_resources()
        redis_url = f"redis://127.0.0.1:{redis_port}/0"
        client = Redis.from_url(redis_url, socket_connect_timeout=2)
        deadline = time.monotonic() + 10
        while True:
            try:
                client.ping()
                if client.info("server").get("process_id") != self.redis_process.pid:
                    raise RuntimeError("The temporary Redis port belongs to another process")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Temporary Redis startup failed") from None
                time.sleep(0.05)
        self.resources.update(
            redis_pid=self.redis_process.pid,
            redis_port=redis_port,
            redis_run_id=client.info("server")["run_id"],
        )
        self.save_resources()
        self.environment = {
            "SONGDANCE_ENVIRONMENT": "test",
            "SONGDANCE_CORS_ORIGINS": self.site,
            "SONGDANCE_DATABASE_URL": self.admin,
            "SONGDANCE_LOCAL_STORAGE_PATH": str(self.root / "storage"),
            "SONGDANCE_TEMP_PATH": str(self.root / "tmp"),
            "SONGDANCE_STORAGE_BACKEND": "local",
            "SONGDANCE_AUTO_CREATE_SCHEMA": "false",
            "SONGDANCE_REDIS_URL": redis_url,
            "SONGDANCE_QUOTA_BACKEND": "redis",
            "SONGDANCE_QUEUE_NAME": "commercial-" + self.root.name,
            "SONGDANCE_QUOTA_NAMESPACE": self.root.name,
            "SONGDANCE_DOWNLOAD_SIGNING_SECRET": secrets.token_hex(32),
            "SONGDANCE_AUTH_ENABLED": "true",
            "SONGDANCE_SUPABASE_URL": self.origin,
            "SONGDANCE_SUPABASE_PUBLISHABLE_KEY": PUBLISHABLE_KEY,
            "SONGDANCE_AUTH_BRIDGE_SECRET": self.bridge,
            "SONGDANCE_AUTH_SESSION_DATABASE_URL": self.admin.replace(
                "postgres@", "session_reader:test-only@"
            ),
            "SONGDANCE_USAGE_ENABLED": "true",
            "SONGDANCE_PAID_USAGE_ENABLED": "true",
            "SONGDANCE_RELIABLE_QUEUE_ENABLED": "true",
            "SONGDANCE_GUEST_USAGE_ENABLED": "true",
            "SONGDANCE_GUEST_SIGNING_SECRET": secrets.token_hex(32),
            "SONGDANCE_ACCOUNT_DELETION_ENABLED": "true",
            "SONGDANCE_CREEM_ENABLED": "true",
            "SONGDANCE_BILLING_ENVIRONMENT": "test",
            "SONGDANCE_CREEM_PRODUCT_ID": PRODUCT_ID,
            "SONGDANCE_CREEM_API_KEY": secrets.token_hex(32),
            "SONGDANCE_CREEM_WEBHOOK_SECRET": secrets.token_hex(32),
            "SONGDANCE_CREEM_SUCCESS_URL": self.site + "/billing/return",
            "SONGDANCE_HOURLY_JOB_LIMIT": "1000",
            "SONGDANCE_PAID_IP_HOURLY_JOB_LIMIT": "1000",
            "SONGDANCE_DAILY_JOB_LIMIT": "1000",
            "SONGDANCE_GLOBAL_ACTIVE_JOB_LIMIT": "100",
            "SONGDANCE_CLIENT_ACTIVE_JOB_LIMIT": "100",
            "SONGDANCE_FREE_MONTHLY_JOB_LIMIT": "1",
        }
        os.environ.update(self.environment)
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=API_ROOT,
            check=True,
            capture_output=True,
            env={**os.environ, **self.environment},
        )
        from app.main import app
        from app.services import creem_client

        # This override exists only in this disposable test process. Production
        # still uses the fixed Test URL and has no configurable provider endpoint.
        creem_client.API_BASE = self.origin + "/v1"
        self.api = app

    def stop(self) -> None:
        if self.worker:
            stop_group(self.worker)
        if self.api:
            self.api.state.engine.dispose()
            self.api.state.auth_verifier.engine.dispose()
        if self.redis_process:
            stop_group(self.redis_process)
            self.redis_log.close()
        if self.pg_started:
            subprocess.run(
                ["pg_ctl", "-D", str(self.root / "cluster"), "-m", "fast", "-w", "stop"],
                check=True,
                capture_output=True,
            )
        self.resources["stopped"] = True
        self.save_resources()

    def auth_user(self, email: str) -> dict:
        email = email.lower()
        if email not in self.auth_users:
            identifier = str(uuid4())
            self.auth_users[email] = {
                "id": identifier,
                "aud": "authenticated",
                "role": "authenticated",
                "email": email,
                "email_confirmed_at": datetime.now(UTC).isoformat(),
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "app_metadata": {"provider": "email", "providers": ["email", "google"]},
                "user_metadata": {},
                "identities": [],
            }
            with psycopg.connect(self.admin, autocommit=True) as connection:
                connection.execute(
                    "INSERT INTO auth.users (id,email_confirmed_at) VALUES (%s,now())",
                    (identifier,),
                )
        return self.auth_users[email]

    def mint_session(self, email: str, sid: str | None = None) -> dict:
        user = self.auth_user(email)
        if sid is None:
            sid = str(uuid4())
            with psycopg.connect(self.admin, autocommit=True) as connection:
                connection.execute(
                    "INSERT INTO auth.sessions (id,user_id,created_at,refreshed_at) "
                    "VALUES (%s,%s,now(),now())",
                    (sid, user["id"]),
                )
        else:
            with psycopg.connect(self.admin, autocommit=True) as connection:
                connection.execute(
                    "UPDATE auth.sessions SET refreshed_at=now() WHERE id=%s", (sid,)
                )
        now = int(datetime.now(UTC).timestamp())
        token = jwt.encode(
            {
                "iss": self.origin + "/auth/v1",
                "aud": "authenticated",
                "sub": user["id"],
                "session_id": sid,
                "role": "authenticated",
                "email": email,
                "iat": now,
                "exp": now + 3600,
            },
            self.key,
            algorithm="RS256",
            headers={"kid": "commercial-local"},
        )
        refresh = secrets.token_urlsafe(32)
        self.refreshes[refresh] = (email, sid)
        return {
            "access_token": token,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 3600,
            "expires_at": now + 3600,
            "user": deepcopy(user),
        }

    def token_user(self, token: str) -> tuple[dict, str]:
        try:
            value = jwt.decode(
                token,
                self.key.public_key(),
                algorithms=["RS256"],
                issuer=self.origin + "/auth/v1",
                audience="authenticated",
            )
            with psycopg.connect(self.admin) as connection:
                row = connection.execute(
                    "SELECT not_after FROM auth.sessions WHERE id=%s AND user_id=%s",
                    (value["session_id"], value["sub"]),
                ).fetchone()
            if row is None or (row[0] is not None and row[0] <= datetime.now(UTC)):
                raise ValueError()
            return self.auth_user(value["email"]), value["session_id"]
        except Exception:
            raise HTTPException(401, detail="Invalid local provider session") from None

    def product(self) -> dict:
        return {
            "id": PRODUCT_ID,
            "mode": "test",
            "price": 990,
            "currency": "USD",
            "billing_type": "recurring",
            "billing_period": "every-month",
        }

    def create_checkout(self, body: dict) -> dict:
        if body.get("product_id") != PRODUCT_ID or body.get("units") != 1:
            raise HTTPException(400)
        identifier = "ch_" + uuid4().hex
        customer = body.get("customer", {}).get("id") or "cust_" + uuid4().hex
        self.checkouts[identifier] = {
            "id": identifier,
            "mode": "test",
            "status": "pending",
            "request_id": body["request_id"],
            "product": PRODUCT_ID,
            "units": 1,
            "customer": customer,
            "subscription": "sub_" + uuid4().hex,
            "checkout_url": "https://www.creem.io/test/checkout/" + identifier,
            "success_url": body["success_url"],
        }
        self.checkout_posts += 1
        return deepcopy(self.checkouts[identifier])

    def complete_payment(self, checkout_id: str) -> dict:
        checkout = self.checkouts[checkout_id]
        if checkout["status"] != "completed":
            start = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=1)
            next_month = start.month % 12 + 1
            year = start.year + (start.month == 12)
            end = start.replace(
                year=year,
                month=next_month,
                day=min(start.day, calendar.monthrange(year, next_month)[1]),
            )
            tx_id = "tx_" + uuid4().hex
            self.subscriptions[checkout["subscription"]] = {
                "id": checkout["subscription"],
                "mode": "test",
                "customer": checkout["customer"],
                "product": PRODUCT_ID,
                "status": "active",
                "updated_at": start.isoformat(),
                "current_period_start_date": start.isoformat(),
                "current_period_end_date": end.isoformat(),
                "last_transaction_id": tx_id,
            }
            self.transactions[tx_id] = {
                "id": tx_id,
                "mode": "test",
                "subscription": checkout["subscription"],
                "customer": checkout["customer"],
                "type": "invoice",
                "status": "paid",
                "amount": 990,
                "amount_paid": 990,
                "currency": "USD",
                "period_start": int(start.timestamp() * 1000),
                "period_end": int(end.timestamp() * 1000),
            }
            checkout["status"] = "completed"
        return {
            "success_url": checkout["success_url"],
            "subscription_id": checkout["subscription"],
            "customer_id": checkout["customer"],
        }

    def deliver(self, checkout_id: str, kinds: list[str], duplicates: int = 1) -> dict:
        checkout = self.checkouts[checkout_id]
        delivered = []
        for kind in kinds:
            remote = (
                checkout
                if kind == "checkout.completed"
                else self.subscriptions[checkout["subscription"]]
            )
            body = json.dumps(
                {"id": "evt_" + uuid4().hex, "eventType": kind, "object": remote}
            ).encode()
            signature = hmac.new(
                self.environment["SONGDANCE_CREEM_WEBHOOK_SECRET"].encode(), body, hashlib.sha256
            ).hexdigest()
            for _ in range(duplicates):
                result = requests.post(
                    self.origin + "/webhooks/creem",
                    data=body,
                    headers={"creem-signature": signature, "Content-Type": "application/json"},
                    timeout=15,
                )
                result.raise_for_status()
                self.webhook_posts += 1
            delivered.append(kind)
        return {"delivered": delivered}

    def state(self) -> dict:
        from rq.job import Job

        from app.models import (
            AccountDeletion,
            AuthIdentity,
            BillingSubscription,
            BillingWebhookEvent,
            CheckoutSession,
            JobDispatch,
            PaidPeriod,
            TranscriptionJob,
            UsageLedger,
            UsagePeriod,
            User,
        )

        def rows(session, model, fields):
            return [
                {field: getattr(row, field) for field in fields}
                for row in session.scalars(select(model))
            ]

        with self.api.state.session_factory() as session:
            users = rows(session, User, ("id", "email", "active"))
            identities = session.scalars(select(AuthIdentity)).all()
            for user in users:
                user["owner_id"] = user["id"]
                user["auth_subject"] = next(
                    item.subject for item in identities if item.user_id == user["id"]
                )
            ledger = rows(
                session,
                UsageLedger,
                ("id", "user_id", "job_id", "reservation_id", "period_id", "event_type", "units"),
            )
            reservations = []
            for entry in ledger:
                if entry["event_type"] == "reservation":
                    events = [
                        row["event_type"]
                        for row in ledger
                        if row["reservation_id"] == entry["reservation_id"]
                    ]
                    reservations.append(
                        {
                            **entry,
                            "status": next(
                                (event for event in events if event in {"consume", "release"}),
                                "reserved",
                            ),
                        }
                    )
            jobs = rows(
                session,
                TranscriptionJob,
                (
                    "id",
                    "owner_user_id",
                    "status",
                    "stage",
                    "attempt_count",
                    "usage_reservation_id",
                    "error_code",
                ),
            )
            for row in jobs:
                job = session.get(TranscriptionJob, row["id"])
                row["owner_id"] = row["owner_user_id"]
                row["source_duration"] = job.source_asset.duration_sec if job.source_asset else None
                row["artifacts"] = [
                    {"type": item.type, "status": item.status} for item in job.artifacts
                ]
            result = {
                "users": users,
                "jobs": jobs,
                "ledger": ledger,
                "reservations": reservations,
                "periods": rows(
                    session,
                    UsagePeriod,
                    (
                        "id",
                        "user_id",
                        "entitlement_type",
                        "limit_units",
                        "reserved_units",
                        "consumed_units",
                    ),
                ),
                "paid_periods": rows(
                    session,
                    PaidPeriod,
                    ("id", "user_id", "transaction_id", "subscription_id", "status"),
                ),
                "checkouts": rows(
                    session, CheckoutSession, ("id", "user_id", "provider_id", "status")
                ),
                "subscriptions": rows(
                    session,
                    BillingSubscription,
                    ("id", "user_id", "provider_id", "customer_id", "status"),
                ),
                "deletions": rows(
                    session,
                    AccountDeletion,
                    ("id", "user_id", "status", "phase", "attempts", "retry_failures"),
                ),
                "events": rows(session, BillingWebhookEvent, ("event_type", "status", "attempts")),
            }
            dispatches = session.scalars(select(JobDispatch)).all()
        executions = 0
        from app.services.queue import queue_job_id

        for dispatch in dispatches:
            try:
                record = Job.fetch(
                    queue_job_id(dispatch.job_id, dispatch.attempt, self.api.state.settings),
                    connection=self.api.state.job_queue.queue.connection,
                )
                executions += record.meta.get("worker_execution_count", 0)
            except Exception:
                pass
        with psycopg.connect(self.admin) as connection:
            calls = connection.execute(
                "SELECT job_id,attempt,source_hash FROM commercial_e2e.model_calls"
            ).fetchall()
        result["model_calls"] = [
            {"job_id": row[0], "attempt": row[1], "source_hash": row[2]} for row in calls
        ]
        result["counts"] = {
            "model_calls": len(calls),
            "rq_executions": executions,
            "checkout_posts": self.checkout_posts,
            "cancel_posts": self.cancel_posts,
            "refresh_calls": self.refresh_calls,
            "webhook_posts": self.webhook_posts,
        }
        result["storage_files"] = [
            str(item.relative_to(self.root / "storage"))
            for item in (self.root / "storage").rglob("*")
            if item.is_file()
        ]
        result["temp_files"] = [
            str(item.relative_to(self.root / "tmp"))
            for item in (self.root / "tmp").rglob("*")
            if item.is_file()
        ]
        return result

    def control(self, body: dict) -> dict:
        from app.services.account_deletion import process_account_deletions
        from app.services.billing_cancellations import process_cancellations
        from app.services.billing_events import process_pending, reconcile_known
        from app.services.creem_client import CreemClient
        from app.services.dispatch import dispatch_pending

        action = body.get("action")
        if action == "state":
            return self.state()
        if action == "select_google_user":
            self.google_email = body["email"]
            return {"ok": True}
        if action == "complete_payment":
            return self.complete_payment(body["checkout_id"])
        if action == "deliver":
            return self.deliver(body["checkout_id"], body["event_types"], body.get("duplicates", 1))
        if action == "cancel_subscription":
            sub = self.subscriptions[body["subscription_id"]]
            sub.update(
                status="scheduled_cancel" if body.get("scheduled", True) else "canceled",
                updated_at=datetime.now(UTC).isoformat(),
            )
            if body.get("deliver", True):
                checkout = next(
                    item for item in self.checkouts.values() if item["subscription"] == sub["id"]
                )
                return self.deliver(checkout["id"], ["subscription." + sub["status"]])
            return {"ok": True}
        if action == "reactivate_subscription":
            sub = self.subscriptions[body["subscription_id"]]
            sub.update(status="active", updated_at=datetime.now(UTC).isoformat())
            if body.get("deliver", True):
                checkout = next(
                    item for item in self.checkouts.values() if item["subscription"] == sub["id"]
                )
                return self.deliver(checkout["id"], ["subscription.active"])
            return {"ok": True}
        if action == "provider_fault":
            if body.get("enabled", True):
                self.faults.add(body["kind"])
            else:
                self.faults.discard(body["kind"])
            return {"ok": True}
        if action == "billing_worker":
            provider = CreemClient(self.api.state.settings)
            handled = process_pending(self.api.state.session_factory, provider)
            cancellations = process_cancellations(self.api.state.session_factory, provider)
            return {"handled": handled, "cancellations": cancellations}
        if action == "reconcile":
            return reconcile_known(
                self.api.state.session_factory, CreemClient(self.api.state.settings)
            )
        if action == "delete_worker":
            provider = CreemClient(self.api.state.settings)
            return {
                "handled": process_account_deletions(
                    self.api.state.session_factory,
                    self.api.state.storage,
                    self.api.state.settings,
                    provider,
                    self.api.state.job_quota,
                )
            }
        if action == "transcription_worker":
            dispatch_pending(
                self.api.state.session_factory,
                self.api.state.settings,
                self.api.state.job_queue,
                self.api.state.storage,
                self.api.state.job_quota,
            )
            with (self.root / "worker.log").open("ab") as log:
                if self.worker is not None and self.worker.poll() is None:
                    raise HTTPException(409, detail="A test worker is already active")
                self.worker = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "tests.support.commercial_stack",
                        "--worker",
                        "--root",
                        str(self.root),
                    ],
                    cwd=API_ROOT,
                    env={**os.environ, **self.environment},
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                self.resources["worker_pid"] = self.worker.pid
                self.save_resources()
                try:
                    code = self.worker.wait(timeout=240)
                except subprocess.TimeoutExpired:
                    stop_group(self.worker)
                    raise HTTPException(503, detail="Test worker timeout") from None
                self.resources["worker_pid"] = None
                self.save_resources()
            if code:
                raise HTTPException(503, detail="Test worker failed")
            return {"exit_code": code, **self.state()["counts"]}
        raise HTTPException(400, detail="Unknown test action")

    def application(self) -> FastAPI:
        outer = FastAPI(docs_url=None)

        @outer.get("/auth/v1/.well-known/jwks.json")
        async def jwks():
            return {"keys": [self.public_jwk]}

        @outer.post("/auth/v1/otp")
        async def send_otp(request: Request):
            body = await request.json()
            self.auth_user(body["email"])
            return {}

        @outer.post("/auth/v1/verify")
        async def verify_otp(request: Request):
            body = await request.json()
            if body.get("token") != "123456":
                return JSONResponse({"msg": "Invalid code"}, status_code=400)
            return self.mint_session(body["email"])

        @outer.get("/auth/v1/authorize")
        async def authorize(request: Request):
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

            redirect = request.query_params["redirect_to"]
            if not redirect.startswith(self.site + "/api/auth/callback?"):
                raise HTTPException(400)
            code = secrets.token_urlsafe(24)
            self.codes[code] = (request.query_params["code_challenge"], self.google_email)
            parts = urlsplit(redirect)
            query = [*parse_qsl(parts.query), ("code", code)]
            return RedirectResponse(
                urlunsplit(parts._replace(query=urlencode(query))), status_code=302
            )

        @outer.post("/auth/v1/token")
        async def token(request: Request):
            import base64

            body = await request.json()
            if request.query_params.get("grant_type") == "refresh_token":
                old = self.refreshes.pop(body.get("refresh_token"), None)
                if old is None:
                    raise HTTPException(401)
                self.refresh_calls += 1
                return self.mint_session(*old)
            old = self.codes.pop(body.get("auth_code"), None)
            challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(body.get("code_verifier", "").encode()).digest()
                )
                .decode()
                .rstrip("=")
            )
            if old is None or challenge != old[0]:
                raise HTTPException(401)
            return self.mint_session(old[1])

        @outer.get("/auth/v1/user")
        async def provider_user(request: Request):
            user, _ = self.token_user(
                request.headers.get("authorization", "").removeprefix("Bearer ")
            )
            return user

        @outer.post("/auth/v1/logout")
        async def logout(request: Request):
            _, sid = self.token_user(
                request.headers.get("authorization", "").removeprefix("Bearer ")
            )
            with psycopg.connect(self.admin, autocommit=True) as connection:
                connection.execute("UPDATE auth.sessions SET not_after=now() WHERE id=%s", (sid,))
            for refresh, (_, value) in list(self.refreshes.items()):
                if value == sid:
                    del self.refreshes[refresh]
            return Response(status_code=204)

        @outer.api_route("/v1/{resource:path}", methods=["GET", "POST"])
        async def payment(resource: str, request: Request):
            if request.headers.get("x-api-key") != self.environment["SONGDANCE_CREEM_API_KEY"]:
                raise HTTPException(401)
            if "all" in self.faults or resource.split("/")[0] in self.faults:
                raise HTTPException(503)
            query = request.query_params
            with self.lock:
                if resource == "products":
                    return self.product()
                if resource == "checkouts":
                    if request.method == "POST":
                        return self.create_checkout(await request.json())
                    return deepcopy(self.checkouts[query["checkout_id"]])
                if resource == "subscriptions":
                    return deepcopy(self.subscriptions[query["subscription_id"]])
                if resource == "transactions":
                    return deepcopy(self.transactions[query["transaction_id"]])
                if resource == "transactions/search":
                    return page(
                        list(self.transactions.values()),
                        int(query.get("page_number", "1")),
                        int(query.get("page_size", "100")),
                    )
                if resource.startswith("subscriptions/") and resource.endswith("/cancel"):
                    body = await request.json()
                    if body != {"mode": "immediate"}:
                        raise HTTPException(400)
                    subscription = self.subscriptions[resource.split("/")[1]]
                    self.cancel_posts += 1
                    subscription.update(status="canceled", updated_at=datetime.now(UTC).isoformat())
                    return deepcopy(subscription)
                if resource == "customers/billing":
                    body = await request.json()
                    return {
                        "customer_portal_link": "https://www.creem.io/test/portal/"
                        + body["customer_id"]
                    }
                if resource.startswith("customers/") and resource.endswith("/subscriptions"):
                    customer = resource.split("/")[1]
                    items = [
                        row for row in self.subscriptions.values() if row["customer"] == customer
                    ]
                    return page(
                        items,
                        int(query.get("page_number", "1")),
                        int(query.get("page_size", "100")),
                    )
            raise HTTPException(404)

        @outer.post("/__commercial__/control")
        async def control(request: Request):
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not secrets.compare_digest(supplied.encode(), self.secret.encode()):
                raise HTTPException(404)
            body = await request.json()
            return await run_in_threadpool(self.control, body)

        outer.mount("/", self.api)
        return outer


def run_worker() -> None:
    hold_seconds = float(os.environ.get("SONGDANCE_COMMERCIAL_WORKER_HOLD_SECONDS", "0"))
    if not 0 <= hold_seconds <= 180:
        raise ValueError("Invalid worker lifecycle test hold")
    if hold_seconds:
        time.sleep(hold_seconds)
    from redis import Redis
    from rq import Queue, SimpleWorker, get_current_job

    from app.services import transcription
    from app.settings import get_settings

    real_transcribe = transcription.transcribe_audio

    def tracked(audio, **kwargs):
        job = get_current_job()
        with psycopg.connect(os.environ["SONGDANCE_DATABASE_URL"], autocommit=True) as connection:
            connection.execute(
                "INSERT INTO commercial_e2e.model_calls (job_id,attempt,source_hash) "
                "VALUES (%s,%s,%s)",
                (
                    job.meta["transcription_job_id"],
                    job.meta["attempt"],
                    hashlib.sha256(Path(audio).read_bytes()).hexdigest(),
                ),
            )
        return real_transcribe(audio, **kwargs)

    transcription.transcribe_audio = tracked
    settings = get_settings()
    connection = Redis.from_url(str(settings.redis_url))
    queue = Queue(settings.queue_name, connection=connection)
    SimpleWorker([queue], connection=connection).work(burst=True, with_scheduler=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--site-url")
    parser.add_argument("--port", type=int)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--cleanup-root", type=Path)
    args = parser.parse_args()
    if args.cleanup_root:
        cleanup_resources(args.cleanup_root)
        return
    if args.worker:
        run_worker()
        return
    if args.root is None or args.site_url is None or args.port is None:
        parser.error("root, site-url and port are required")
    stack = CommercialStack(args.root, args.site_url, args.port)
    interrupted = False

    def request_stop(_signal, _frame):
        nonlocal interrupted
        interrupted = True

    # Uvicorn replays captured signals after shutdown. A returning handler lets
    # the outer finally stop the independent PostgreSQL/Redis processes too.
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        stack.start()
        if interrupted:
            return
        print(
            json.dumps(
                {
                    "ready": True,
                    "api_origin": stack.origin,
                    "provider_origin": stack.origin,
                    "control_path": "/__commercial__/control",
                }
            ),
            flush=True,
        )
        uvicorn.run(
            stack.application(),
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=5,
        )
    finally:
        stack.stop()


def cleanup_resources(root: Path) -> None:
    root = root.resolve()
    if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not root.name.startswith(
        "songdance-commercial-"
    ):
        raise ValueError("A commercial test temporary directory is required")
    manifest_path = root / "resources.json"
    resources = (
        json.loads(manifest_path.read_text()) if manifest_path.exists() else {"root": str(root)}
    )
    if resources.get("root") != str(root):
        raise ValueError("Test resource ownership does not match")
    if resources.get("worker_pid"):
        stop_recorded_worker(resources["worker_pid"], root)
    if resources.get("redis_port"):
        connection = Redis(
            host="127.0.0.1",
            port=resources["redis_port"],
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            identity = connection.info("server")
        except Exception:
            identity = None
        if identity and (
            not resources.get("redis_run_id") or identity.get("run_id") == resources["redis_run_id"]
        ):
            if identity.get("process_id") != resources["redis_pid"]:
                raise ValueError("Temporary Redis process identity changed")
            configured = Path(connection.config_get("dir")["dir"]).resolve()
            if configured != root:
                raise ValueError("Temporary Redis directory ownership changed")
            connection.shutdown(nosave=True)
    cluster = root / "cluster"
    if (cluster / "postmaster.pid").exists():
        subprocess.run(
            ["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
            check=True,
            capture_output=True,
        )
    resources["stopped"] = True
    manifest_path.write_text(json.dumps(resources))
    manifest_path.chmod(0o600)
    print(json.dumps({"stopped": True}), flush=True)


def stop_recorded_worker(pid: int, root: Path) -> None:
    if type(pid) is not int or pid <= 1:
        raise ValueError("Invalid temporary worker identity")

    def active() -> bool:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat=,command="],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                raise RuntimeError("Temporary worker inspection permission was denied") from None
            raise RuntimeError("Temporary worker shutdown could not be verified")
        status, command = result.stdout.strip().split(maxsplit=1)
        if "Z" in status:
            return False
        expected = "tests.support.commercial_stack --worker --root " + str(root)
        if not command.endswith(expected) or os.getpgid(pid) != pid:
            raise ValueError("Temporary worker ownership does not match")
        return True

    if not active():
        return
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while active() and time.monotonic() < deadline:
        time.sleep(0.05)
    if active():
        os.killpg(pid, signal.SIGKILL)
        deadline = time.monotonic() + 5
        while active() and time.monotonic() < deadline:
            time.sleep(0.05)
    if active():
        raise RuntimeError("Temporary worker shutdown was not confirmed")


if __name__ == "__main__":
    main()
