"""Bounded, test-only Creem transport. Provider responses are never error messages."""

import json
import re
from typing import Any
from urllib.parse import unquote, urlsplit

import requests

from app.settings import Settings

API_BASE = "https://test-api.creem.io/v1"
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT = (5, 15)


class CreemError(Exception):
    """Safe to report without disclosing provider bodies or credentials."""


def validate_identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
        raise CreemError("Invalid payment identifier")
    return value


def validate_hosted_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 8192:
        raise CreemError("Invalid hosted payment URL")
    decoded = unquote(value)
    if any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in decoded):
        raise CreemError("Invalid hosted payment URL")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in {"creem.io", "www.creem.io"}
            and parsed.username is None
            and parsed.password is None
            and parsed.port in {None, 443}
        )
    except ValueError:
        valid = False
    if not valid:
        raise CreemError("Invalid hosted payment URL")
    return value


def _validate_modes(value: Any, *, entity: bool = False) -> None:
    if isinstance(value, dict):
        if (entity or "mode" in value) and value.get("mode") not in ("test", "sandbox"):
            raise CreemError("Payment response is not in test mode")
        for key, nested in value.items():
            # Expanded provider entities must carry their own mode. Metadata is
            # arbitrary merchant data, not a provider entity.
            _validate_modes(
                nested,
                entity=key in {"product", "customer", "subscription", "transaction", "checkout"},
            )
    elif isinstance(value, list):
        for nested in value:
            _validate_modes(nested)


class CreemClient:
    def __init__(self, settings: Settings):
        if not settings.creem_enabled or settings.billing_environment != "test":
            raise CreemError("Test billing is unavailable")
        self._api_key = settings.creem_api_key.get_secret_value()
        if not self._api_key:
            raise CreemError("Test billing is unavailable")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        payload: dict | None = None,
        entity: bool = True,
    ) -> dict:
        try:
            # A fresh Session uses requests' zero-retry adapter. POST creation
            # is deliberately never retried, even with the same request_id.
            with requests.Session() as session:
                with session.request(
                    method,
                    API_BASE + path,
                    headers={"x-api-key": self._api_key, "Accept": "application/json"},
                    params=params,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if not 200 <= response.status_code < 300:
                        raise CreemError("Payment provider request failed")
                    body = bytearray()
                    for chunk in response.iter_content(chunk_size=16384):
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise CreemError("Payment provider response is too large")
                    result = json.loads(body)
        except (requests.RequestException, ValueError, RecursionError):
            raise CreemError("Payment provider request failed") from None
        if not isinstance(result, dict):
            raise CreemError("Invalid payment provider response")
        _validate_modes(result, entity=entity)
        return result

    def get_product(self, product_id: str) -> dict:
        return self._request(
            "GET", "/products", params={"product_id": validate_identifier(product_id)}
        )

    def get_checkout(self, checkout_id: str) -> dict:
        return self._request(
            "GET",
            "/checkouts",
            params={"checkout_id": validate_identifier(checkout_id)},
        )

    def get_subscription(self, subscription_id: str) -> dict:
        return self._request(
            "GET",
            "/subscriptions",
            params={"subscription_id": validate_identifier(subscription_id)},
        )

    def get_transaction(self, transaction_id: str) -> dict:
        return self._request(
            "GET",
            "/transactions",
            params={"transaction_id": validate_identifier(transaction_id)},
        )

    def list_transactions(self, *, page_number: int = 1, page_size: int = 100) -> dict:
        if type(page_number) is not int or page_number < 1 or type(page_size) is not int:
            raise CreemError("Invalid transaction pagination")
        if not 1 <= page_size <= 100:
            raise CreemError("Invalid transaction pagination")
        result = self._request(
            "GET",
            "/transactions/search",
            params={"page_number": page_number, "page_size": page_size},
            entity=False,
        )
        items = result.get("items")
        if not isinstance(items, list) or len(items) > page_size:
            raise CreemError("Invalid transaction list")
        for item in items:
            if not isinstance(item, dict):
                raise CreemError("Invalid transaction list")
            _validate_modes(item, entity=True)
        return result

    def cancel_subscription(self, subscription_id: str) -> dict:
        return self._request(
            "POST",
            f"/subscriptions/{validate_identifier(subscription_id)}/cancel",
            payload={"mode": "immediate"},
        )

    def create_checkout(
        self,
        *,
        product_id: str,
        request_id: str,
        success_url: str,
        customer_id: str | None = None,
    ) -> dict:
        correlation = validate_identifier(request_id)
        payload = {
            "product_id": validate_identifier(product_id),
            "units": 1,
            "request_id": correlation,
            "success_url": success_url,
            "metadata": {"songdance_checkout_id": correlation},
        }
        if customer_id is not None:
            payload["customer"] = {"id": validate_identifier(customer_id)}
        result = self._request("POST", "/checkouts", payload=payload)
        validate_hosted_url(result.get("checkout_url"))
        return result

    def create_portal(self, customer_id: str) -> dict:
        result = self._request(
            "POST",
            "/customers/billing",
            payload={"customer_id": validate_identifier(customer_id)},
            entity=False,
        )
        validate_hosted_url(result.get("customer_portal_link"))
        return result
