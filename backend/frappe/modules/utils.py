from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import frappe


def get_module_app(module: str) -> str | None:
    """Get the app that contains a module.

    Args:
        module: Module name.

    Returns:
        App name, or None if not found.
    """
    try:
        app = frappe.db.get_value("Module Def", module, "app_name")
        if app:
            return app
    except Exception:
        pass

    # Fallback: scan installed apps
    for app in frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else ["frappe"]:
        app_path = frappe.get_app_path(app) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app)
        module_path = os.path.join(app_path, module.replace(" ", "").lower())
        if os.path.isdir(module_path):
            return app

    return None


def get_app_modules(app: str) -> list[str]:
    """Get all modules belonging to an app.

    Args:
        app: App name.

    Returns:
        List of module names.
    """
    modules: list[str] = []

    try:
        modules = frappe.db.get_all(
            "Module Def",
            filters={"app_name": app},
            fields=["name"],
            order_by="name",
            pluck="name",
        )
    except Exception:
        pass

    return modules


def export_module_json(doc: "frappe.Document", module: str, create_init: bool = True) -> str | None:
    """Export a document as JSON to its module directory.

    Args:
        doc: Document to export.
        module: Target module name.
        create_init: Whether to create __init__.py if missing.

    Returns:
        Path to exported file, or None.
    """
    app = get_module_app(module) or "frappe"

    # Determine export path
    if hasattr(frappe, "get_app_path"):
        app_path = frappe.get_app_path(app)
    else:
        app_path = os.path.join("apps", app, app)

    module_clean = module.replace(" ", "").lower()

    export_dir = os.path.join(
        app_path,
        module_clean,
        doc.doctype.lower(),
        doc.name,
    )
    os.makedirs(export_dir, exist_ok=True)

    if create_init:
        init_file = os.path.join(export_dir, "__init__.py")
        if not os.path.isfile(init_file):
            Path(init_file).touch()

    # Prepare data
    data = doc.as_dict()

    # Remove system fields
    for field in ("creation", "modified", "modified_by", "owner", "docstatus", "idx"):
        data.pop(field, None)

    export_path = os.path.join(export_dir, f"{doc.name}.json")

    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    return export_path


def get_module_from_doctype(doctype: str) -> str | None:
    """Get the module that owns a DocType.

    Args:
        doctype: DocType name.

    Returns:
        Module name, or None.
    """
    try:
        module = frappe.db.get_value("DocType", doctype, "module")
        return module
    except Exception:
        return None


def scrub(txt: str) -> str:
    """Convert a string to a valid Python module name.

    Replaces spaces and special characters with underscores
    and converts to lowercase.

    Args:
        txt: Input string.

    Returns:
        Scrubbed module name.
    """
    return txt.replace(" ", "_").replace("-", "_").lower()


def scrub_dt_name(doctype: str) -> str:
    """Scrub a DocType name for use as a module name.

    Args:
        doctype: DocType name.

    Returns:
        Scrubbed name.
    """
    return scrub(doctype)


def make_boilerplate(path: str, template: str, context: dict[str, Any]) -> None:
    """Create a file from a boilerplate template.

    Args:
        path: Destination file path.
        template: Template string with {placeholders}.
        context: Dictionary of values to substitute.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    try:
        content = template.format(**context)
    except KeyError:
        content = template

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_doc_module(doctype: str, name: str) -> Any | None:
    """Get the Python module for a specific document's controller.

    Args:
        doctype: DocType name.
        name: Document name.

    Returns:
        The controller module, or None.
    """
    from frappe.modules import load_doctype_module

    try:
        return load_doctype_module(doctype)
    except Exception:
        return None


def get_file_items(path: str, raise_not_found: bool = False, ignore_empty_lines: bool = True) -> list[str]:
    """Read a file and return non-empty lines as a list.

    Args:
        path: File path.
        raise_not_found: Raise exception if file not found.
        ignore_empty_lines: Skip empty lines.

    Returns:
        List of line strings.
    """
    if not os.path.isfile(path):
        if raise_not_found:
            raise FileNotFoundError(f"File not found: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if ignore_empty_lines:
        lines = [line for line in lines if line.strip()]

    return lines


def get_folder_size(path: str) -> int:
    """Calculate total size of a directory in bytes.

    Args:
        path: Directory path.

    Returns:
        Total size in bytes.
    """
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def get_app_publisher(app: str) -> str:
    """Get the publisher of an app from its hooks.

    Args:
        app: App name.

    Returns:
        Publisher string.
    """
    try:
        app_hooks = frappe.get_hooks(app_name=app)
        if app_hooks:
            publisher = app_hooks.get("app_publisher")
            if isinstance(publisher, list):
                publisher = publisher[0]
            return publisher or ""
    except Exception:
        pass
    return ""


def get_app_version(app: str) -> str:
    """Get the version of an app.

    Args:
        app: App name.

    Returns:
        Version string.
    """
    try:
        app_hooks = frappe.get_hooks(app_name=app)
        if app_hooks:
            version = app_hooks.get("app_version")
            if isinstance(version, list):
                version = version[0]
            return version or "0.0.1"
    except Exception:
        pass
    return "0.0.1"


def get_app_title(app: str) -> str:
    """Get the title of an app.

    Args:
        app: App name.

    Returns:
        App title string.
    """
    try:
        app_hooks = frappe.get_hooks(app_name=app)
        if app_hooks:
            title = app_hooks.get("app_title")
            if isinstance(title, list):
                title = title[0]
            return title or app
    except Exception:
        pass
    return app


def list_all_modules() -> list[str]:
    """List all modules across all installed apps.

    Returns:
        List of module names.
    """
    all_modules: set[str] = set()

    for app in frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else ["frappe"]:
        modules = get_app_modules(app)
        all_modules.update(modules)

    return sorted(all_modules)


def is_module_installed(module: str) -> bool:
    """Check if a module is installed.

    Args:
        module: Module name.

    Returns:
        True if the module exists.
    """
    try:
        return frappe.db.exists("Module Def", module) is not None
    except Exception:
        return False


def reload_doctype_module(doctype: str) -> None:
    """Force reload of a DocType's controller module.

    Clears the module cache and re-imports the controller.

    Args:
        doctype: DocType name.
    """
    from frappe.modules import _doctype_module_cache, load_doctype_module

    cache_key = doctype
    _doctype_module_cache.pop(cache_key, None)

    # Also clear prefixed variants
    keys_to_remove = [k for k in _doctype_module_cache if k.endswith(doctype)]
    for k in keys_to_remove:
        _doctype_module_cache.pop(k, None)

    load_doctype_module(doctype)


def delete_folder(path: str, with_files: bool = False) -> None:
    """Delete a module folder.

    Args:
        path: Folder path to delete.
        with_files: If True, also delete database records.
    """
    if os.path.isdir(path):
        if with_files:
            shutil.rmtree(path)
        else:
            # Only delete Python files, preserve JSON data
            for root, _dirs, files in os.walk(path):
                for f in files:
                    if f.endswith(".py"):
                        os.remove(os.path.join(root, f))


def get_module_info(module: str) -> dict[str, Any] | None:
    """Get metadata about a module.

    Args:
        module: Module name.

    Returns:
        Dict with module info, or None.
    """
    try:
        info = frappe.db.get_value(
            "Module Def",
            module,
            ["name", "app_name", "module_name", "restrict_to_domain"],
            as_dict=True,
        )
        return info
    except Exception:
        return None


def get_doctypes_with_customizations(module: str) -> list[str]:
    """Get DocTypes in a module that have custom fields.

    Args:
        module: Module name.

    Returns:
        List of DocType names.
    """
    try:
        doctypes = frappe.db.get_all(
            "DocType",
            filters={"module": module, "custom": 1},
            pluck="name",
        )
        return doctypes
    except Exception:
        return []


def get_module_doctypes(module: str) -> list[str]:
    """Get all DocTypes belonging to a module.

    Args:
        module: Module name.

    Returns:
        List of DocType names.
    """
    try:
        doctypes = frappe.db.get_all(
            "DocType",
            filters={"module": module},
            fields=["name", "istable", "issingle", "custom"],
            order_by="name",
        )
        return [d.name for d in doctypes]
    except Exception:
        return []
