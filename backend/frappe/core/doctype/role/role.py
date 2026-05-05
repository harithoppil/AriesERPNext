"""
Role DocType Controller

Manages role definitions used by the role-based access control (RBAC) system.
System roles (Administrator, System Manager, All, Guest) are protected
and cannot be deleted or modified by non-administrator users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import frappe
from frappe.model.document import Document

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Roles that are intrinsic to the framework and cannot be deleted.
#: Only the Administrator user may modify these roles.
SYSTEM_ROLES: frozenset[str] = frozenset({
    "Administrator",
    "System Manager",
    "All",
    "Guest",
})

#: Default roles that are auto-created during framework initialisation.
DEFAULT_ROLES: tuple[str, ...] = (
    "Administrator",
    "System Manager",
    "All",
    "Guest",
    "Desk User",
)


class Role(Document):
    """Controller for Role — protects system roles and manages cache."""

    # --------------------------------------------------------------------------
    # Lifecycle hooks
    # --------------------------------------------------------------------------

    def validate(self) -> None:
        """Prevent non-administrators from modifying system roles.

        System roles are critical to framework security. Only the
        Administrator user may edit their properties.

        Raises:
            frappe.PermissionError: If a non-administrator tries to modify
                a system role.
            frappe.ValidationError: If the role name is invalid.
        """
        if self.name in SYSTEM_ROLES:
            if frappe.session.user != "Administrator":
                raise frappe.PermissionError(
                    f"Only Administrator can modify the system role '{self.name}'"
                )

        self.validate_name()
        self.validate_references()

    def on_update(self) -> None:
        """Clear permission caches so the new role definition takes effect.

        This flushes:
        - Per-user role caches
        - DocType permission caches
        - Shared document permission caches
        """
        frappe.cache_manager.clear_cache()

        # If the role name changed, update all user assignments
        if self.get_doc_before_save() and self.name != self.get_doc_before_save().name:
            old_name = self.get_doc_before_save().name
            frappe.db.sql(
                "UPDATE `tabHas Role` SET role = %s WHERE role = %s",
                (self.name, old_name),
            )

    def on_trash(self) -> None:
        """Prevent deletion of system roles.

        System roles are required for the framework to function. Removing
        them would break authentication and authorisation.

        Raises:
            frappe.ValidationError: If the role is a system role.
        """
        if self.name in SYSTEM_ROLES:
            raise frappe.ValidationError(
                f"Cannot delete system role '{self.name}'. "
                "System roles are required for framework operation."
            )

        # Check if any users still have this role assigned
        assigned_users = frappe.db.get_all(
            "Has Role",
            filters={"role": self.name, "parenttype": "User"},
            pluck="parent",
            limit=1,
        )
        if assigned_users:
            raise frappe.ValidationError(
                f"Cannot delete role '{self.name}': it is still assigned to user(s). "
                f"Remove the role from all users first."
            )

        # Clean up related permission records
        frappe.db.delete("DocPerm", {"role": self.name})

    def before_rename(self, old_name: str, new_name: str, merge: bool = False) -> None:
        """Prevent renaming of system roles.

        Args:
            old_name: Current role name.
            new_name: Target role name.
            merge: Whether this is a merge operation.

        Raises:
            frappe.ValidationError: If the role is a system role.
            frappe.ValidationError: If merge is requested.
        """
        if old_name in SYSTEM_ROLES:
            raise frappe.ValidationError(
                f"Cannot rename system role '{old_name}'"
            )
        if merge:
            raise frappe.ValidationError("Merge is not supported for Role")

    # --------------------------------------------------------------------------
    # Validation helpers
    # --------------------------------------------------------------------------

    def validate_name(self) -> None:
        """Ensure the role name is well-formed.

        Role names should be descriptive, human-readable strings.

        Raises:
            frappe.ValidationError: If the role name is empty or too long.
        """
        if not self.name:
            raise frappe.ValidationError("Role name is required")

        if len(self.name) > 140:
            raise frappe.ValidationError(
                f"Role name too long ({len(self.name)} > 140 characters)"
            )

    def validate_references(self) -> None:
        """Validate any linked documents referenced by this role.

        Currently a no-op placeholder for future extensions (e.g. role
        hierarchies, role profiles).
        """
        pass

    # --------------------------------------------------------------------------
    # Query helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def get_user_roles(user: str) -> list[str]:
        """Return all roles assigned to *user*.

        Args:
            user: User name to query.

        Returns:
            List of role names (including the implicit 'All' role).
        """
        roles = frappe.db.get_all(
            "Has Role",
            filters={"parent": user, "parenttype": "User"},
            pluck="role",
        )
        if "All" not in roles:
            roles.append("All")
        return roles

    @staticmethod
    def exists(role: str) -> bool:
        """Check if a role with the given name exists.

        Args:
            role: Role name to check.

        Returns:
            ``True`` if the role exists.
        """
        return bool(frappe.db.exists("Role", role))

    @staticmethod
    def get_users(role: str) -> list[str]:
        """Return names of all users that have *role* assigned.

        Args:
            role: Role name to filter by.

        Returns:
            List of user names.
        """
        return frappe.db.get_all(
            "Has Role",
            filters={"role": role, "parenttype": "User"},
            pluck="parent",
            distinct=True,
        )
