import json

import pytest

from app.services.creem_client import API_BASE, REQUEST_TIMEOUT, CreemError
from tests.test_creem_client import client
from tests.test_creem_client import transport as transport


def test_customer_subscriptions_uses_customer_path_and_official_pagination(transport):
    body = {
        "items": [{"id": "sub_1", "customer": "cust_1", "mode": "test"}],
        "pagination": {
            "total_records": 101, "total_pages": 2, "current_page": 2,
            "next_page": None, "prev_page": 1,
        },
    }
    transport.body = json.dumps(body).encode()
    assert client().list_customer_subscriptions("cust_1", page_number=2, page_size=100) == body
    verb, url, options = transport.calls[0]
    assert (verb, url) == ("GET", API_BASE + "/customers/cust_1/subscriptions")
    assert options["params"] == {"page_number": 2, "page_size": 100}
    assert options["json"] is None
    assert options["timeout"] == REQUEST_TIMEOUT
    assert options["allow_redirects"] is False and options["stream"] is True
    assert transport.closed


def test_customer_subscriptions_accepts_empty_envelope_without_mode(transport):
    transport.body = b'{"items":[],"pagination":{"total_records":0,"total_pages":0}}'
    assert client().list_customer_subscriptions("cust_1")["items"] == []


@pytest.mark.parametrize("items", [
    None, {}, [None], [{"id": "sub_1"}], [{"id": "sub_1", "mode": "prod"}],
    [{"id": "sub_1", "mode": "test", "customer": {"id": "cust_1", "mode": "prod"}}],
    [{"id": "sub_1", "mode": "test"}] * 101,
])
def test_customer_subscriptions_rejects_invalid_or_live_entities(transport, items):
    transport.body = json.dumps({"items": items, "pagination": {}}).encode()
    with pytest.raises(CreemError):
        client().list_customer_subscriptions("cust_1")
    assert transport.closed


@pytest.mark.parametrize("page_number,page_size", [
    (0, 100), (-1, 100), (True, 100), (1.0, 100), ("1", 100),
    (1, 0), (1, 101), (1, True), (1, 1.0), (1, "100"),
])
def test_customer_subscriptions_validates_pagination_before_transport(
    transport, page_number, page_size
):
    with pytest.raises(CreemError):
        client().list_customer_subscriptions(
            "cust_1", page_number=page_number, page_size=page_size,
        )
    assert transport.calls == []


@pytest.mark.parametrize("identifier", ["", "../cust_1", "cust_1?mode=prod", "cust_1\n", None])
def test_customer_subscriptions_validates_customer_path_before_transport(transport, identifier):
    with pytest.raises(CreemError):
        client().list_customer_subscriptions(identifier)
    assert transport.calls == []
