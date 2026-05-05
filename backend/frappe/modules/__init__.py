from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import frappe

# Module-level cache for loaded DocType modules
_doctype_module_cache: dict[str, Any] = {}


def reload_doc(
    module: str,
    dt: str | None = None,
    dn: str | None = None,
    force: bool = False,
    reset_permissions: bool = False,
) -> "frappe.Document | None":
    """Reload a document from its JSON file.

    Finds the document's JSON file within the module's file structure
    and imports it into the database, optionally forcing overwrite.

    Args:
        module: Module name (e.g., 'core', 'custom').
        dt: DocType of the document to reload (e.g., 'DocType', 'Print Format').
        dn: Name of the specific document.
        force: If True, overwrite existing document even if modified.
        reset_permissions: If True, reset permissions to defaults from JSON.

    Returns:
        The imported document, or None if not found.
    """
    if not dt or not dn:
        return None

    # Find the JSON file
    json_path = _find_doc_json(module, dt, dn)
    if not json_path or not os.path.isfile(json_path):
        return None

    # Import the document
    doc = import_file_by_path(json_path, ignore_links=True)

    if doc:
        # Reset permissions if requested
        if reset_permissions and dt == "DocType":
            _reset_permissions(doc.name)

        frappe.db.commit()

    return doc


def load_doctype_module(
    doctype: str,
    module: str | None = None,
    prefix: str = "",
) -> Any:
    """Load the Python module for a DocType's controller.

    Finds and imports the Python module containing the Document
    subclass for the given DocType. Results are cached.

    Args:
        doctype: Name of the DocType.
        module: Optional module name hint.
        prefix: Optional prefix for the module name.

    Returns:
        The loaded Python module.
    """
    cache_key = f"{prefix}{doctype}"
    if cache_key in _doctype_module_cache:
        return _doctype_module_cache[cache_key]

    # Get module from DocType if not provided
    if not module:
        try:
            module = frappe.db.get_value("DocType", doctype, "module")
        except Exception:
            pass

    if not module:
        # Fall back to default document module
        module = frappe
        _doctype_module_cache[cache_key] = module
        return module

    # Construct the module path
    # Pattern: {app}.{module}.doctype.{doctype}.{doctype}
    app = _get_app_for_module(module)

    # Try multiple module path patterns
    module_paths = []

    if prefix:
        module_paths.append(f"{app}.{module}.doctype.{doctype}.{prefix}_{doctype.lower()}")

    module_paths.extend([
        f"{app}.{module}.doctype.{doctype}.{doctype.lower()}",
        f"{app}.{module}.doctype.{doctype}.{doctype}",
        f"{app}.{module}.doctype.{doctype}.doctype",
    ])

    loaded_module = None
    for mod_path in module_paths:
        try:
            loaded_module = frappe.get_module(mod_path)
            break
        except Exception:
            continue

    if not loaded_module:
        # Try filesystem import
        loaded_module = _load_from_filesystem(app, module, doctype, prefix)

    if not loaded_module:
        # Fall back to default document module
        loaded_module = frappe

    _doctype_module_cache[cache_key] = loaded_module
    return loaded_module


def get_doc_path(module: str, doctype: str, name: str) -> str | None:
    """Get filesystem path to a document's JSON file.

    Args:
        module: Module name.
        doctype: DocType of the document.
        name: Document name.

    Returns:
        Absolute path to the JSON file, or None if not found.
    """
    app = _get_app_for_module(module)

    # Standard path: {app}/{module}/{doctype}/{name}/{name}.json
    paths = [
        os.path.join(
            _get_app_path(app), module.replace(" ", "").lower(),
            doctype.lower(), name, f"{name}.json"
        ),
        os.path.join(
            _get_app_path(app), module.replace(" ", "").lower(),
            doctype.lower(), f"{name}.json"
        ),
        os.path.join(
            _get_app_path(app), module.replace(" ", "").lower(),
            doctype.lower(), name, f"{name}.json"
        ),
    ]

    for p in paths:
        if os.path.isfile(p):
            return p

    return None


def get_module_path(module: str, *joins: str) -> str:
    """Get path within a module.

    Args:
        module: Module name.
        *joins: Additional path components.

    Returns:
        Absolute filesystem path.
    """
    app = _get_app_for_module(module)
    app_path = _get_app_path(app)

    module_clean = module.replace(" ", "").lower()
    path = os.path.join(app_path, module_clean, *joins)
    return path


def make_boilerplate(
    template: str,
    doc: "frappe.Document | dict",
    opts: dict | None = None,
) -> str:
    """Generate boilerplate code from templates.

    Args:
        template: Template name or path (e.g., 'controller_template.py').
        doc: Document with context variables.
        opts: Additional template options.

    Returns:
        Generated boilerplate code as string.
    """
    opts = opts or {}

    # Convert doc to dict if needed
    if hasattr(doc, "as_dict"):
        doc_dict = doc.as_dict()
    else:
        doc_dict = dict(doc)

    # Built-in templates
    templates = {
        "doc_type_controller": _CONTROLLER_TEMPLATE,
        "client_script": _CLIENT_SCRIPT_TEMPLATE,
        "test": _TEST_TEMPLATE,
    }

    tmpl = templates.get(template, template)

    # Simple template substitution
    context = {**doc_dict, **opts}
    try:
        result = tmpl.format(**context)
    except KeyError:
        result = tmpl

    return result


def export_doc(
    doctype: str,
    name: str,
    module: str | None = None,
) -> str | None:
    """Export a document to its module's JSON file.

    Saves the document as a JSON file in the appropriate module directory.

    Args:
        doctype: DocType of the document.
        name: Document name.
        module: Target module (inferred from document if not provided).

    Returns:
        Path to the exported file, or None.
    """
    doc = frappe.get_doc(doctype, name)

    if not module:
        module = doc.get("module") if hasattr(doc, "get") else doc.get("module")

    if not module:
        return None

    # Determine export path
    app = _get_app_for_module(module)
    module_clean = module.replace(" ", "").lower()

    export_dir = os.path.join(
        _get_app_path(app),
        module_clean,
        doctype.lower(),
        name,
    )
    os.makedirs(export_dir, exist_ok=True)

    export_path = os.path.join(export_dir, f"{name}.json")

    # Prepare document data for export
    export_data = doc.as_dict()

    # Remove auto-generated fields
    for field in ("creation", "modified", "modified_by", "owner", "docstatus", "idx"):
        export_data.pop(field, None)

    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)

    return export_path


def import_file_by_path(
    path: str,
    ignore_links: bool = False,
    ignore_fields: list[str] | None = None,
) -> "frappe.Document | None":
    """Import a document from a JSON file.

    Args:
        path: Absolute path to the JSON file.
        ignore_links: Skip link validation.
        ignore_fields: Fields to skip during import.

    Returns:
        The imported document, or None.
    """
    if not os.path.isfile(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    if not isinstance(data, dict):
        return None

    # Handle both single doc and {docs: [...]} formats
    if "docs" in data and isinstance(data["docs"], list):
        doc_data = data["docs"][0]
    else:
        doc_data = data

    # Remove fields to ignore
    if ignore_fields:
        for field in ignore_fields:
            doc_data.pop(field, None)

    # Ensure doctype is set
    if "doctype" not in doc_data:
        # Try to infer from file path structure
        # Path: .../module/doctype/DocTypeName/DocTypeName.json
        parts = Path(path).parts
        for i, part in enumerate(parts):
            if part.lower() == "doctype" and i + 1 < len(parts):
                doc_data["doctype"] = parts[i + 1]
                break

    # Check if document exists
    doctype = doc_data.get("doctype")
    name = doc_data.get("name")

    if doctype and name:
        existing = frappe.db.exists(doctype, name)
        if existing:
            # Update existing
            doc = frappe.get_doc(doctype, name)
            for key, value in doc_data.items():
                if key not in ("name", "doctype"):
                    doc.set(key, value)
            doc.save(ignore_permissions=True, ignore_version=True)
        else:
            # Create new
            doc = frappe.get_doc(doc_data)
            doc.insert(ignore_links=ignore_links, ignore_permissions=True)
    else:
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_links=ignore_links, ignore_permissions=True)

    return doc


def get_module_list(app: str | None = None) -> list[str]:
    """Get list of all modules.

    Args:
        app: Optional app name to filter by.

    Returns:
        List of module names.
    """
    modules: list[str] = []

    try:
        filters = {"app_name": app} if app else {}
        modules = frappe.db.get_all(
            "Module Def",
            filters=filters or None,
            fields=["name"],
            order_by="name",
            pluck="name",
        )
    except Exception:
        # Fallback: scan filesystem
        if app:
            app_path = _get_app_path(app)
            if os.path.isdir(app_path):
                for entry in os.listdir(app_path):
                    entry_path = os.path.join(app_path, entry)
                    if os.path.isdir(entry_path) and not entry.startswith((".", "__")):
                        modules.append(entry)
        else:
            for installed_app in frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else []:
                modules.extend(get_module_list(installed_app))

    return sorted(set(modules))


# --- Internal helpers ---


def _find_doc_json(module: str, dt: str, dn: str) -> str | None:
    """Find a document's JSON file in the module structure."""
    path = get_doc_path(module, dt, dn)
    if path and os.path.isfile(path):
        return path

    # Try alternate locations
    app = _get_app_for_module(module)
    app_path = _get_app_path(app)
    module_clean = module.replace(" ", "").lower()

    candidates = [
        os.path.join(app_path, module_clean, dt.lower(), dn, f"{dn}.json"),
        os.path.join(app_path, module_clean, dt.lower(), f"{dn}.json"),
        os.path.join(app_path, module_clean, "doctype", dt.lower(), dn, f"{dn}.json"),
        os.path.join(app_path, module_clean, "doctype", dt.lower(), f"{dn}.json"),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


def _get_app_for_module(module: str) -> str:
    """Get the app that owns a module."""
    try:
        app_name = frappe.db.get_value("Module Def", module, "app_name")
        if app_name:
            return app_name
    except Exception:
        pass

    # Try to find module in installed apps
    for app in frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else ["frappe"]:
        app_path = _get_app_path(app)
        module_clean = module.replace(" ", "").lower()
        if os.path.isdir(os.path.join(app_path, module_clean)):
            return app

    return "frappe"


def _get_app_path(app: str) -> str:
    """Get the base path for an app."""
    if hasattr(frappe, "get_app_path"):
        try:
            return frappe.get_app_path(app)
        except Exception:
            pass
    return os.path.join("apps", app, app)


def _load_from_filesystem(
    app: str,
    module: str,
    doctype: str,
    prefix: str = "",
) -> Any | None:
    """Load a DocType controller module from the filesystem."""
    app_path = _get_app_path(app)
    module_clean = module.replace(" ", "").lower()

    # Possible file paths
    candidates = [
        os.path.join(app_path, module_clean, "doctype", doctype.lower(), f"{doctype.lower()}.py"),
        os.path.join(app_path, module_clean, "doctype", doctype.lower(), f"{doctype}.py"),
    ]

    if prefix:
        candidates.insert(
            0,
            os.path.join(
                app_path, module_clean, "doctype", doctype.lower(),
                f"{prefix}_{doctype.lower()}.py",
            ),
        )

    for candidate in candidates:
        if os.path.isfile(candidate):
            module_name = f"{app}_{module}_{doctype}_controller"
            spec = importlib.util.spec_from_file_location(module_name, candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod

    return None


def _reset_permissions(doctype: str) -> None:
    """Reset permissions for a DocType to defaults."""
    try:
        # Delete existing permissions
        existing = frappe.db.get_all(
            "DocPerm",
            filters={"parent": doctype},
            pluck="name",
        )
        for perm_name in existing:
            frappe.delete_doc("DocPerm", perm_name, ignore_permissions=True, delete_permanently=True)

        # Commit so DocPerm deletions take effect
        frappe.db.commit()
    except Exception:
        pass


# --- Templates ---

_CONTROLLER_TEMPLATE = '''\
from __future__ import annotations

import frappe
from frappe.model.document import Document


class {name}(Document):
	"""DocType controller for {name}."""

	def before_insert(self):
		pass

	def after_insert(self):
		pass

	def validate(self):
		pass

	def on_update(self):
		pass

	def on_submit(self):
		pass

	def on_cancel(self):
		pass

	def on_trash(self):
		pass
'''

_CLIENT_SCRIPT_TEMPLATE = '''\
// Client Script for {name}

frappe.ui.form.on('{name}', {{
	refresh(frm) {{
		// Form refresh logic
	}},

	// onload(frm) {{
	// 	// Form load logic
	// }},

	// before_save(frm) {{
	// 	// Validation before save
	// }},
}});
'''

_TEST_TEMPLATE = '''\
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class Test{name}(FrappeTestCase):
	def setUp(self):
		pass

	def tearDown(self):
		pass

	def test_create_{name_lower}(self):
		"""Test creating a {name} document."""
		doc = frappe.get_doc({{
			"doctype": "{name}",
			"title": "Test {name}",
		}}).insert()
		self.assertIsNotNone(doc.name)
'''
