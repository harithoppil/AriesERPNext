from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from typing import Any, Optional

import requests

import frappe
from frappe.types import _dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OAuth2 helpers
# ---------------------------------------------------------------------------


def get_oauth2_providers() -> _dict:
    """Return configured OAuth2 providers from site config / hooks.

    Providers are defined in ``OAuth2 Provider`` DocType records or
    in the ``oauth2_providers`` hook.

    Returns:
        An ``_dict`` mapping provider names to their configuration
        (client_id, client_secret, authorize_url, access_token_url, etc.).
    """
    providers: _dict = _dict()

    # First check hooks
    oauth2_providers = frappe.get_hooks("oauth2_providers")
    if oauth2_providers:
        for provider_name, config in oauth2_providers.items():
            providers[provider_name] = _dict(config)

    # Then check DocType records
    try:
        for doc in frappe.get_all(
            "OAuth2 Provider",
            fields=["name", "client_id", "client_secret", "authorize_url",
                    "access_token_url", "redirect_url", "icon", "base_url"],
        ):
            providers[doc.name] = _dict({
                "client_id": doc.client_id,
                "client_secret": doc.get_password("client_secret") if hasattr(doc, "get_password") else doc.client_secret,
                "authorize_url": doc.authorize_url,
                "access_token_url": doc.access_token_url,
                "redirect_url": doc.redirect_url,
                "icon": doc.icon,
                "base_url": doc.base_url,
            })
    except Exception:
        # OAuth2 Provider DocType may not exist yet
        pass

    return providers


def get_oauth_keys(provider: str) -> tuple[Optional[str], Optional[str]]:
    """Return the *(client_id, client_secret)* pair for *provider*.

    Args:
        provider: The OAuth provider name.

    Returns:
        A tuple of ``(client_id, client_secret)`` or ``(None, None)``
        if the provider is not configured.
    """
    providers = get_oauth2_providers()
    config = providers.get(provider)
    if not config:
        return None, None
    return config.get("client_id"), config.get("client_secret")


# ---------------------------------------------------------------------------
# Generic HTTP request helpers
# ---------------------------------------------------------------------------


def make_get_request(
    url: str,
    **kwargs: Any,
) -> Any:
    """Make an HTTP GET request.

    Args:
        url: The target URL.
        **kwargs: Additional arguments forwarded to ``requests.get``.

    Returns:
        The parsed JSON response, raw text, or ``None`` on error.
    """
    try:
        response = requests.get(url, timeout=kwargs.pop("timeout", 30), **kwargs)
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as exc:
        logger.error(f"GET request failed: {url} — {exc}")
        frappe.log_error(f"GET request failed: {url}", "Integration Request")
        raise


def make_post_request(
    url: str,
    **kwargs: Any,
) -> Any:
    """Make an HTTP POST request.

    Args:
        url: The target URL.
        **kwargs: Additional arguments forwarded to ``requests.post``.

    Returns:
        The parsed JSON response, raw text, or ``None`` on error.
    """
    try:
        response = requests.post(url, timeout=kwargs.pop("timeout", 30), **kwargs)
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as exc:
        logger.error(f"POST request failed: {url} — {exc}")
        frappe.log_error(f"POST request failed: {url}", "Integration Request")
        raise


def make_put_request(
    url: str,
    **kwargs: Any,
) -> Any:
    """Make an HTTP PUT request.

    Args:
        url: The target URL.
        **kwargs: Additional arguments forwarded to ``requests.put``.

    Returns:
        The parsed JSON response, raw text, or ``None`` on error.
    """
    try:
        response = requests.put(url, timeout=kwargs.pop("timeout", 30), **kwargs)
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as exc:
        logger.error(f"PUT request failed: {url} — {exc}")
        frappe.log_error(f"PUT request failed: {url}", "Integration Request")
        raise


def make_delete_request(
    url: str,
    **kwargs: Any,
) -> Any:
    """Make an HTTP DELETE request.

    Args:
        url: The target URL.
        **kwargs: Additional arguments forwarded to ``requests.delete``.

    Returns:
        The parsed JSON response, raw text, or ``None`` on error.
    """
    try:
        response = requests.delete(url, timeout=kwargs.pop("timeout", 30), **kwargs)
        response.raise_for_status()
        return _parse_response(response)
    except requests.RequestException as exc:
        logger.error(f"DELETE request failed: {url} — {exc}")
        frappe.log_error(f"DELETE request failed: {url}", "Integration Request")
        raise


# ---------------------------------------------------------------------------
# Authenticated request helpers
# ---------------------------------------------------------------------------


def get_request(
    url: str,
    auth_header: Optional[dict] = None,
    **kwargs: Any,
) -> Any:
    """Make a GET request with an optional authentication header.

    Args:
        url: The target URL.
        auth_header: Dict of headers to add (e.g.
            ``{"Authorization": "Bearer …"}``).
        **kwargs: Forwarded to ``requests.get``.

    Returns:
        Parsed response content.
    """
    headers = kwargs.pop("headers", {}) or {}
    if auth_header:
        headers.update(auth_header)
    return make_get_request(url, headers=headers, **kwargs)


def post_request(
    url: str,
    auth_header: Optional[dict] = None,
    **kwargs: Any,
) -> Any:
    """Make a POST request with an optional authentication header.

    Args:
        url: The target URL.
        auth_header: Dict of headers to add.
        **kwargs: Forwarded to ``requests.post``.

    Returns:
        Parsed response content.
    """
    headers = kwargs.pop("headers", {}) or {}
    if auth_header:
        headers.update(auth_header)
    return make_post_request(url, headers=headers, **kwargs)


# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------


def create_request_log(
    url: str,
    status_code: Optional[int] = None,
    error: Optional[str] = None,
    data: Optional[dict] = None,
    integration_type: Optional[str] = None,
    integration_request_service: Optional[str] = None,
    reference_doctype: Optional[str] = None,
    reference_docname: Optional[str] = None,
) -> Optional[Any]:
    """Log an external API request in the ``Integration Request`` DocType.

    Args:
        url: The request URL.
        status_code: HTTP status code returned.
        error: Error message if the request failed.
        data: Request / response payload.
        integration_type: Type of integration (e.g. ``'Webhook'``).
        integration_request_service: Service name.
        reference_doctype: Link to a reference DocType.
        reference_docname: Link to a reference document.

    Returns:
        The created ``Integration Request`` document, or ``None``.
    """
    try:
        if not frappe.db.table_exists("Integration Request"):
            return None

        log = frappe.get_doc({
            "doctype": "Integration Request",
            "integration_type": integration_type or "Remote",
            "integration_request_service": integration_request_service,
            "request_url": url,
            "request_headers": json.dumps(data.get("headers")) if data and isinstance(data, dict) and "headers" in data else None,
            "data": json.dumps(data) if data else None,
            "output": json.dumps({"status_code": status_code}) if status_code else None,
            "error": error,
            "status": "Failed" if error else "Completed",
            "reference_doctype": reference_doctype,
            "reference_docname": reference_docname,
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log
    except Exception:
        logger.exception("Failed to create integration request log")
        return None


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------


def get_json(obj: requests.Response) -> Any:
    """Safely convert a ``requests.Response`` to JSON.

    Args:
        obj: A ``requests.Response`` object.

    Returns:
        Parsed JSON, or ``None`` if parsing fails.
    """
    try:
        return obj.json()
    except (json.JSONDecodeError, ValueError, AttributeError):
        return None


def get_xml(obj: requests.Response) -> Optional[ET.Element]:
    """Parse a ``requests.Response`` as XML.

    Args:
        obj: A ``requests.Response`` object.

    Returns:
        The root XML element, or ``None`` on failure.
    """
    try:
        return ET.fromstring(obj.content)
    except ET.ParseError:
        return None


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def get_file_data(file_url: str) -> Optional[bytes]:
    """Read file data for upload to external services.

    Resolves *file_url* against the site's public / private files
    directories and returns the raw bytes.

    Args:
        file_url: The file URL or file path.

    Returns:
        The file contents as bytes, or ``None`` if not found.
    """
    if file_url.startswith("/files/"):
        file_path = frappe.get_site_path("public", "files", file_url.lstrip("/"))
    elif file_url.startswith("/private/"):
        file_path = frappe.get_site_path("private", file_url.lstrip("/"))
    elif file_url.startswith("http://") or file_url.startswith("https://"):
        try:
            resp = requests.get(file_url, timeout=30)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException:
            return None
    else:
        file_path = frappe.get_site_path(file_url.lstrip("/"))

    try:
        with open(file_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_response(response: requests.Response) -> Any:
    """Parse a ``requests.Response`` based on its Content-Type."""
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return response.json()
    if "text/" in content_type:
        return response.text
    return response.content
