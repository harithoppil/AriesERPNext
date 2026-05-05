from __future__ import annotations

from typing import Any

import frappe


def get_page(page_name: str) -> dict[str, Any]:
    """Load a desktop page/workspace by name.

    Retrieves the full workspace configuration including cards,
    shortcuts, charts, and widgets for the desk UI.

    Args:
        page_name: Name of the workspace/page.

    Returns:
        Dictionary with page configuration.
    """
    try:
        page = frappe.get_doc("Workspace", page_name)
    except Exception:
        # Return a minimal page structure
        return _build_default_page(page_name)

    return {
        "name": page.name,
        "title": page.get("title", page_name),
        "icon": page.get("icon", ""),
        "indicator_color": page.get("indicator_color", ""),
        "charts": _load_charts(page),
        "shortcuts": _load_shortcuts(page),
        "cards": _load_cards(page),
        "onboarding": page.get("onboarding", ""),
        "content": page.get("content", ""),
        "is_editable": page.get("is_standard", 0) == 0,
        "is_standard": page.get("is_standard", 0),
    }


def get_pages_for_user(user: str | None = None) -> list[dict[str, Any]]:
    """Get all workspace pages visible to a user.

    Args:
        user: User to check (defaults to current user).

    Returns:
        List of page summary dicts.
    """
    if not user:
        user = frappe.session.user

    # Get pages the user has access to
    try:
        filters = {"extends_another_page": 0}
        if user != "Administrator":
            filters["for_user"] = ["in", [user, ""]]

        pages = frappe.db.get_all(
            "Workspace",
            filters=filters,
            fields=["name", "title", "icon", "indicator_color", "for_user", "is_standard"],
            order_by="sequence_id asc, name asc",
        )
    except Exception:
        # Workspace DocType may not exist
        return _get_default_pages()

    result = []
    for p in pages:
        # Check module access
        if p.get("module") and not frappe.has_permission(p["module"], "read"):
            continue
        result.append({
            "name": p["name"],
            "title": p.get("title", p["name"]),
            "icon": p.get("icon", ""),
            "indicator_color": p.get("indicator_color", ""),
        })

    return result


def get_desk_items() -> dict[str, list[dict[str, Any]]]:
    """Get all items for the desk sidebar.

    Returns:
        Dict with 'modules', 'admin', 'tools' lists.
    """
    return {
        "modules": _get_modules_for_desk(),
        "admin": _get_admin_items(),
        "tools": _get_tool_items(),
    }


def get_workspace_shortcuts(workspace_name: str) -> list[dict[str, Any]]:
    """Get shortcuts for a workspace.

    Args:
        workspace_name: Name of the workspace.

    Returns:
        List of shortcut dicts.
    """
    try:
        shortcuts = frappe.db.get_all(
            "Workspace Shortcut",
            filters={"parent": workspace_name},
            fields=["type", "link_to", "label", "icon", "restrict_to_domain", "stats_filter", "url"],
            order_by="idx",
        )
        return shortcuts
    except Exception:
        return []


def get_workspace_charts(workspace_name: str) -> list[dict[str, Any]]:
    """Get chart configurations for a workspace.

    Args:
        workspace_name: Name of the workspace.

    Returns:
        List of chart configuration dicts.
    """
    try:
        charts = frappe.db.get_all(
            "Workspace Chart",
            filters={"parent": workspace_name},
            fields=["label", "chart_name", "report_name"],
            order_by="idx",
        )
        return charts
    except Exception:
        return []


def get_workspace_cards(workspace_name: str) -> list[dict[str, Any]]:
    """Get card/link configurations for a workspace.

    Args:
        workspace_name: Name of the workspace.

    Returns:
        List of card configuration dicts.
    """
    try:
        cards = frappe.db.get_all(
            "Workspace Link",
            filters={"parent": workspace_name},
            fields=["type", "link_to", "label", "icon", "onboard", "dependencies"],
            order_by="idx",
        )
        return cards
    except Exception:
        return []


def save_workspace(
    workspace_name: str,
    config: dict[str, Any],
    user: str | None = None,
) -> dict[str, Any]:
    """Save workspace configuration.

    Args:
        workspace_name: Name of the workspace.
        config: New workspace configuration.
        user: User making the change.

    Returns:
        Saved workspace data.
    """
    if not user:
        user = frappe.session.user

    try:
        doc = frappe.get_doc("Workspace", workspace_name)

        # Only allow editing non-standard or user's own workspaces
        if doc.get("is_standard") and doc.get("for_user") != user:
            frappe.throw("Not permitted to edit standard workspace")

        # Update fields
        for key in ("title", "icon", "indicator_color", "content"):
            if key in config:
                doc.set(key, config[key])

        # Handle child tables
        if "shortcuts" in config:
            doc.set("shortcuts", config["shortcuts"])
        if "cards" in config:
            doc.set("cards", config["cards"])
        if "charts" in config:
            doc.set("charts", config["charts"])

        doc.save(ignore_permissions=True)

        return doc.as_dict()
    except Exception:
        frappe.throw("Could not save workspace")
        return {}


def delete_workspace(workspace_name: str) -> None:
    """Delete a custom workspace.

    Args:
        workspace_name: Name of the workspace to delete.
    """
    try:
        doc = frappe.get_doc("Workspace", workspace_name)
        if doc.get("is_standard"):
            frappe.throw("Cannot delete standard workspace")
        doc.delete(ignore_permissions=True)
    except Exception:
        frappe.throw("Could not delete workspace")


def get_onboarding_steps(onboarding_name: str) -> list[dict[str, Any]]:
    """Get onboarding steps for a workspace.

    Args:
        onboarding_name: Name of the onboarding configuration.

    Returns:
        List of step dicts with 'title', 'description', 'action', 'is_complete'.
    """
    try:
        steps = frappe.db.get_all(
            "Onboarding Step",
            filters={"parent": onboarding_name},
            fields=["title", "description", "action_label", "action", "is_complete", "route"],
            order_by="idx",
        )
        return steps
    except Exception:
        return []


def mark_onboarding_complete(onboarding_name: str) -> None:
    """Mark an onboarding as completed for the current user.

    Args:
        onboarding_name: Name of the onboarding.
    """
    user = frappe.session.user
    try:
        # Store completion in cache
        frappe.cache_manager.set(f"onboarding_complete:{user}:{onboarding_name}", True)
    except Exception:
        pass


# --- Internal helpers ---


def _load_charts(page) -> list[dict[str, Any]]:
    """Load chart configurations from a page document."""
    charts: list[dict] = []
    if hasattr(page, "charts") and page.charts:
        for chart in page.charts:
            charts.append({
                "label": chart.get("label", ""),
                "chart_name": chart.get("chart_name", ""),
                "type": chart.get("type", ""),
            })
    return charts


def _load_shortcuts(page) -> list[dict[str, Any]]:
    """Load shortcut configurations from a page document."""
    shortcuts: list[dict] = []
    if hasattr(page, "shortcuts") and page.shortcuts:
        for shortcut in page.shortcuts:
            shortcuts.append({
                "label": shortcut.get("label", ""),
                "type": shortcut.get("type", ""),
                "link_to": shortcut.get("link_to", ""),
                "url": shortcut.get("url", ""),
                "icon": shortcut.get("icon", ""),
            })
    return shortcuts


def _load_cards(page) -> list[dict[str, Any]]:
    """Load card/link configurations from a page document."""
    cards: list[dict] = []
    if hasattr(page, "cards") and page.cards:
        for card in page.cards:
            cards.append({
                "label": card.get("label", ""),
                "type": card.get("type", ""),
                "link_to": card.get("link_to", ""),
                "icon": card.get("icon", ""),
                "description": card.get("description", ""),
            })
    return cards


def _build_default_page(page_name: str) -> dict[str, Any]:
    """Build a minimal default page structure."""
    return {
        "name": page_name,
        "title": page_name.replace("-", " ").title(),
        "icon": "",
        "indicator_color": "",
        "charts": [],
        "shortcuts": [],
        "cards": [],
        "onboarding": "",
        "content": "",
        "is_editable": False,
        "is_standard": True,
    }


def _get_default_pages() -> list[dict[str, str]]:
    """Return default desk pages when Workspace DocType is unavailable."""
    return [
        {"name": "dashboard", "title": "Dashboard", "icon": "dashboard"},
        {"name": "awesome-bar", "title": "Search", "icon": "search"},
        {"name": "build", "title": "Build", "icon": "tool"},
        {"name": "settings", "title": "Settings", "icon": "setting"},
    ]


def _get_modules_for_desk() -> list[dict[str, Any]]:
    """Get modules visible on the desk."""
    modules: list[dict] = []

    try:
        results = frappe.db.get_all(
            "Module Def",
            filters={"app_name": ("!=", ""), "custom": 0},
            fields=["name", "module_name", "app_name"],
            order_by="module_name",
        )
        for r in results:
            modules.append({
                "name": r["name"],
                "label": r.get("module_name", r["name"]),
                "app": r.get("app_name", ""),
            })
    except Exception:
        # Fallback defaults
        modules = [
            {"name": "core", "label": "Core", "app": "frappe"},
            {"name": "custom", "label": "Customize", "app": "frappe"},
        ]

    return modules


def _get_admin_items() -> list[dict[str, Any]]:
    """Get admin menu items for the desk."""
    return [
        {"label": "Users", "route": "/app/List/User", "icon": "users"},
        {"label": "Roles", "route": "/app/List/Role", "icon": "shield"},
        {"label": "Role Profile", "route": "/app/List/Role Profile", "icon": "user-check"},
        {"label": "Permission Manager", "route": "/app/permission-manager", "icon": "lock"},
        {"label": "Doctype", "route": "/app/List/DocType", "icon": "database"},
        {"label": "Customize Form", "route": "/app/customize-form", "icon": "edit"},
        {"label": "System Settings", "route": "/app/Form/System Settings", "icon": "settings"},
    ]


def _get_tool_items() -> list[dict[str, Any]]:
    """Get tool menu items for the desk."""
    return [
        {"label": "Import Data", "route": "/app/data-import", "icon": "upload"},
        {"label": "Export Data", "route": "/app/List/Data Export", "icon": "download"},
        {"label": "Background Jobs", "route": "/app/background_jobs", "icon": "activity"},
        {"label": "Error Log", "route": "/app/List/Error Log", "icon": "alert-circle"},
        {"label": "Scheduled Job Type", "route": "/app/List/Scheduled Job Type", "icon": "clock"},
    ]
