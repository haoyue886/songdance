import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from contextlib import contextmanager

import requests
from cryptography.fernet import Fernet
from redis import Redis

from app.services.auth import auth_error
from app.settings import Settings


class AuthCoordinator:
    """Server-only OTP budgets and cross-instance refresh serialization."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.secret = settings.auth_bridge_secret.get_secret_value().encode()
        self.cipher = Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(b"refresh-cache:" + self.secret).digest())
        )
        self.redis = (
            Redis.from_url(str(settings.redis_url)) if settings.quota_backend == "redis" else None
        )
        self.memory: dict[str, tuple[float, object]] = {}
        self.mutex = threading.RLock()
        self.prefix = f"songdance:{settings.quota_namespace}:auth:"

    def digest(self, value: str) -> str:
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    @contextmanager
    def locked(self, key: str):
        lock = (
            self.redis.lock(self.prefix + "lock:" + key, timeout=30, blocking_timeout=5)
            if self.redis
            else self.mutex
        )
        with lock:
            yield

    def get(self, key: str):
        if self.redis:
            data = self.redis.get(self.prefix + key)
            return json.loads(data) if data else None
        entry = self.memory.get(key)
        if entry is None or entry[0] <= time.time():
            self.memory.pop(key, None)
            return None
        return entry[1]

    def put(self, key: str, value: object, ttl: int) -> None:
        if self.redis:
            self.redis.set(self.prefix + key, json.dumps(value), ex=ttl)
        else:
            self.memory[key] = (time.time() + ttl, value)

    def delete(self, key: str) -> None:
        if self.redis:
            self.redis.delete(self.prefix + key)
        else:
            self.memory.pop(key, None)

    def start_otp(self, email: str, client: str) -> dict[str, str]:
        email_key = self.digest(email)
        with self.locked("otp"):
            now = time.time()
            if self.get("cooldown:" + email_key):
                raise auth_error(429, "AUTH_RATE_LIMITED")
            budgets = [
                ("email:" + email_key, 5),
                ("ip:" + self.digest(client), 20),
                ("global", 100),
            ]
            history = {}
            for key, limit in budgets:
                entries = [stamp for stamp in (self.get(key) or []) if stamp > now - 3600]
                if len(entries) >= limit:
                    raise auth_error(429, "AUTH_RATE_LIMITED")
                history[key] = entries
            for key, entries in history.items():
                self.put(key, [*entries, now], 3600)
            self.put("cooldown:" + email_key, True, 60)
            challenge = secrets.token_urlsafe(32)
            self.put(
                "challenge:" + self.digest(challenge),
                {"email": email_key, "attempts": 0, "expires": now + 600},
                600,
            )
        return {"challenge": challenge}

    def attempt_otp(self, challenge: str, email: str, consume: bool = False) -> dict[str, bool]:
        key = "challenge:" + self.digest(challenge)
        with self.locked("otp"):
            item = self.get(key)
            if not item or item["email"] != self.digest(email) or item["expires"] <= time.time():
                raise auth_error()
            if consume:
                self.delete(key)
            else:
                if item["attempts"] >= 5:
                    raise auth_error(429, "AUTH_RATE_LIMITED")
                self.put(
                    key,
                    {**item, "attempts": item["attempts"] + 1},
                    max(1, int(item["expires"] - time.time())),
                )
        return {"ok": True}

    def refresh(self, refresh_token: str) -> dict:
        key = "refresh:" + self.digest(refresh_token)
        with self.locked(key):
            cached = self.get(key)
            if cached:
                return json.loads(self.cipher.decrypt(cached.encode()))
            try:
                response = requests.post(
                    self.settings.supabase_url.rstrip("/") + "/auth/v1/token",
                    params={"grant_type": "refresh_token"},
                    headers={"apikey": self.settings.supabase_publishable_key.get_secret_value()},
                    json={"refresh_token": refresh_token},
                    timeout=(5, 8),
                    allow_redirects=False,
                )
                if response.status_code >= 500:
                    raise auth_error(503, "AUTH_UNAVAILABLE")
                if response.status_code != 200:
                    raise auth_error(401, "AUTH_REFRESH_FAILED")
                payload = response.json()
                if not isinstance(payload, dict) or any(
                    not isinstance(payload.get(field), str)
                    or not 1 <= len(payload[field]) <= 16_384
                    for field in ("access_token", "refresh_token")
                ):
                    raise auth_error(503, "AUTH_UNAVAILABLE")
            except (requests.RequestException, ValueError):
                raise auth_error(503, "AUTH_UNAVAILABLE") from None
            encrypted = self.cipher.encrypt(json.dumps(payload).encode()).decode()
            self.put(key, encrypted, 10)
            return payload
