from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import frappe


def create_hmac(
    secret: str,
    message: str,
    hashfn: str = "sha256",
) -> str:
    """Create a Base64-encoded HMAC signature.

    Args:
        secret: The shared secret key.
        message: The message to sign.
        hashfn: Hash function name (``'sha256'``, ``'sha512'``, ``'md5'``).

    Returns:
        Base64-encoded HMAC signature string.
    """
    hash_alg = getattr(hashlib, hashfn, hashlib.sha256)
    sig = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hash_alg,
    ).digest()
    return base64.b64encode(sig).decode("utf-8")


def verify_hmac(
    secret: str,
    message: str,
    signature: str,
    hashfn: str = "sha256",
) -> bool:
    """Verify a Base64-encoded HMAC signature.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        secret: The shared secret key.
        message: The original message.
        signature: The Base64-encoded signature to verify.
        hashfn: Hash function name.

    Returns:
        ``True`` if the signature is valid.
    """
    expected = create_hmac(secret, message, hashfn)
    return hmac.compare_digest(expected, signature)


def get_payment_gateway_controller(payment_gateway: str) -> Any:
    """Return the payment gateway integration controller instance.

    Looks up the gateway in the ``Payment Gateway`` DocType and
    instantiates the controller class defined by its ``gateway_controller``
    field.

    Args:
        payment_gateway: Name of the payment gateway.

    Returns:
        An instance of the gateway controller class.
    """
    gateway_doc = frappe.get_doc("Payment Gateway", payment_gateway)
    controller_path = gateway_doc.gateway_controller
    controller_class = frappe.get_attr(controller_path)
    return controller_class(gateway_doc.name)


def get_webhook_address(
    connector_name: str,
    method: str,
    exclude_uri: bool = False,
) -> str:
    """Build the webhook URL for an integration connector.

    Args:
        connector_name: The integration connector name.
        method: The webhook method name.
        exclude_uri: If ``True``, omit the leading scheme/host.

    Returns:
        The full webhook URL.
    """
    site_url = frappe.utils.get_url()
    webhook_path = f"/api/method/frappe.integrations.{connector_name}.{method}"
    if exclude_uri:
        return webhook_path
    return f"{site_url}{webhook_path}"


def json_handler(obj: Any) -> Any:
    """JSON serializer helper for non-serializable types.

    Handles ``datetime``, ``date``, ``Decimal``, ``set``, ``bytes``,
    and Frappe document objects.

    Args:
        obj: The object to serialize.

    Returns:
        A JSON-serializable representation.
    """
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, (date,)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, dict)):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def get_iso_datetime(dt: Optional[datetime] = None) -> str:
    """Return an ISO 8601 formatted datetime string.

    Args:
        dt: The datetime to format (defaults to *now*).

    Returns:
        ISO-formatted string with timezone info if available.
    """
    if dt is None:
        dt = datetime.now()
    return dt.isoformat()


def generate_id() -> str:
    """Generate a unique identifier for integration records.

    Returns:
        A UUID4 hex string.
    """
    return uuid.uuid4().hex


def create_auth_hash(data: dict, secret: str, hashfn: str = "sha256") -> str:
    """Create an authentication hash for a payload dictionary.

    Serialises *data* to a canonical JSON string and signs it.

    Args:
        data: The payload dictionary.
        secret: The shared secret.
        hashfn: Hash algorithm.

    Returns:
        Base64-encoded HMAC signature.
    """
    message = json.dumps(data, sort_keys=True, separators=(",", ":"), default=json_handler)
    return create_hmac(secret, message, hashfn)


def verify_auth_hash(
    data: dict,
    secret: str,
    signature: str,
    hashfn: str = "sha256",
) -> bool:
    """Verify an authentication hash for a payload dictionary.

    Args:
        data: The payload dictionary.
        secret: The shared secret.
        signature: The signature to verify.
        hashfn: Hash algorithm.

    Returns:
        ``True`` if the signature is valid.
    """
    expected = create_auth_hash(data, secret, hashfn)
    return hmac.compare_digest(expected, signature)


def generate_nonce(length: int = 32) -> str:
    """Generate a cryptographically secure random nonce.

    Args:
        length: Length of the nonce in bytes (result is hex = 2x length).

    Returns:
        Hex-encoded random string.
    """
    return hashlib.sha256(os.urandom(length)).hexdigest()


def build_query_string(params: dict[str, Any]) -> str:
    """Build a URL query string from a dictionary.

    Values are JSON-serialised (except simple strings).

    Args:
        params: Query parameters.

    Returns:
        URL-encoded query string (without leading ``?``).
    """
    from urllib.parse import quote_plus

    parts: list[str] = []
    for key, value in params.items():
        if isinstance(value, (str, int, float, bool)):
            parts.append(f"{quote_plus(str(key))}={quote_plus(str(value))}")
        else:
            parts.append(f"{quote_plus(str(key))}={quote_plus(json.dumps(value, default=json_handler))}")
    return "&".join(parts)


# Ensure json_handler can reference os for generate_nonce
import os  # noqa: E402
