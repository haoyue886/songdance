import json
from types import SimpleNamespace

import pytest
import requests
from pydantic import SecretStr

from app.services.creem_client import (
    API_BASE,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
    CreemClient,
    CreemError,
    validate_hosted_url,
    validate_identifier,
)


@pytest.fixture
def transport(monkeypatch):
    state = SimpleNamespace(
        body=json.dumps({"mode": "test", "id": "prod_1"}).encode(),
        status=200,
        calls=[],
        closed=False,
        error=None,
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            state.closed = True

        @property
        def status_code(self):
            return state.status

        def iter_content(self, chunk_size):
            for offset in range(0, len(state.body), chunk_size):
                yield state.body[offset : offset + chunk_size]

    def request(self, method, url, **kwargs):
        state.calls.append((method, url, kwargs))
        if state.error:
            raise state.error
        return Response()

    monkeypatch.setattr(requests.Session, "request", request)
    return state


def client(**overrides):
    settings = dict(
        creem_enabled=True,
        billing_environment="test",
        creem_api_key=SecretStr("test_secret"),
    )
    settings.update(overrides)
    return CreemClient(SimpleNamespace(**settings))


@pytest.mark.parametrize(
    "method,resource,field",
    [
        ("get_product", "products", "product_id"),
        ("get_checkout", "checkouts", "checkout_id"),
        ("get_subscription", "subscriptions", "subscription_id"),
        ("get_transaction", "transactions", "transaction_id"),
    ],
)
def test_get_contract(transport, method, resource, field):
    assert getattr(client(), method)("entity_1")["mode"] == "test"
    verb, url, options = transport.calls[0]
    assert (verb, url) == ("GET", f"{API_BASE}/{resource}")
    assert options["params"] == {field: "entity_1"}
    assert options["headers"]["x-api-key"] == "test_secret"
    assert options["timeout"] == REQUEST_TIMEOUT
    assert options["allow_redirects"] is False
    assert options["stream"] is True
    assert transport.closed


@pytest.mark.parametrize("customer", [None, "cust_1"])
def test_checkout_payload(transport, customer):
    transport.body = json.dumps(
        {"mode": "sandbox", "checkout_url": "https://creem.io/pay"}
    ).encode()
    client().create_checkout(
        product_id="prod_1",
        request_id="internal-1",
        success_url="https://songdance.app/done",
        customer_id=customer,
    )
    assert len(transport.calls) == 1
    payload = transport.calls[0][2]["json"]
    assert payload["metadata"] == {"songdance_checkout_id": "internal-1"}
    assert payload["request_id"] == "internal-1"
    assert payload["units"] == 1
    assert "cancel_url" not in payload
    assert payload.get("customer") == ({"id": customer} if customer else None)


def test_portal_contract(transport):
    transport.body = b'{"customer_portal_link":"https://www.creem.io/portal"}'
    assert client().create_portal("cust_1")["customer_portal_link"].endswith("/portal")
    assert transport.calls[0][:2] == ("POST", API_BASE + "/customers/billing")
    assert transport.calls[0][2]["json"] == {"customer_id": "cust_1"}


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b"{}",
        b'{"mode":"prod"}',
        b'{"mode":"local"}',
        b'{"mode":[]}',
        b'{"mode":"test","subscription":{"id":"sub_1"}}',
        b'{"mode":"test","customer":{"mode":"prod"}}',
        b"not json test_secret",
    ],
)
def test_reject_invalid_entities(transport, body):
    transport.body = body
    with pytest.raises(CreemError) as error:
        client().get_product("prod_1")
    assert "test_secret" not in str(error.value)
    assert transport.closed


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_failures_are_closed_and_sanitized(transport, status):
    transport.status = status
    transport.body = b"test_secret sensitive provider error"
    with pytest.raises(CreemError) as error:
        client().get_product("prod_1")
    assert "test_secret" not in str(error.value)
    assert transport.closed
    assert len(transport.calls) == 1


def test_response_limit(transport):
    transport.body = b" " * (MAX_RESPONSE_BYTES + 1)
    with pytest.raises(CreemError, match="too large"):
        client().get_product("prod_1")
    assert transport.closed


def test_post_timeout_is_not_retried(transport):
    transport.error = requests.Timeout("test_secret provider error")
    with pytest.raises(CreemError) as error:
        client().create_checkout(product_id="p", request_id="r", success_url="https://example.com")
    assert "test_secret" not in str(error.value)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("value", ["", None, "../id", "id?x=1", "id\n", "a" * 201])
def test_identifier_rejection(value):
    with pytest.raises(CreemError):
        validate_identifier(value)


@pytest.mark.parametrize(
    "url",
    [
        "http://creem.io/pay",
        "https://evil.example/pay",
        "https://creem.io.evil.example",
        "https://user@creem.io",
        "https://creem.io:444",
        "https://creem.io\\@evil.example",
        "https://creem.io/%0a",
        " https://creem.io",
        "https://creem.io:bad",
        None,
    ],
)
def test_hosted_url_rejection(url):
    with pytest.raises(CreemError):
        validate_hosted_url(url)


def test_valid_helpers():
    assert validate_identifier("sub_a-B_1") == "sub_a-B_1"
    assert validate_hosted_url("https://www.creem.io:443/a") == "https://www.creem.io:443/a"


@pytest.mark.parametrize(
    "overrides",
    [
        {"creem_enabled": False},
        {"billing_environment": "live"},
        {"creem_api_key": SecretStr("")},
    ],
)
def test_client_fails_closed(overrides):
    with pytest.raises(CreemError):
        client(**overrides)
