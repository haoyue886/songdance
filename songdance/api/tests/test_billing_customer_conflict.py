"""A provider customer reused across identities must remain a review, not a merge."""

import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Barrier, Lock, get_ident

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select

from app.models import (
    AccountDeletion,
    BillingAccount,
    BillingSubscription,
    BillingWebhookEvent,
    CheckoutSession,
    PaidPeriod,
    User,
)
from app.services.account_deletion_billing import verify_stopped_billing
from app.services.billing import BillingMismatch, account_for, billing_state, create_checkout
from app.services.billing_events import reconcile_known, sync_checkout
from tests.test_account_deletion import (
    create_job,
    request_deletion,
)
from tests.test_account_deletion import (
    deletion_client as deletion_client,
)
from tests.test_account_deletion import (
    process as process_deletion,
)
from tests.test_auth_ownership import auth_settings
from tests.test_auth_real_services import postgres as postgres
from tests.test_creem_billing import (
    HEADERS,
    FakeProvider,
    event,
    pay,
    process,
)
from tests.test_creem_billing import (
    billing as billing,
)
from tests.test_creem_real_services import database as database
from tests.test_creem_real_services import owner

BOB = {**HEADERS, "Authorization": "Bearer bob", "Idempotency-Key": "bob_key_1"}


def second_checkout(client, *, during_create=None, headers=BOB):
    provider = FakeProvider()
    original = provider.create_checkout

    def create(**kwargs):
        original(**kwargs)
        provider.checkout.update(id="ch_bob", subscription="sub_bob")
        if during_create:
            during_create(provider)
        return deepcopy(provider.checkout)

    provider.create_checkout = create
    provider.get_checkout = lambda checkout_id: deepcopy(provider.checkout)
    provider.get_subscription = lambda sub_id: deepcopy(provider.subscription)
    provider.subscription.update(id="sub_bob", last_transaction_id="tx_bob")
    transaction = provider.transactions.pop("tx_test")
    transaction.update(id="tx_bob", subscription="sub_bob")
    provider.transactions["tx_bob"] = transaction
    client.app.state.creem_client = provider
    response = client.post("/billing/checkout", headers=headers, json={})
    assert response.status_code == 200
    if during_create:
        assert response.json()["sync_state"] == "review_required"
        assert response.json()["checkout_url"] is None
    provider.checkout["status"] = "completed"
    return provider, response.json()["id"]


def original_snapshot(factory):
    with factory() as session:
        return {
            model.__tablename__: [
                {column.name: getattr(row, column.name) for column in model.__table__.columns}
                for row in session.scalars(select(model).order_by(model.id))
            ]
            for model in (BillingAccount, BillingSubscription, PaidPeriod)
        }


def assert_review(client, checkout_id, snapshot):
    factory = client.app.state.session_factory
    with factory() as session:
        checkout = session.get(CheckoutSession, checkout_id)
        account = session.scalar(
            select(BillingAccount).where(BillingAccount.user_id == checkout.user_id)
        )
        assert account.blocked and account.customer_id is None
        assert checkout.status == "uncertain"
        assert checkout.error_code == "CUSTOMER_BINDING_CONFLICT"
        assert checkout.checkout_url is None
        assert billing_state(session, checkout.user_id)["sync_state"] == "review_required"
        assert billing_state(session, checkout.user_id)["portal_available"] is False
        assert not session.scalar(
            select(BillingSubscription.id).where(BillingSubscription.user_id == checkout.user_id)
        )
        assert not session.scalar(
            select(PaidPeriod.id).where(PaidPeriod.user_id == checkout.user_id)
        )
    current = original_snapshot(factory)
    for table, rows in snapshot.items():
        assert all(row in current[table] for row in rows)
    purchase = client.post("/billing/checkout", headers=BOB, json={})
    assert purchase.status_code == 409
    assert purchase.json()["detail"]["code"] == "BILLING_REVIEW_REQUIRED"


@pytest.mark.parametrize("projection", ["direct", "event", "reconcile"])
def test_colliding_customer_is_durable_review_and_preserves_original_owner(billing, projection):
    client, first = billing
    pay(client, first)
    factory = client.app.state.session_factory
    before = original_snapshot(factory)
    provider, checkout_id = second_checkout(client)
    if projection == "event":
        assert event(
            client, "checkout.completed", "evt_bob", {"id": "ch_bob", "mode": "test"}
        ).status_code == 200
        assert process(client, provider) == 1
        with factory() as session:
            row = session.scalar(
                select(BillingWebhookEvent).where(BillingWebhookEvent.event_id == "evt_bob")
            )
            assert (row.status, row.error_code) == ("review", "CUSTOMER_BINDING_CONFLICT")
    elif projection == "reconcile":
        combined = FakeProvider()
        combined.get_checkout = lambda reference: deepcopy(
            first.checkout if reference == "ch_test" else provider.checkout
        )
        combined.get_subscription = lambda reference: deepcopy(
            first.subscription if reference == "sub_test" else provider.subscription
        )
        combined.transactions = {**deepcopy(first.transactions), **deepcopy(provider.transactions)}
        report = reconcile_known(factory, combined)
        assert report["scan_complete"] and report["failed"] == 0
        assert report["unbound"] == 1
        assert process(client, combined) == 1
    else:
        with factory.begin() as session:
            assert sync_checkout(session, provider, "ch_bob") is None
    assert_review(client, checkout_id, before)
    # Refunding/canceling the remote collision cannot make its identity safe to bind.
    provider.subscription["status"] = "canceled"
    provider.transactions["tx_bob"].update(status="refunded", refunded_amount=990)
    for _ in range(2):
        with factory.begin() as session:
            assert sync_checkout(session, provider, "ch_bob") is None
        assert_review(client, checkout_id, before)
    assert len(provider.create_calls) == 1
    assert event(
        client, "checkout.completed", "evt_bob_repeated", {"id": "ch_bob", "mode": "test"}
    ).status_code == 200
    assert process(client, provider) == 1
    assert_review(client, checkout_id, before)
    # The unresolved paid checkout must not disappear through account deletion.
    with factory() as session:
        checkout = session.get(CheckoutSession, checkout_id)
        with pytest.raises(BillingMismatch, match="DELETION_CUSTOMER_CONFLICT"):
            verify_stopped_billing(
                session, AccountDeletion(user_id=checkout.user_id), provider
            )
    assert provider.cancel_calls == []


@pytest.mark.parametrize("invalid", ["request_id", "product", "units", "mode"])
def test_invalid_provider_checkout_does_not_block_target_account(billing, invalid):
    client, first = billing
    pay(client, first)
    provider, checkout_id = second_checkout(client)
    provider.checkout[invalid] = {"units": 2, "mode": "live"}.get(invalid, "unbound")
    factory = client.app.state.session_factory
    with pytest.raises(BillingMismatch), factory.begin() as session:
        sync_checkout(session, provider, "ch_bob")
    with factory() as session:
        checkout = session.get(CheckoutSession, checkout_id)
        account = session.scalar(
            select(BillingAccount).where(BillingAccount.user_id == checkout.user_id)
        )
        assert not account.blocked
        assert checkout.error_code is None and checkout.status == "pending"


def test_late_create_response_does_not_overwrite_verified_conflict(billing):
    client, first = billing
    pay(client, first)
    factory = client.app.state.session_factory
    before = original_snapshot(factory)

    def callback(provider):
        provider.checkout["status"] = "completed"
        with factory.begin() as session:
            assert sync_checkout(session, provider, "ch_bob") is None

    _, checkout_id = second_checkout(client, during_create=callback)
    assert_review(client, checkout_id, before)


def test_historical_conflict_preserves_terminal_status_beside_new_pending_checkout(billing):
    client, first = billing
    pay(client, first)
    factory = client.app.state.session_factory
    with factory.begin() as session:
        original = session.scalar(select(CheckoutSession))
        original_id, user_id = original.id, original.user_id
        session.scalar(select(BillingSubscription)).status = "canceled"
        session.scalar(select(PaidPeriod)).period_end = datetime.now(UTC) - timedelta(hours=1)
    before = original_snapshot(factory)
    headers = {**HEADERS, "Idempotency-Key": "alice_second_key"}
    _, newer_id = second_checkout(client, headers=headers)
    first.checkout["customer"] = "cust_changed"
    with factory.begin() as session:
        assert sync_checkout(session, first, "ch_test") is None
    with factory() as session:
        original = session.get(CheckoutSession, original_id)
        newer = session.get(CheckoutSession, newer_id)
        assert original.status == "completed"
        assert original.error_code == "CUSTOMER_BINDING_CONFLICT"
        assert original.checkout_url is None
        assert newer.status == "pending" and newer.error_code is None
        account = session.scalar(select(BillingAccount))
        assert account.blocked and account.customer_id == "cust_alice"
        assert billing_state(session, user_id)["sync_state"] == "review_required"
        with pytest.raises(BillingMismatch, match="DELETION_CUSTOMER_CONFLICT"):
            verify_stopped_billing(session, AccountDeletion(user_id=user_id), None)
    current = original_snapshot(factory)
    for table in ("billing_subscriptions", "paid_periods"):
        assert current[table] == before[table]
    response = client.post("/billing/checkout", headers=headers, json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BILLING_REVIEW_REQUIRED"
    # A terminal marker remains a deletion blocker even without an open intent.
    with factory.begin() as session:
        session.get(CheckoutSession, newer_id).status = "expired"
    with factory() as session:
        with pytest.raises(BillingMismatch, match="DELETION_CUSTOMER_CONFLICT"):
            verify_stopped_billing(session, AccountDeletion(user_id=user_id), None)


@pytest.mark.parametrize("previously_completed", [False, True])
def test_late_customer_conflict_reopens_deletion_billing_before_cleanup(
    deletion_client, previously_completed
):
    client, provider = deletion_client
    pay(client, provider)
    bob_id = client.get("/me", headers=BOB).json()["id"]
    factory = client.app.state.session_factory
    with factory.begin() as session:
        account_for(session, bob_id).customer_id = "cust_other"
    job = create_job(client, "alice").json()
    job_key = f"jobs/{job['id']}/source.wav"
    assert client.app.state.storage.exists(job_key)
    assert request_deletion(client).status_code == 202
    assert process_deletion(client, provider) == 1
    if previously_completed:
        assert process_deletion(client, provider) == 1
    with factory() as session:
        deletion = session.scalar(select(AccountDeletion))
        user_id = deletion.user_id
        assert deletion.phase == "cleanup"
        assert deletion.status == ("completed" if previously_completed else "pending")
    # The provider's authoritative historical checkout has changed customer,
    # and the new customer belongs to a different local identity.
    provider.checkout["customer"] = "cust_other"
    with factory.begin() as session:
        assert sync_checkout(session, provider, "ch_test") is None
    with factory() as session:
        deletion = session.scalar(select(AccountDeletion))
        assert (deletion.phase, deletion.status, deletion.error_code) == (
            "billing", "review", "DELETION_CUSTOMER_CONFLICT"
        )
        assert deletion.completed_at is None
        assert session.get(User, user_id).active is False
        owner_account = account_for(session, user_id)
        assert owner_account.blocked and owner_account.customer_id == "cust_alice"
        other_account = account_for(session, bob_id)
        assert not other_account.blocked and other_account.customer_id == "cust_other"
        assert session.scalar(select(BillingSubscription)).user_id == user_id
        assert session.scalar(select(PaidPeriod)).user_id == user_id
        checkout = session.scalar(select(CheckoutSession))
        assert checkout.status == "completed"
        assert checkout.error_code == "CUSTOMER_BINDING_CONFLICT"
        with pytest.raises(BillingMismatch, match="DELETION_CUSTOMER_CONFLICT"):
            verify_stopped_billing(session, deletion, provider)
    assert process_deletion(client, provider) == 0
    if not previously_completed:
        assert client.app.state.storage.exists(job_key)
        with factory() as session:
            assert session.get(User, user_id).email is not None
    assert provider.cancel_calls == ["sub_test"]


@pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; no existing database is used",
)
def test_concurrent_new_customer_binding_keeps_one_owner_and_persists_loser_review(
    database, tmp_path
):
    _, engine, factory = database
    users = [owner(factory), owner(factory)]
    settings = auth_settings(tmp_path).model_copy(update={"creem_product_id": "prod_test"})
    providers = [FakeProvider(), FakeProvider()]
    for index, (user_id, provider) in enumerate(zip(users, providers, strict=True)):
        # Distinct authoritative checkouts return the same unbound customer.
        def create(*, _provider=provider, _index=index, **kwargs):
            FakeProvider.create_checkout(_provider, **kwargs)
            _provider.checkout.update(id=f"ch_{_index}", subscription=f"sub_{_index}")
            return deepcopy(_provider.checkout)

        provider.create_checkout = create
        provider.get_checkout = lambda _, p=provider: deepcopy(p.checkout)
        provider.get_subscription = lambda _, p=provider: deepcopy(p.subscription)
        provider.subscription.update(id=f"sub_{index}", last_transaction_id=None)
        with factory() as session:
            create_checkout(
                session, session.get(User, user_id), "race_key", settings, provider
            )
        provider.checkout["status"] = "completed"
    barrier, lock, arrived = Barrier(2), Lock(), set()

    def customer_lookup(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("SELECT billing_accounts.id ")
            and "billing_accounts.customer_id =" in statement
            and "billing_accounts.user_id !=" in statement
        ):
            with lock:
                first_lookup = get_ident() not in arrived
                arrived.add(get_ident())
            if first_lookup:
                barrier.wait(timeout=15)

    def synchronize(index):
        with factory.begin() as session:
            binding = sync_checkout(session, providers[index], f"ch_{index}")
            return binding.user_id if binding else None

    sqlalchemy_event.listen(engine, "after_cursor_execute", customer_lookup)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(synchronize, range(2)))
    finally:
        sqlalchemy_event.remove(engine, "after_cursor_execute", customer_lookup)
    assert len(arrived) == 2
    assert results.count(None) == 1
    winner = next(result for result in results if result)
    with factory() as session:
        accounts = session.scalars(select(BillingAccount)).all()
        assert len(accounts) == 2
        assert [(row.user_id, row.customer_id) for row in accounts if not row.blocked] == [
            (winner, "cust_alice")
        ]
        loser = next(row for row in accounts if row.blocked)
        assert loser.customer_id is None and loser.user_id != winner
        assert billing_state(session, loser.user_id)["sync_state"] == "review_required"
        assert session.scalars(select(BillingSubscription)).one().user_id == winner
        assert not session.scalar(select(PaidPeriod.id))
        pending = session.scalar(
            select(CheckoutSession).where(CheckoutSession.user_id == loser.user_id)
        )
        assert pending.status == "uncertain"
        assert pending.error_code == "CUSTOMER_BINDING_CONFLICT"
