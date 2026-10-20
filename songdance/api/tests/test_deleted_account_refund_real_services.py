"""Post-erasure payment reconciliation on disposable PG; suppliers remain offline."""

import os

import pytest

from tests.test_account_deletion_real_services import client as client
from tests.test_auth_real_services import postgres as postgres
from tests.test_creem_real_services import database as database
from tests.test_deleted_account_refund import (
    test_financial_event_after_deletion_updates_only_retained_grant as reconcile_existing,
)
from tests.test_deleted_account_refund import (
    test_new_payment_after_completed_deletion_cannot_create_a_new_period as rejects_new_period,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases and providers are never used",
)


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("status,kind,expected", [
    ("refunded", "refund.created", "revoked"),
    ("partialRefund", "refund.created", "active"),
    ("chargedBack", "dispute.created", "frozen"),
])
def test_post_erasure_verified_financial_facts_reconcile_on_postgres(
    client, completed, status, kind, expected
):
    reconcile_existing(
        (client, client.app.state.creem_client), completed, status, kind, expected,
    )


def test_post_erasure_new_period_is_rejected_on_postgres(client):
    rejects_new_period((client, client.app.state.creem_client))
