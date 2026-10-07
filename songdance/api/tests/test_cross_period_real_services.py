"""Opt-in cross-period attempt fencing against disposable PostgreSQL, without a real model."""

import os

import pytest

from tests.test_auth_real_services import postgres as postgres
from tests.test_cross_period_jobs import assert_late_attempt_cannot_settle_new_period
from tests.test_cross_period_jobs import period_clock as period_clock
from tests.test_dispatch_real_services import client as client
from tests.test_dispatch_real_services import database as database

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases are never used",
)


@pytest.mark.parametrize("plan", ["free", "pro"])
def test_postgres_late_worker_cannot_settle_cross_period_retry(
    client, period_clock, monkeypatch, plan
):
    assert_late_attempt_cannot_settle_new_period(client, period_clock, monkeypatch, plan)
