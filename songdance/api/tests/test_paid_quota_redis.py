"""Opt-in paid quota checks using real Lua on a test-owned temporary Redis."""

import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import RedisError

from app.services.quota import QuotaExceeded, RedisJobQuota
from app.settings import Settings
from tests.test_auth_real_services import free_port

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to temporary Redis; no existing services are used",
)


@pytest.fixture(scope="module")
def temporary_redis(tmp_path_factory):
    if not shutil.which("redis-server"):
        pytest.skip("Redis binary unavailable")
    root = tmp_path_factory.mktemp("paid-quota-redis")
    port = free_port()
    process = subprocess.Popen(
        [
            "redis-server",
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--save",
            "",
            "--appendonly",
            "no",
            "--dir",
            str(root),
            "--loglevel",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"redis://127.0.0.1:{port}/0"
    redis = Redis.from_url(url)
    try:
        for _ in range(100):
            assert process.poll() is None, "Test-owned Redis exited during startup"
            try:
                if redis.ping():
                    # A port collision must not silently connect to an existing service.
                    assert redis.info("server")["process_id"] == process.pid
                    break
            except RedisError:
                time.sleep(0.05)
        else:
            pytest.fail("Test-owned Redis did not become ready")
        yield url
    finally:
        redis.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture
def quota_factory(temporary_redis, monkeypatch):
    # Keep all calls in one UTC hour/day without changing Redis's real expiration clock.
    monkeypatch.setattr(
        "app.services.quota.time",
        SimpleNamespace(time=lambda: 1_790_000_000, strftime=time.strftime, gmtime=time.gmtime),
    )
    instances = []

    def create(**overrides):
        settings = Settings(
            _env_file=None,
            **(
                {
                    "quota_backend": "redis",
                    "redis_url": temporary_redis,
                    "quota_namespace": uuid4().hex,
                    "hourly_job_limit": 1,
                    "paid_ip_hourly_job_limit": 3,
                    "client_active_job_limit": 1,
                    "global_active_job_limit": 8,
                    "daily_job_limit": 20,
                }
                | overrides
            ),
        )
        quota = RedisJobQuota(settings)
        instances.append(quota)
        return quota

    yield create
    for quota in instances:
        quota.redis.close()


def assert_blocked(quota, client_key, code, *, paid=True):
    with pytest.raises(QuotaExceeded) as error:
        quota.reserve(uuid4().hex, client_key, paid=paid)
    assert error.value.code == code
    assert error.value.retry_after > 0


def test_free_ip_exhaustion_does_not_block_multiple_paid_reservations(quota_factory):
    quota = quota_factory()
    quota.reserve(uuid4().hex, "shared-ip")
    assert_blocked(quota, "shared-ip", "HOURLY_LIMIT", paid=False)
    quota.reserve(uuid4().hex, "shared-ip", paid=True)
    quota.reserve(uuid4().hex, "shared-ip", paid=True)
    # Paid reservations did not replenish or replace the exhausted Free bucket.
    assert_blocked(quota, "shared-ip", "HOURLY_LIMIT", paid=False)


def test_paid_hourly_limit_is_atomic_independent_and_cancel_preserves_charge(quota_factory):
    quota = quota_factory(paid_ip_hourly_job_limit=1)
    other = quota_factory(
        quota_namespace=quota.settings.quota_namespace, paid_ip_hourly_job_limit=1
    )
    barrier = Barrier(2)
    job_ids = [uuid4().hex, uuid4().hex]

    def reserve(index):
        barrier.wait(timeout=5)
        try:
            [quota, other][index].reserve(job_ids[index], "shared-ip", paid=True)
            return True
        except QuotaExceeded as error:
            assert error.code == "IP_SECURITY_LIMIT"
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert sorted(results) == [False, True]
    quota.reserve(uuid4().hex, "shared-ip", paid=False)
    quota.reserve(uuid4().hex, "other-ip", paid=True)
    winner = job_ids[results.index(True)]
    quota.cancel(winner)
    quota.cancel(winner)
    assert_blocked(quota, "shared-ip", "IP_SECURITY_LIMIT")


@pytest.mark.parametrize("shared_ip", [False, True], ids=["different-ips", "same-ip"])
def test_paid_global_capacity_survives_client_limit_bypass(quota_factory, shared_ip):
    quota = quota_factory(global_active_job_limit=2, paid_ip_hourly_job_limit=10)
    first, second = uuid4().hex, uuid4().hex
    quota.reserve(first, "ip-a", paid=True)
    quota.reserve(second, "ip-a" if shared_ip else "ip-b", paid=True)
    client = "ip-a" if shared_ip else "ip-c"
    assert_blocked(quota, client, "GLOBAL_CAPACITY")
    quota.complete(first)
    quota.reserve(uuid4().hex, client, paid=True)
    assert_blocked(quota, "unused-ip", "GLOBAL_CAPACITY", paid=False)


def test_free_and_paid_share_global_capacity_and_cancel_releases_slot(quota_factory):
    quota = quota_factory(global_active_job_limit=2)
    free_job = uuid4().hex
    quota.reserve(free_job, "shared-ip")
    quota.reserve(uuid4().hex, "shared-ip", paid=True)
    assert_blocked(quota, "another-ip", "GLOBAL_CAPACITY")
    quota.cancel(free_job)
    quota.reserve(uuid4().hex, "another-ip", paid=True)
    assert_blocked(quota, "third-ip", "GLOBAL_CAPACITY")


def test_daily_capacity_is_shared_and_cancel_cannot_refund_it(quota_factory):
    quota = quota_factory(daily_job_limit=2, paid_ip_hourly_job_limit=10)
    free_job, paid_job = uuid4().hex, uuid4().hex
    quota.reserve(free_job, "free-ip")
    quota.complete(free_job)
    quota.reserve(paid_job, "paid-ip", paid=True)
    assert_blocked(quota, "other-paid-ip", "DAILY_CAPACITY")
    assert_blocked(quota, "other-free-ip", "DAILY_CAPACITY", paid=False)
    quota.cancel(paid_job)
    quota.cancel(paid_job)
    assert_blocked(quota, "other-paid-ip", "DAILY_CAPACITY")
    assert_blocked(quota, "other-free-ip", "DAILY_CAPACITY", paid=False)


def test_complete_releases_active_capacity_but_preserves_paid_hourly_charge(quota_factory):
    quota = quota_factory(paid_ip_hourly_job_limit=1, global_active_job_limit=1)
    job_id = uuid4().hex
    quota.reserve(job_id, "paid-ip", paid=True)
    quota.complete(job_id)
    quota.cancel(job_id)
    assert_blocked(quota, "paid-ip", "IP_SECURITY_LIMIT")
    quota.reserve(uuid4().hex, "different-ip", paid=True)
