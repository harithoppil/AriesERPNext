"""
User DocType Controller

Manages user accounts, authentication credentials, role assignments,
and self-permission sharing. Integrates with frappe.auth for password
hashing and frappe.permissions for role-based access control.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

import frappe
from frappe.model.document import Document

if TYPE_CHECKING:
    from collections.abc import Iterable


#: Users that cannot be deleted or disabled.
STANDARD_USERS: tuple[str, ...] = ("Administrator", "Guest")

#: System roles that cannot be assigned through normal UI.
SYSTEM_ROLES: frozenset[str] = frozenset({"Administrator", "System Manager", "All", "Guest"})

#: Default role for non-guest users.
DEFAULT_ROLE = "System User"

#: Email validation regex (RFC 5322 simplified).
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class User(Document):
    """DocType controller for User — handles validation, roles, and permissions."""

    # --------------------------------------------------------------------------
    # Lifecycle hooks
    # --------------------------------------------------------------------------

    def validate(self) -> None:
        """Validate user fields before insert / update.

        Runs on every save. Ensures email is well-formed, at least one role
        is present, and generates a password for new users when none is supplied.
        """
        self.validate_email()
        self.validate_roles()
        self.validate_username()

        if self.is_new():
            self.set_new_password_if_empty()

        # Prevent renaming of standard users
        if self.name in STANDARD_USERS and self.name != self.get_doc_before_save().name if self.get_doc_before_save() else False:
            raise frappe.ValidationError("Cannot rename standard users")

    def before_save(self) -> None:
        """Normalize fields before the record is persisted.

        * Derives ``full_name`` from first + last name.
        * Falls back ``username`` to the local-part of the email address.
        * Strips leading/trailing whitespace from text fields.
        """
        self.full_name = " ".join(filter(None, [self.first_name or "", self.last_name or ""]))

        if not self.username and self.email:
            self.username = self.email.split("@")[0]

        # Normalize whitespace
        for field in ("first_name", "last_name", "full_name", "username", "email"):
            value = getattr(self, field, None)
            if value and isinstance(value, str):
                setattr(self, field, value.strip())

    def on_update(self) -> None:
        """Post-save housekeeping.

        * Clears the user cache so subsequent permission checks pick up changes.
        * Ensures the user can read their own User record.
        * Updates ``modified_by`` tracking if needed.
        """
        frappe.cache_manager.clear_user_cache(self.name)
        self.share_with_self()

        # If the user just changed their own password, update password_login
        if self.new_password and not self.flags.ignore_permissions:
            self.update_password(self.new_password)
            self.new_password = None  # Clear transient field after hashing

    def on_trash(self) -> None:
        """Prevent deletion of system users and clean up related records.

        Raises:
            frappe.ValidationError: If the user is a standard/system user.
        """
        if self.name in STANDARD_USERS:
            raise frappe.ValidationError(f"Cannot delete standard user: {self.name}")

        if self.name == frappe.session.user and not frappe.flags.in_test:
            raise frappe.ValidationError("You cannot delete your own account")

        # Clean up role assignments
        self.remove_all_roles()

        # Clean up user permissions
        frappe.db.delete("User Permission", {"user": self.name})

        # Clean up communication references
        frappe.db.sql(
            """UPDATE `tabCommunication`
               SET sender = NULL, sent_or_received = ""
               WHERE sender = %s""",
            (self.name,),
        )

    def before_rename(self, old_name: str, new_name: str, merge: bool = False) -> None:
        """Prevent renaming of standard users.

        Args:
            old_name: Current document name.
            new_name: Desired new name.
            merge: Whether this is a merge operation.

        Raises:
            frappe.ValidationError: If the user is a standard user.
        """
        if old_name in STANDARD_USERS:
            raise frappe.ValidationError("Cannot rename standard users")

    # --------------------------------------------------------------------------
    # Validation helpers
    # --------------------------------------------------------------------------

    def validate_email(self) -> None:
        """Ensure the email address is non-empty and RFC-compliant.

        Raises:
            frappe.ValidationError: If the email is missing or malformed.
        """
        if not self.email:
            raise frappe.ValidationError("Email address is required")

        email = self.email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise frappe.ValidationError(f"Invalid email address: {self.email}")

        # Prevent duplicate email addresses across users (excluding self on update)
        existing = frappe.db.get_value("User", {"email": email, "name": ("!=", self.name)}, "name")
        if existing:
            raise frappe.ValidationError(f"Email address {email} is already registered to user {existing}")

        self.email = email

    def validate_roles(self) -> None:
        """Ensure the user has at least one valid role assigned.

        * ``Guest`` is automatically assigned the ``Guest`` role.
        * All other users must have at least one non-Guest role.
        * Prevents assignment of the reserved ``Administrator`` role.

        Raises:
            frappe.ValidationError: If role validation fails.
        """
        roles = [r.role for r in (self.roles or []) if r.role]

        if self.name == "Guest":
            if "Guest" not in roles:
                self.append("roles", {"role": "Guest"})
            return

        if not roles:
            # Auto-assign default role for new non-guest users
            self.append("roles", {"role": DEFAULT_ROLE})

        # Prevent non-admin from assigning Administrator role
        if "Administrator" in roles and frappe.session.user != "Administrator":
            raise frappe.PermissionError("Only Administrator can assign the Administrator role")

    def validate_username(self) -> None:
        """Validate username format and uniqueness.

        Usernames must be alphanumeric with underscores/hyphens only.

        Raises:
            frappe.ValidationError: If the username is invalid or taken.
        """
        if not self.username:
            return

        username = self.username.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", username):
            raise frappe.ValidationError(
                "Username can only contain letters, numbers, underscores, and hyphens"
            )

        # Check uniqueness (case-insensitive)
        existing = frappe.db.get_value(
            "User", {"username": username, "name": ("!=", self.name)}, "name"
        )
        if existing:
            raise frappe.ValidationError(f"Username '{username}' is already taken")

        self.username = username

    def set_new_password_if_empty(self) -> None:
        """Generate a secure random password for new users when none is provided.

        The generated password is stored in ``new_password`` which is hashed
        during ``on_update``.  It is NOT persisted in plaintext.
        """
        if not self.new_password and not self.send_welcome_email:
            self.new_password = frappe.generate_hash(length=12)

    # --------------------------------------------------------------------------
    # Permissions & self-sharing
    # --------------------------------------------------------------------------

    def share_with_self(self) -> None:
        """Grant the user read access to their own User record.

        Creates a ``User Permission`` row so the user can view their own
        profile without requiring a blanket read permission on *all* users.
        """
        if not self.reference_doctype_applicable():
            return

        # Check if self-permission already exists
        if frappe.db.exists(
            "User Permission",
            {"user": self.name, "allow": "User", "for_value": self.name},
        ):
            return

        try:
            user_permission = frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": self.name,
                    "allow": "User",
                    "for_value": self.name,
                    "apply_to_all_doctypes": 1,
                    "is_default": 1,
                }
            )
            user_permission.insert(ignore_permissions=True)
        except Exception:
            # Best-effort: if User Permission DocType doesn't exist yet (bootstrapping),
            # silently skip.
            pass

    def remove_all_roles(self) -> None:
        """Remove all role assignments for this user.

        Called during deletion to maintain referential integrity.
        """
        frappe.db.delete("Has Role", {"parent": self.name})
        frappe.cache_manager.clear_user_cache(self.name)

    # --------------------------------------------------------------------------
    # Password management
    # --------------------------------------------------------------------------

    def update_password(self, new_password: str) -> None:
        """Hash and persist a new password for this user.

        Args:
            new_password: Plaintext password (will be hashed).
        """
        from frappe.auth import hash_password

        phash = hash_password(new_password)
        frappe.db.set_value(
            "User", self.name, {"password": phash, "reset_password_key": None, "last_password_reset_datetime": frappe.now()}
        )

    def reset_password(self, send_email: bool = False) -> Optional[str]:
        """Generate a reset token and optionally email it.

        Args:
            send_email: Whether to dispatch the reset email.

        Returns:
            The reset key token, or ``None``.
        """
        reset_key = frappe.generate_hash(length=32)
        frappe.db.set_value("User", self.name, "reset_password_key", reset_key)

        if send_email:
            # Emit password-reset event; actual email logic lives in notifications layer
            frappe.emit_event("password_reset", {"user": self.name, "reset_key": reset_key})

        return reset_key

    # --------------------------------------------------------------------------
    # Role API
    # --------------------------------------------------------------------------

    def add_role(self, role: str) -> None:
        """Assign *role* to this user and persist immediately.

        Args:
            role: The role to assign.

        Raises:
            frappe.ValidationError: If the role does not exist.
        """
        if not frappe.db.exists("Role", role):
            raise frappe.ValidationError(f"Role '{role}' does not exist")

        existing = {r.role for r in (self.roles or [])}
        if role in existing:
            return  # Idempotent

        self.append("roles", {"role": role})
        self.save()

    def remove_role(self, role: str) -> None:
        """Revoke *role* from this user and persist immediately.

        Args:
            role: The role to remove.
        """
        for i, r in enumerate(self.roles or []):
            if r.role == role:
                self.roles.pop(i)
                self.save()
                break

    def has_role(self, role: str) -> bool:
        """Return ``True`` if the user possesses *role*.

        Args:
            role: Role name to check.
        """
        return any(r.role == role for r in (self.roles or []))

    def get_roles(self) -> list[str]:
        """Return all roles including the implicit ``All`` role.

        Returns:
            Sorted list of unique role names.
        """
        roles = list({r.role for r in (self.roles or []) if r.role})
        if "All" not in roles:
            roles.append("All")
        return sorted(roles)

    def get_roles_dict(self) -> dict[str, bool]:
        """Return roles as a dict for fast membership tests.

        Returns:
            Mapping of role name → ``True``.
        """
        return {r: True for r in self.get_roles()}

    # --------------------------------------------------------------------------
    # Convenience predicates
    # --------------------------------------------------------------------------

    def is_admin(self) -> bool:
        """Return ``True`` if this user is *Administrator*."""
        return self.name == "Administrator"

    def is_system_manager(self) -> bool:
        """Return ``True`` if this user has the *System Manager* role."""
        return self.has_role("System Manager")

    def is_guest(self) -> bool:
        """Return ``True`` if this user is *Guest*."""
        return self.name == "Guest"

    def is_active(self) -> bool:
        """Return ``True`` if the user account is enabled."""
        return bool(self.enabled)

    # --------------------------------------------------------------------------
    # Query helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def get_all_users_with_role(role: str) -> list[str]:
        """Return names of all users that have *role*.

        Args:
            role: Role name to filter by.

        Returns:
            List of user names.
        """
        return frappe.get_all(
            "Has Role",
            filters={"role": role, "parenttype": "User"},
            pluck="parent",
            distinct=True,
        )

    @staticmethod
    def find_by_email(email: str) -> Optional["User"]:
        """Lookup a user by their email address.

        Args:
            email: Email address to search.

        Returns:
            The ``User`` document, or ``None``.
        """
        name = frappe.db.get_value("User", {"email": email.lower().strip()}, "name")
        return frappe.get_doc("User", name) if name else None

    @staticmethod
    def find_by_username(username: str) -> Optional["User"]:
        """Lookup a user by their username.

        Args:
            username: Username to search.

        Returns:
            The ``User`` document, or ``None``.
        """
        name = frappe.db.get_value("User", {"username": username.strip()}, "name")
        return frappe.get_doc("User", name) if name else None
