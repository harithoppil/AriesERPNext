from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import frappe


def get_home_page_via_hooks() -> str | None:
    """Get homepage via app hooks.

    Checks installed apps for a 'get_website_user_home_page' hook
    that can customize the homepage per user.

    Returns:
        Homepage route string, or None.
    """
    hooks = frappe.get_hooks("get_website_user_home_page")
    if hooks:
        for hook in hooks:
            try:
                result = frappe.call(hook, frappe.session.user)
                if result:
                    return result
            except Exception:
                continue
    return None


def can_cache_page(path: str) -> bool:
    """Determine if a page can be cached.

    Pages with user-specific content should not be cached.

    Args:
        path: URL path.

    Returns:
        True if the page is cacheable.
    """
    # Don't cache portal/private pages
    non_cacheable_prefixes = ("me", "message", "update-", "login", "logout", "desk")
    if any(path.startswith(prefix) for prefix in non_cacheable_prefixes):
        return False

    # Don't cache if user is logged in
    if frappe.session.user != "Guest":
        return False

    return True


def get_html_content_based_on_user(path: str) -> str | None:
    """Get HTML content for a path considering user context.

    Args:
        path: URL path.

    Returns:
        HTML content if a user-specific page exists.
    """
    # This is a hook point for apps to customize content
    hooks = frappe.get_hooks("website_route_condition")
    if hooks:
        for hook in hooks:
            try:
                result = frappe.call(hook, path)
                if result:
                    return result
            except Exception:
                continue
    return None


def get_comment_list(doctype: str, name: str) -> list[dict]:
    """Get comments for a document.

    Args:
        doctype: DocType name.
        name: Document name.

    Returns:
        List of comment dictionaries.
    """
    try:
        comments = frappe.db.get_all(
            "Comment",
            filters={
                "reference_doctype": doctype,
                "reference_name": name,
                "comment_type": "Comment",
            },
            fields=["name", "content", "owner", "creation", "modified_by"],
            order_by="creation desc",
        )
        return comments
    except Exception:
        return []


def get_tag_list(doctype: str, name: str) -> list[str]:
    """Get tags for a document.

    Args:
        doctype: DocType name.
        name: Document name.

    Returns:
        List of tag strings.
    """
    try:
        tags = frappe.db.get_value(doctype, name, "_user_tags")
        if tags:
            return [t.strip() for t in tags.split(",") if t.strip()]
    except Exception:
        pass
    return []


def get_sidebar_items(path: str) -> list[dict]:
    """Get sidebar items for a page.

    Args:
        path: Current URL path.

    Returns:
        List of sidebar item dicts with 'label', 'route', 'active'.
    """
    items: list[dict] = []

    try:
        # Get sidebar from Website Settings
        settings = frappe.get_cached_doc("Website Settings")
        if hasattr(settings, "sidebar_items") and settings.sidebar_items:
            for item in settings.sidebar_items:
                route = item.get("route", "") if isinstance(item, dict) else getattr(item, "route", "")
                label = item.get("label", "") if isinstance(item, dict) else getattr(item, "label", "")
                items.append({
                    "label": label,
                    "route": route,
                    "active": path.strip("/") == route.strip("/"),
                })
    except Exception:
        pass

    return items


def get_breadcrumbs(path: str) -> list[dict]:
    """Build breadcrumb trail for a URL path.

    Args:
        path: URL path (e.g., 'blog/post-1').

    Returns:
        List of breadcrumb dicts with 'label' and 'route'.
    """
    breadcrumbs: list[dict] = [{"label": "Home", "route": "/"}]

    parts = path.strip("/").split("/")
    cumulative = ""

    for part in parts:
        if not part:
            continue
        cumulative += f"/{part}"
        breadcrumbs.append({
            "label": part.replace("-", " ").title(),
            "route": cumulative,
        })

    return breadcrumbs


def cleanup_page_name(title: str) -> str:
    """Convert a title to a URL-safe page name.

    Args:
        title: Page title.

    Returns:
        URL-safe slug string.
    """
    # Lowercase and replace spaces with hyphens
    slug = title.lower()
    # Remove special characters
    slug = re.sub(r"[^\w\s-]", "", slug)
    # Replace spaces/hyphens with single hyphen
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def get_full_index(route_list: list[str] | None = None) -> list[dict]:
    """Get a full index of website routes.

    Args:
        route_list: Optional list of routes to filter.

    Returns:
        List of route dicts with 'route', 'title', 'content'.
    """
    routes: list[dict] = []

    # Get static pages
    apps = frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else ["frappe"]
    for app in apps:
        app_path = frappe.get_app_path(app) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app)
        www_dir = os.path.join(app_path, "www")
        if os.path.isdir(www_dir):
            for root, _dirs, files in os.walk(www_dir):
                for f in files:
                    if f.endswith(".html"):
                        rel_path = os.path.relpath(os.path.join(root, f), www_dir)
                        route = "/" + rel_path.replace("\\", "/").replace(".html", "").replace("/index", "")
                        if route_list and route not in route_list:
                            continue
                        routes.append({
                            "route": route,
                            "title": f.replace(".html", "").replace("-", " ").title(),
                        })

    return routes


def get_toc(route: str) -> list[dict]:
    """Get table of contents for a route.

    Args:
        route: URL route.

    Returns:
        List of TOC item dicts.
    """
    # Placeholder - actual implementation would parse headers from content
    return []


def set_cookie(key: str, value: str, expires_in_days: int = 30, secure: bool = False) -> None:
    """Set a cookie in the response.

    Args:
        key: Cookie name.
        value: Cookie value.
        expires_in_days: Cookie expiry in days.
        secure: Whether cookie should be secure-only.
    """
    if hasattr(frappe.local, "cookie_manager"):
        frappe.local.cookie_manager.set_cookie(key, value, expires_in_days, secure)


def get_cookie(key: str, default: str | None = None) -> str | None:
    """Get a cookie value from the request.

    Args:
        key: Cookie name.
        default: Default value if cookie not found.

    Returns:
        Cookie value, or default.
    """
    if hasattr(frappe.local, "request") and frappe.local.request:
        return frappe.local.request.cookies.get(key, default)
    return default


def get_site_logo() -> str:
    """Get the site logo URL.

    Returns:
        URL path to site logo.
    """
    try:
        logo = frappe.db.get_single_value("Website Settings", "app_logo")
        if logo:
            return logo
    except Exception:
        pass
    return "/assets/frappe/images/frappe-framework-logo.svg"


def abs_url(url: str) -> str:
    """Convert a relative URL to an absolute URL.

    Args:
        url: Relative or absolute URL.

    Returns:
        Absolute URL string.
    """
    if url.startswith(("http://", "https://")):
        return url

    host = (
        frappe.local.request.host_url
        if hasattr(frappe.local, "request") and frappe.local.request
        else "/"
    )
    if url.startswith("/"):
        return host.rstrip("/") + url
    return host.rstrip("/") + "/" + url


def get_page_title_from_route(path: str) -> str:
    """Get a page title from a URL route.

    Args:
        path: URL path.

    Returns:
        Formatted page title.
    """
    # Remove leading/trailing slashes
    path = path.strip("/")

    # Try to find a matching document with a title
    parts = path.split("/")
    if len(parts) >= 2:
        try:
            dt = parts[0].replace("-", " ").title()
            dn = parts[1]
            doc = frappe.db.get_value(dt, dn, "title")
            if doc:
                return doc
        except Exception:
            pass

    # Fallback: format the path
    return path.replace("-", " ").replace("/", " — ").title()


def add_next_prev_links(context: dict, path: str) -> None:
    """Add next/previous navigation links to context.

    For routes that are part of a sequence (like blog posts),
    adds links to adjacent items.

    Args:
        context: Page context dict (modified in place).
        path: Current URL path.
    """
    # Check if this is a web view route
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return

    try:
        doctype = parts[0].replace("-", " ").title()
        # Get adjacent items based on creation date
        current_doc = context.get("doc")
        if not current_doc or not hasattr(current_doc, "creation"):
            return

        prev_doc = frappe.db.get_value(
            doctype,
            {"creation": ("<", current_doc.creation), "published": 1},
            ["name", "route", "title"],
            order_by="creation desc",
            as_dict=True,
        )
        if prev_doc:
            context["prev"] = prev_doc

        next_doc = frappe.db.get_value(
            doctype,
            {"creation": (">", current_doc.creation), "published": 1},
            ["name", "route", "title"],
            order_by="creation asc",
            as_dict=True,
        )
        if next_doc:
            context["next"] = next_doc
    except Exception:
        pass


def get_web_blocks(block_names: list[str]) -> list[dict]:
    """Get web page block configurations.

    Args:
        block_names: List of web block names.

    Returns:
        List of block configuration dicts.
    """
    blocks: list[dict] = []
    try:
        for name in block_names:
            block = frappe.db.get_value(
                "Web Page Block",
                name,
                ["name", "web_template", "web_template_values"],
                as_dict=True,
            )
            if block:
                blocks.append(block)
    except Exception:
        pass
    return blocks


def get_context_data(context: dict[str, Any]) -> dict[str, Any]:
    """Enhance page context with common data.

    Adds frequently used data to the context like footer items,
    top bar, and common settings.

    Args:
        context: Base context dict.

    Returns:
        Enhanced context dict.
    """
    # Top bar items
    try:
        settings = frappe.get_cached_doc("Website Settings")
        if hasattr(settings, "top_bar_items") and settings.top_bar_items:
            context["top_bar_items"] = settings.top_bar_items
        if hasattr(settings, "footer_items") and settings.footer_items:
            context["footer_items"] = settings.footer_items
    except Exception:
        context["top_bar_items"] = []
        context["footer_items"] = []

    # Meta tags
    context.setdefault("meta", {})
    if not context["meta"].get("title"):
        context["meta"]["title"] = context.get("page_title", "")
    if not context["meta"].get("description"):
        context["meta"]["description"] = context.get("meta_description", "")
    if not context["meta"].get("image"):
        context["meta"]["image"] = context.get("meta_image", "")

    return context


def get_hex_shade(color: str, percent: int) -> str:
    """Lighten or darken a hex color by a percentage.

    Args:
        color: Hex color string (e.g., '#FF5733').
        percent: Percentage to adjust (-100 to 100).

    Returns:
        Adjusted hex color string.
    """
    color = color.lstrip("#")
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)

    if percent > 0:
        r = min(255, r + int((255 - r) * percent / 100))
        g = min(255, g + int((255 - g) * percent / 100))
        b = min(255, b + int((255 - b) * percent / 100))
    else:
        r = max(0, r + int(r * percent / 100))
        g = max(0, g + int(g * percent / 100))
        b = max(0, b + int(b * percent / 100))

    return f"#{r:02x}{g:02x}{b:02x}"
