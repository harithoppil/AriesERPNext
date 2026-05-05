"""
Website rendering with real Jinja2 templating.

Replaces the regex string-replacer with proper Jinja2 Environment.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

import frappe
from frappe.types import _dict

logger = logging.getLogger("frappe.website.serve")

# ─── Jinja2 Setup ────────────────────────────────────────────────────────────

_jinja_env = None


def get_jinja_env():
    """Get or create Jinja2 environment."""
    global _jinja_env
    if _jinja_env is None:
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            # Template directories
            template_paths = []

            # Site public templates
            if hasattr(frappe.local, "site_path"):
                template_paths.append(
                    os.path.join(frappe.local.site_path, "public", "templates")
                )

            # Frappe app templates
            try:
                app_path = frappe.get_app_path("frappe")
                template_paths.append(os.path.join(app_path, "templates"))
            except Exception:
                pass

            # Also check installed apps
            try:
                for app in frappe.get_installed_apps():
                    if app == "frappe":
                        continue
                    try:
                        app_path = frappe.get_app_path(app)
                        template_paths.append(os.path.join(app_path, "templates"))
                        template_paths.append(os.path.join(app_path, "www"))
                    except Exception:
                        pass
            except Exception:
                pass

            # Filter to existing paths
            template_paths = [p for p in template_paths if os.path.isdir(p)]

            # Ensure at least one path
            if not template_paths:
                # Create a dummy loader - templates will be rendered via from_string
                _jinja_env = Environment(
                    autoescape=select_autoescape(["html", "xml"]),
                    trim_blocks=True,
                    lstrip_blocks=True,
                )
            else:
                _jinja_env = Environment(
                    loader=FileSystemLoader(template_paths),
                    autoescape=select_autoescape(["html", "xml"]),
                    trim_blocks=True,
                    lstrip_blocks=True,
                )

            # Add Frappe globals
            _jinja_env.globals.update(_get_jinja_globals())

            # Add Frappe filters
            _jinja_env.filters.update(_get_jinja_filters())

        except ImportError:
            logger.warning("Jinja2 not installed. Using minimal fallback.")
            _jinja_env = None

    return _jinja_env


def _get_jinja_globals() -> dict[str, Any]:
    """Build the dict of global variables exposed to all Jinja2 templates."""
    globals_map: dict[str, Any] = {
        "frappe": frappe,
        "_": frappe._,
        "get_doc": frappe.get_doc,
        "get_list": frappe.get_list,
        "get_all": frappe.get_all,
        "now": frappe.utils.now,
        "today": frappe.utils.today,
        "get_url": frappe.utils.get_url,
        "get_fullname": frappe.utils.get_fullname,
    }

    # Format helpers (graceful fallback if missing)
    try:
        globals_map["format_date"] = frappe.utils.format_date
    except AttributeError:
        pass
    try:
        globals_map["format_datetime"] = frappe.utils.format_datetime
    except AttributeError:
        pass
    try:
        globals_map["format_number"] = frappe.utils.format_number
    except AttributeError:
        globals_map["format_number"] = _format_number_fallback
    try:
        globals_map["format_currency"] = frappe.utils.format_currency
    except AttributeError:
        globals_map["format_currency"] = _format_currency_fallback

    return globals_map


def _get_jinja_filters() -> dict[str, Any]:
    """Build the dict of Jinja2 filters."""
    filters: dict[str, Any] = {
        "json": lambda x: json.dumps(x, default=str),
    }
    try:
        filters["markdown"] = frappe.utils.to_markdown
    except AttributeError:
        pass
    try:
        filters["strip_html"] = frappe.utils.strip_html
    except AttributeError:
        pass
    try:
        filters["sanitize_html"] = frappe.utils.sanitize_html
    except AttributeError:
        pass
    try:
        filters["money_in_words"] = frappe.utils.money_in_words
    except AttributeError:
        pass
    try:
        filters["format_date"] = frappe.utils.format_date
    except AttributeError:
        pass
    try:
        filters["format_datetime"] = frappe.utils.format_datetime
    except AttributeError:
        pass
    return filters


def _format_number_fallback(value: Any, precision: int = 2) -> str:
    """Fallback number formatter when frappe.utils.format_number is unavailable."""
    try:
        return f"{float(value):,.{precision}f}"
    except (ValueError, TypeError):
        return str(value)


def _format_currency_fallback(value: Any, currency: str = "", precision: int = 2) -> str:
    """Fallback currency formatter when frappe.utils.format_currency is unavailable."""
    try:
        return f"{currency} {float(value):,.{precision}f}".strip()
    except (ValueError, TypeError):
        return str(value)


def render_template(template_name: str, context: Optional[dict] = None) -> str:
    """Render a named Jinja2 template file.

    Args:
        template_name: Template path (e.g. "www/about.html").
        context: Context dictionary passed to the template.

    Returns:
        Rendered HTML string.
    """
    env = get_jinja_env()
    if env is None:
        return _minimal_render(template_name, context)

    try:
        template = env.get_template(template_name)
        return template.render(context or {})
    except Exception:
        # If loader-based lookup fails, try treating it as a template string
        if os.path.isfile(template_name):
            with open(template_name, "r", encoding="utf-8") as f:
                content = f.read()
            return render_string(content, context)
        raise


def render_string(template_string: str, context: Optional[dict] = None) -> str:
    """Render a Jinja2 template from a string.

    Args:
        template_string: Raw template content.
        context: Context dictionary passed to the template.

    Returns:
        Rendered HTML string.
    """
    env = get_jinja_env()
    if env is None:
        return _minimal_render_string(template_string, context)

    template = env.from_string(template_string)
    return template.render(context or {})


def _minimal_render(template_name: str, context: Optional[dict] = None) -> str:
    """Minimal fallback when Jinja2 is not available."""
    context = context or {}
    # Try to find the file on disk
    try:
        apps = frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else ["frappe"]
        for app in apps:
            app_path = frappe.get_app_path(app) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app)
            for subdir in ("templates", "www"):
                full_path = os.path.join(app_path, subdir, template_name)
                if os.path.isfile(full_path):
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    return _minimal_render_string(content, context)
    except Exception:
        pass

    # Try direct file path
    if os.path.isfile(template_name):
        with open(template_name, "r", encoding="utf-8") as f:
            return _minimal_render_string(f.read(), context)

    return f"<!-- Template not found: {template_name} -->"


def _minimal_render_string(template_string: str, context: Optional[dict] = None) -> str:
    """Very basic {{ variable }} substitution fallback."""
    context = context or {}

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1).strip()
        parts = var_name.split(".")
        value: Any = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part, "")
            elif hasattr(value, part):
                value = getattr(value, part, "")
            else:
                value = ""
                break
        return str(value) if value is not None else ""

    result = re.sub(r"\{\{\s*(.+?)\s*\}\}", replace_var, template_string)
    return result


# ─── Public exports ─────────────────────────────────────────────────────────

__all__ = [
    "render",
    "resolve_route",
    "get_page_context",
    "get_home_page",
    "get_boot_data",
    "get_website_settings",
    "is_signup_enabled",
    "render_template",
    "render_string",
    "get_jinja_env",
]


def render(path: str | None = None, http_status_code: int | None = None) -> tuple[str, int, dict]:
    """Render a website page.

    Resolves the URL path to a route configuration, builds the page context,
    and renders the appropriate template returning HTML.

    Args:
        path: URL path to render (e.g., '/about', '/blog/post-1').
        http_status_code: Optional HTTP status override.

    Returns:
        Tuple of (html_content, status_code, headers_dict).
    """
    if not path:
        path = frappe.local.request.path if hasattr(frappe.local, "request") else "/"

    # Clean the path
    path = path.strip("/")
    if not path:
        path = get_home_page()

    # Try static file first
    static_response = _try_static_file(path)
    if static_response:
        return static_response

    # Resolve route
    route_info = resolve_route(path)
    if not route_info:
        # 404 page
        return _render_404(), 404, {"Content-Type": "text/html"}

    # Build page context
    context = get_page_context(path, route_info)

    # Render the page
    html = _render_page(route_info, context)

    status = http_status_code or route_info.get("http_status_code", 200)
    headers = {"Content-Type": "text/html; charset=utf-8"}

    return html, status, headers


def resolve_route(path: str) -> _dict | None:
    """Resolve a URL path to a route configuration.

    Checks multiple sources in order:
    1. Website Route Rules (redirects)
    2. Static pages in www/
    3. Web Form routes
    4. DocType web views (published documents)
    5. Blog/Newsletter routes
    6. Static files

    Args:
        path: URL path (without leading/trailing slashes).

    Returns:
        Route configuration _dict, or None if no route found.
    """
    path = path.strip("/")

    # 1. Check Website Route Rules
    route_rule = _check_route_rules(path)
    if route_rule:
        return route_rule

    # 2. Check static pages (www/)
    static_page = _check_static_pages(path)
    if static_page:
        return static_page

    # 3. Check Web Forms
    web_form = _check_web_forms(path)
    if web_form:
        return web_form

    # 4. Check DocType web views
    web_view = _check_doctype_web_views(path)
    if web_view:
        return web_view

    # 5. Check portal pages
    portal_page = _check_portal_pages(path)
    if portal_page:
        return portal_page

    return None


def get_page_context(path: str, route_info: _dict | None = None) -> dict[str, Any]:
    """Build page context for template rendering.

    Constructs the full context dict used when rendering templates,
    including common variables, route-specific data, and user info.

    Args:
        path: URL path.
        route_info: Optional route configuration from resolve_route.

    Returns:
        Context dictionary for template rendering.
    """
    context: dict[str, Any] = {}

    # Common context
    context["path"] = path
    context["frappe"] = frappe
    context["site_name"] = frappe.local.site_name if hasattr(frappe.local, "site_name") else "localhost"
    context["hostname"] = (
        frappe.local.request.host if hasattr(frappe.local, "request") and frappe.local.request else "localhost"
    )

    # User info
    context["user"] = frappe.session.user if hasattr(frappe.session, "user") else "Guest"
    context["is_guest"] = context["user"] == "Guest"

    # Website settings
    context.update(get_website_settings())

    # Boot data for frontend
    context["boot"] = get_boot_data()

    # Route-specific context
    if route_info:
        context.update(route_info.get("context", {}))

        # Load document data if applicable
        if route_info.get("doctype") and route_info.get("docname"):
            try:
                doc = frappe.get_doc(route_info.doctype, route_info.docname)
                context["doc"] = doc
                context.update(doc.as_dict())
            except Exception:
                pass

        # Template override
        if route_info.get("template"):
            context["template"] = route_info.template

    # CSRF token for forms
    if hasattr(frappe.local, "session") and hasattr(frappe.local.session, "data"):
        context["csrf_token"] = frappe.local.session.data.get("csrf_token", "")

    # Add system settings
    try:
        context["system_settings"] = frappe.get_cached_doc("System Settings")
    except Exception:
        context["system_settings"] = {}

    return context


def get_home_page() -> str:
    """Get the homepage route.

    Returns the configured homepage route from Website Settings,
    falling back to defaults.

    Returns:
        Homepage route string (e.g., 'home', 'index').
    """
    try:
        home_page = frappe.db.get_single_value("Website Settings", "home_page")
        if home_page:
            return home_page
    except Exception:
        pass

    # Check for index page
    for candidate in ("home", "index", "main"):
        if _check_static_pages(candidate):
            return candidate

    return "index"


def get_boot_data() -> dict[str, Any]:
    """Get data needed for website frontend.

    Collects data required by the frontend JavaScript for
    initial page load.

    Returns:
        Dictionary of boot data.
    """
    user = (
        frappe.session.user
        if hasattr(frappe.session, "user")
        else "Guest"
    )

    boot = {
        "sysdefaults": {
            "date_format": "yyyy-mm-dd",
            "time_format": "HH:mm:ss",
            "float_precision": 2,
            "currency_precision": 2,
        },
        "user": {
            "name": user,
            "email": user,
            "can_create": [],
            "can_read": [],
            "can_write": [],
            "can_delete": [],
        },
        "lang": frappe.local.lang if hasattr(frappe.local, "lang") else "en",
        "timezone": (
            frappe.db.get_default("timezone")
            or "UTC"
        ),
        "website": get_website_settings(),
    }

    # Add permission info for logged-in users
    if user != "Guest":
        try:
            user_doc = frappe.get_doc("User", user)
            boot["user"]["full_name"] = user_doc.get("full_name", user)
            boot["user"]["user_image"] = user_doc.get("user_image", "")
        except Exception:
            pass

    return boot


def is_signup_enabled() -> bool:
    """Check if website signup is enabled.

    Returns:
        True if new user registration is allowed.
    """
    try:
        return bool(frappe.db.get_single_value("Website Settings", "enable_signup"))
    except Exception:
        return False


def get_website_settings() -> dict[str, Any]:
    """Get website settings dict.

    Loads website configuration settings for use in templates
    and frontend.

    Returns:
        Dictionary of website settings.
    """
    defaults = {
        "website_name": "Frappe",
        "home_page": "home",
        "banner_image": "",
        "brand_html": "",
        "copyright": "",
        "hide_login": False,
        "hide_signup": False,
        "enable_signup": False,
        "show_footer_on_login": True,
        "head_html": "",
        "robots_txt": "",
        "google_analytics_id": "",
        "favicon": "/assets/frappe/images/favicon.png",
        "splash_image": "",
        "app_name": "Frappe",
        "app_logo": "",
        "app_logo_url": "",
        "disable_signup": True,
        "website_theme": "",
        "top_bar_items": [],
        "footer_items": [],
        "footer_logo": "",
        "footer_powered": "",
    }

    try:
        settings = frappe.get_cached_doc("Website Settings")
        for key in defaults:
            if hasattr(settings, key):
                value = getattr(settings, key)
                if value is not None:
                    defaults[key] = value
    except Exception:
        pass

    return defaults


# --- Internal route resolution ---


def _check_route_rules(path: str) -> _dict | None:
    """Check Website Route Rules for redirect matches."""
    try:
        rules = frappe.db.get_all(
            "Website Route Rule",
            fields=["from_route", "to_route", "redirect_http_status"],
        )
        for rule in rules:
            # Exact match
            if rule.from_route == path:
                return _dict({
                    "route_type": "redirect",
                    "to_route": rule.to_route,
                    "http_status_code": rule.redirect_http_status or 301,
                })
            # Pattern match with wildcards
            if "*" in rule.from_route:
                pattern = rule.from_route.replace("*", "(.+)")
                match = re.match(pattern, path)
                if match:
                    to_route = rule.to_route
                    # Replace $1, $2 etc. with captured groups
                    for i, group in enumerate(match.groups(), 1):
                        to_route = to_route.replace(f"${i}", group)
                    return _dict({
                        "route_type": "redirect",
                        "to_route": to_route,
                        "http_status_code": rule.redirect_http_status or 301,
                    })
    except Exception:
        pass

    return None


def _check_static_pages(path: str) -> _dict | None:
    """Check for static HTML templates in the www/ directories."""
    if not path:
        path = "index"

    # Check all apps' www directories
    apps = frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else ["frappe"]

    for app in apps:
        app_path = frappe.get_app_path(app) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app)
        www_dir = os.path.join(app_path, "www")

        if not os.path.isdir(www_dir):
            continue

        # Direct HTML file match
        for ext in (".html", ".md"):
            file_path = os.path.join(www_dir, path + ext)
            if os.path.isfile(file_path):
                return _dict({
                    "route_type": "static_page",
                    "template": file_path,
                    "http_status_code": 200,
                    "context": {"page_title": _format_page_title(path)},
                })

            # Index file in directory
            index_path = os.path.join(www_dir, path, "index" + ext)
            if os.path.isfile(index_path):
                return _dict({
                    "route_type": "static_page",
                    "template": index_path,
                    "http_status_code": 200,
                    "context": {"page_title": _format_page_title(path)},
                })

    return None


def _check_web_forms(path: str) -> _dict | None:
    """Check for published Web Forms."""
    try:
        web_form = frappe.db.get_value(
            "Web Form",
            {"route": path, "published": 1},
            ["name", "title", "module", "allow_edit", "allow_multiple", "login_required"],
            as_dict=True,
        )
        if web_form:
            return _dict({
                "route_type": "web_form",
                "doctype": "Web Form",
                "docname": web_form.name,
                "template": "generators/web_form.html",
                "http_status_code": 200,
                "context": {
                    "web_form": web_form,
                    "page_title": web_form.title,
                },
            })
    except Exception:
        pass

    return None


def _check_doctype_web_views(path: str) -> _dict | None:
    """Check for DocType web views (e.g., /blog/post-name)."""
    # Get DocTypes that have web publishing enabled
    try:
        web_doctypes = frappe.db.get_all(
            "DocType",
            filters={"has_web_view": 1, "allow_guest_to_view": 1},
            fields=["name", "website_search_field"],
        )

        for dt in web_doctypes:
            # Check if path matches route field
            route_field = dt.website_search_field or "route"
            doc = frappe.db.get_value(
                dt.name,
                {route_field: path},
                ["name", route_field],
                as_dict=True,
            )
            if doc:
                return _dict({
                    "route_type": "doctype_web_view",
                    "doctype": dt.name,
                    "docname": doc.name,
                    "template": f"generators/{dt.name.lower()}.html",
                    "http_status_code": 200,
                    "context": {"page_title": doc.name},
                })

        # Check list views: /doctype-name
        for dt in web_doctypes:
            dt_slug = dt.name.lower().replace(" ", "-")
            if path == dt_slug:
                return _dict({
                    "route_type": "doctype_list",
                    "doctype": dt.name,
                    "template": f"list/{dt.name.lower()}.html",
                    "http_status_code": 200,
                    "context": {"page_title": dt.name},
                })
    except Exception:
        pass

    return None


def _check_portal_pages(path: str) -> _dict | None:
    """Check for portal pages (profile, inbox, etc.)."""
    portal_routes = {
        "me": {"template": "portal/me.html", "title": "My Account"},
        "message": {"template": "portal/messages.html", "title": "Messages"},
        "update-profile": {"template": "portal/update-profile.html", "title": "Update Profile"},
        "update-password": {"template": "portal/update-password.html", "title": "Update Password"},
    }

    if path in portal_routes:
        info = portal_routes[path]
        return _dict({
            "route_type": "portal_page",
            "template": info["template"],
            "http_status_code": 200,
            "context": {"page_title": info["title"]},
        })

    return None


def _try_static_file(path: str) -> tuple | None:
    """Try to serve a static file directly.

    Returns:
        Tuple of (content, status, headers) if file found, None otherwise.
    """
    if "." not in path:
        return None

    apps = frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else ["frappe"]

    for app in apps:
        app_path = frappe.get_app_path(app) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app)

        # Check public assets
        for subdir in ("public", "www", "assets"):
            full_path = os.path.join(app_path, subdir, path)
            if os.path.isfile(full_path):
                mime_type, _encoding = mimetypes.guess_type(full_path)
                with open(full_path, "rb") as f:
                    return f.read(), 200, {"Content-Type": mime_type or "application/octet-stream"}

    return None


def _render_page(route_info: _dict, context: dict[str, Any]) -> str:
    """Render a page from route info and context.

    Args:
        route_info: Route configuration.
        context: Template context.

    Returns:
        Rendered HTML string.
    """
    route_type = route_info.get("route_type", "")

    if route_type == "redirect":
        return _render_redirect(route_info.to_route, route_info.get("http_status_code", 301))

    template = route_info.get("template")
    if template:
        return _render_template(template, context)

    # Fallback: render with a generic template
    return _render_generic_page(context)


def _render_template(template_path: str, context: dict[str, Any]) -> str:
    """Render a template file with context.

    Args:
        template_path: Path to template file.
        context: Template context dict.

    Returns:
        Rendered HTML string.
    """
    # Use real Jinja2 rendering
    try:
        return render_template(template_path, context)
    except Exception as exc:
        logger.error("Template render failed for %s: %s", template_path, exc)
        # Fallback to minimal rendering
        if os.path.isfile(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            return _minimal_render_string(content, context)
        return f"<pre>Error rendering template: {exc}</pre>"


def _render_404() -> str:
    """Render the 404 not found page."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>404 - Page Not Found</title>
</head>
<body>
    <h1>404 - Page Not Found</h1>
    <p>The page you are looking for does not exist.</p>
    <a href="/">Go to Home</a>
</body>
</html>"""


def _render_redirect(to_route: str, status_code: int) -> str:
    """Render a redirect page."""
    if status_code == 301:
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url=/{to_route}">
    <title>Redirecting...</title>
</head>
<body>
    <p>Redirecting to <a href="/{to_route}">{to_route}</a>...</p>
</body>
</html>"""
    else:
        return _render_404()


def _render_generic_page(context: dict[str, Any]) -> str:
    """Render a generic page with context data."""
    title = context.get("page_title", "Untitled")
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
</head>
<body>
    <h1>{title}</h1>
    <pre>{frappe.as_json(context)}</pre>
</body>
</html>"""


def _format_page_title(path: str) -> str:
    """Convert a URL path to a readable page title."""
    return " ".join(path.replace("-", " ").replace("_", " ").split()).title()
