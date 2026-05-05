"""
frappe.utils.user — User permission helpers and user queries.

Provides a cache-friendly way to look up a user's roles and
DocType-level permissions, plus standalone helpers for fetching
user metadata.
"""

from __future__ import annotations

from typing import Any

from frappe.utils.data import _dict, cstr


# ---------------------------------------------------------------------------
# Module-level cache so that repeated lookups in the same request are cheap.
# The key is ``user_name``.
# ---------------------------------------------------------------------------
_role_cache: dict[str, list[str]] = {}
_perm_cache: dict[str, dict[str, _dict]] = {}


class UserPermissions:
    """Caches roles and DocType permissions for a single user.

    Typical usage::

        perms = UserPermissions("Administrator")
        if perms.has_permission("Sales Order", "read"):
            ...
    """

    def __init__(self, user: str) -> None:
        self.user: str = user

    # -- public API --------------------------------------------------------

    def get_roles(self) -> list[str]:
        """Return the list of role names assigned to this user.

        Results are cached per-request in the module-level ``_role_cache``.
        """
        if self.user in _role_cache:
            return _role_cache[self.user]

        roles: list[str] = []
        try:
            import frappe

            # The user always implicitly has "All"
            roles.append("All")

            # Fetch from the User document
            user_doc = frappe.get_doc("User", self.user)
            for role_row in user_doc.get("roles", []):
                role = cstr(role_row.role)
                if role and role not in roles:
                    roles.append(role)

            # In Frappe, the session user also gets their username as a role
            # (used for user-specific permissions)
            if self.user not in roles:
                roles.append(self.user)

        except Exception:
            # During bootstrap or when the "User" DocType doesn't exist yet,
            # fall back to a sensible default.
            roles = ["All", self.user, "System Manager" if self.user == "Administrator" else "Guest"]

        _role_cache[self.user] = roles
        return roles

    def get_permissions(self, doctype: str) -> _dict:
        """Return a ``_dict`` with permission flags for *doctype*.

        Keys typically include ``read``, ``write``, ``create``, ``delete``,
        ``submit``, ``cancel``, ``amend``, ``print``, ``email``,
        ``report``, ``import``, ``export``, ``share``.

        Each value is ``1`` (allowed) or ``0`` (not allowed).
        """
        cache_key = f"{self.user}:{doctype}"
        if cache_key in _perm_cache.get(self.user, {}):
            return _perm_cache[self.user][cache_key]

        perms = self._load_permissions(doctype)

        if self.user not in _perm_cache:
            _perm_cache[self.user] = {}
        _perm_cache[self.user][cache_key] = perms
        return perms

    def has_permission(self, doctype: str, ptype: str = "read") -> bool:
        """Return ``True`` if the user has *ptype* permission on *doctype*.

        *ptype* is one of the standard permission types (``read``,
        ``write``, ``create``, …).
        """
        perms = self.get_permissions(doctype)
        return bool(perms.get(ptype, 0))

    # -- internal helpers --------------------------------------------------

    def _load_permissions(self, doctype: str) -> _dict:
        """Hit the database (or DocPerm cache) to build the permission map."""
        roles = self.get_roles()
        result: dict[str, int] = {}

        try:
            import frappe

            # Fetch DocPerm records for this DocType where role in user's roles
            doc_perms = frappe.get_all(
                "DocPerm",
                filters={"parent": doctype, "role": ["in", roles]},
                fields=[
                    "role",
                    "read",
                    "write",
                    "create",
                    "delete",
                    "submit",
                    "cancel",
                    "amend",
                    "print",
                    "email",
                    "report",
                    "import",
                    "export",
                    "share",
                ],
            )

            for perm_row in doc_perms:
                for key, value in perm_row.items():
                    if key == "role":
                        continue
                    # If any role grants the permission, set it to 1
                    if value:
                        result[key] = 1

        except Exception:
            # If DocPerm doesn't exist yet (bootstrap), default to no perms
            pass

        return _dict(result)


def get_user_fullname(user: str) -> str:
    """Return the full name of *user*.

    Falls back to the raw *user* value on error.
    """
    try:
        import frappe

        fullname = frappe.db.get_value("User", user, "full_name")
        if fullname:
            return fullname
    except Exception:
        pass
    return user


def get_users_with_role(role: str) -> list[str]:
    """Return a list of user names that have *role* assigned."""
    try:
        import frappe

        users = frappe.get_all(
            "Has Role",
            filters={"role": role, "parenttype": "User"},
            fields=["parent"],
            distinct=True,
        )
        return sorted({u.parent for u in users})
    except Exception:
        return []
