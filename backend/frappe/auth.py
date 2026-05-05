"""
Frappe Authentication — Login, Logout, API Key Auth

Replaces frappe/auth.py — handles user login/logout, API key authentication,
JWT token generation, and CSRF protection.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

import frappe
from frappe.types import _dict
from frappe.utils.data import cint


class LoginManager:
    """Handle user login, session creation, and post-login setup."""

    def __init__(self):
        self.user = None
        self.info = None
        self.is_valid_login = False

    def login(self, user: str, password: str | None = None, resume: bool = False):
        """Login a user.

        :param user: Username/email
        :param password: Password (optional for token-based login)
        :param resume: If True, resume existing session without password check
        """
        if not resume and password:
            self.check_password(user, password)

        self.user = user
        self.is_valid_login = True

        # Setup session
        frappe.session.user = user
        frappe.local.user = user

        # Load user info
        self.info = frappe.db.get_value(
            "User", user, ["name", "first_name", "last_name", "full_name", "user_type"], as_dict=True
        )

        if not self.info:
            frappe.throw(frappe._("User {0} not found").format(user), frappe.AuthenticationError)

        # Start session
        frappe.local.session = frappe.sessions.start(user, resume=resume)

        # Run login hooks
        self.run_trigger("on_login")

        # Update user timestamp
        frappe.db.set_value("User", user, "last_login", frappe.utils.now(), update_modified=False)
        frappe.db.commit()

        return frappe.local.session

    def check_password(self, user: str, password: str) -> bool:
        """Verify user password."""
        # Get stored password hash
        user_doc = frappe.db.get_value(
            "User", user, ["name", "password"], as_dict=True
        )

        if not user_doc or not user_doc.password:
            frappe.throw(frappe._("Invalid login credentials"), frappe.AuthenticationError)

        # Check password using werkzeug-style check (PBKDF2 or simple hash)
        if not check_hash(password, user_doc.password):
            # Log failed login attempt
            log_login_attempt(user, success=False)
            frappe.throw(frappe._("Invalid login credentials"), frappe.AuthenticationError)

        log_login_attempt(user, success=True)
        return True

    def logout(self, arg="", user=None):
        """Logout the current user."""
        self.run_trigger("on_logout")

        if not user:
            user = frappe.session.user

        # Clear sessions
        frappe.sessions.clear(user=user)

        # Reset to guest
        frappe.session.user = "Guest"
        frappe.local.user = "Guest"
        frappe.local.session = frappe.sessions.create_guest_session()

        return frappe._("Logged out")

    def run_trigger(self, event: str):
        """Run login/logout hooks from installed apps."""
        for method in frappe.get_hooks(event, []):
            try:
                frappe.call(method, login_manager=self)
            except Exception:
                frappe.log_error(f"Error running {event} hook")


def login(user: str, password: str | None = None) -> _dict:
    """Convenience function for login."""
    lm = LoginManager()
    return lm.login(user, password)


def logout():
    """Convenience function for logout."""
    lm = LoginManager()
    return lm.logout()


def check_password(user: str, password: str) -> bool:
    """Check if password is correct for a user."""
    user_doc = frappe.db.get_value("User", user, ["name", "password"], as_dict=True)
    if not user_doc or not user_doc.password:
        return False
    return check_hash(password, user_doc.password)


def check_hash(password: str, hashed: str) -> bool:
    """Check a password against a hash.

    Supports both PBKDF2 (werkzeug format) and simple SHA256 hashes.
    """
    if hashed.startswith("pbkdf2:"):
        # Werkzeug PBKDF2 format: pbkdf2:sha256:iterations$salt$hash
        try:
            from werkzeug.security import check_password_hash
            return check_password_hash(hashed, password)
        except ImportError:
            pass

    # Fallback: SHA256 comparison
    if hashed.startswith("sha256$"):
        salt = hashed.split("$")[1]
        expected_hash = hashed.split("$")[2]
        actual = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return hmac.compare_digest(expected_hash, actual)

    # Direct comparison (for dev/testing)
    return hmac.compare_digest(hashed, hashlib.sha256(password.encode()).hexdigest())


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    try:
        from werkzeug.security import generate_password_hash
        return generate_password_hash(password, method="pbkdf2:sha256", salt_length=8)
    except ImportError:
        # Fallback to SHA256
        salt = secrets.token_hex(8)
        hash_value = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"sha256${salt}${hash_value}"


def validate_auth():
    """Validate authentication for current request.

    Checks session, API keys, or OAuth headers.
    """
    # Try session-based auth
    session = frappe.sessions.get()
    if session and session.user and session.user != "Guest":
        frappe.session.user = session.user
        frappe.local.user = session.user
        return

    # Try API key auth
    auth_header = frappe.get_request_header("Authorization", "")
    if auth_header.startswith("Basic "):
        validate_auth_via_api_keys(auth_header)
        return

    # Guest is fine for whitelisted methods
    frappe.session.user = "Guest"
    frappe.local.user = "Guest"


def validate_auth_via_api_keys(authorization_header: str):
    """Validate API key/secret from Authorization header."""
    import base64

    try:
        encoded = authorization_header.replace("Basic ", "")
        decoded = base64.b64decode(encoded).decode("utf-8")
        api_key, api_secret = decoded.split(":", 1)
    except Exception:
        frappe.throw(frappe._("Invalid authorization headers"), frappe.AuthenticationError)

    validate_api_key_secret(api_key, api_secret)


def validate_api_key_secret(api_key: str, api_secret: str, frappe_authorization_source=None):
    """Validate API key and secret against stored values."""
    user = frappe.db.get_value("User", {"api_key": api_key}, "name")
    if not user:
        frappe.throw(frappe._("Invalid API key"), frappe.AuthenticationError)

    stored_secret = frappe.db.get_value("User", user, "api_secret")
    if not stored_secret:
        frappe.throw(frappe._("API secret not configured"), frappe.AuthenticationError)

    # Use constant-time comparison
    if not hmac.compare_digest(stored_secret, api_secret):
        frappe.throw(frappe._("Invalid API secret"), frappe.AuthenticationError)

    # Set user context
    frappe.session.user = user
    frappe.local.user = user
    frappe.local.session = frappe.sessions.start(user)


def get_logged_user():
    """Get the currently logged-in user."""
    if hasattr(frappe, "session") and frappe.session and frappe.session.user:
        return frappe.session.user
    return "Guest"


def clear_cookies():
    """Clear authentication cookies."""
    # In replacement framework, client-side handles cookie clearing
    pass


def validate_ip_address(user):
    """Check if request IP is allowed for the user."""
    # TODO: Implement IP restriction check
    pass


def log_login_attempt(user: str, success: bool = True):
    """Log a login attempt."""
    try:
        frappe.get_doc(
            {
                "doctype": "Activity Log",
                "user": user,
                "status": "Success" if success else "Failed",
                "ip_address": getattr(frappe.local, "request_ip", None),
                "activity_type": "Login",
            }
        ).insert(ignore_permissions=True)
    except Exception:
        pass


class LoginAttemptTracker:
    """Track login attempts to prevent brute force."""

    def __init__(self, key: str, raise_locked_exception: bool = True):
        self.key = key
        self.raise_locked_exception = raise_locked_exception
        self.max_attempts = 3
        self.lock_interval = 5 * 60  # 5 minutes

    def track_attempt(self, success: bool = False):
        """Track a login attempt."""
        cache_key = f"login_attempts:{self.key}"
        attempts = frappe.cache.get_value(cache_key, 0) or 0

        if success:
            # Clear attempts on success
            frappe.cache.delete_value(cache_key)
            return

        attempts += 1
        frappe.cache.set_value(cache_key, attempts, expires_in_sec=self.lock_interval)

        if attempts >= self.max_attempts and self.raise_locked_exception:
            frappe.throw(
                frappe._("Too many failed login attempts. Please try again later."),
                frappe.AuthenticationError,
            )

    def is_locked(self) -> bool:
        """Check if the account is temporarily locked."""
        cache_key = f"login_attempts:{self.key}"
        attempts = frappe.cache.get_value(cache_key, 0) or 0
        return attempts >= self.max_attempts


def get_login_attempt_tracker(key: str, raise_locked_exception: bool = True):
    """Get a login attempt tracker for a key (user or IP)."""
    return LoginAttemptTracker(key, raise_locked_exception)


def validate_oauth(authorization_header: str):
    """Validate OAuth token. Placeholder for OAuth support."""
    frappe.throw(frappe._("OAuth not yet implemented"), frappe.AuthenticationError)


def validate_auth_via_hooks():
    """Run custom auth validation hooks."""
    for method in frappe.get_hooks("auth_validation", []):
        try:
            frappe.call(method)
        except Exception:
            pass


def check_request_ip():
    """Check if the request IP is valid."""
    pass  # TODO: IP-based restrictions
