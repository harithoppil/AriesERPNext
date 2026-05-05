"""
Frappe — Clean-Room Framework Replacement

A from-scratch, modern Python reimplementation of the Frappe framework
that maintains API compatibility with ERPNext.

Key design decisions:
- SQLite as primary database (PostgreSQL support planned)
- Pydantic for type safety
- contextvars instead of werkzeug.local
- Async-native where possible, sync wrappers for compatibility
"""

from __future__ import annotations

import functools
import importlib
import inspect
import json
import os
import re
import sys
import threading
import warnings
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    TypeAlias,
    Union,
)

# ── Version ──
__version__ = "17.0.0-replacement"
__title__ = "Frappe Framework (Replacement)"

# ── Local context ──
from frappe.local import (
    Local,
    LocalProxy,
    initialize_context,
    release_context,
    get_context,
)
from frappe.types import _dict

# ── Exceptions ──
from frappe.exceptions import *

# ── Type aliases ──
if TYPE_CHECKING:
    from logging import Logger

    from frappe.database.database import Database
    from frappe.model.document import Document

# ── Controller registries ──
controllers: dict[str, type] = {}
lazy_controllers: dict[str, type] = {}

# ── Thread-local storage ──
local = Local()
STANDARD_USERS = ("Guest", "Administrator")
SITE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
in_test = False

_dev_server = int(os.environ.get("DEV_SERVER", False))

if _dev_server:
    warnings.simplefilter("always", DeprecationWarning)
    warnings.simplefilter("always", PendingDeprecationWarning)


# ═══════════════════════════════════════════════════════════════════════════════
#  LOCAL PROXIES
# ═══════════════════════════════════════════════════════════════════════════════

db: "Database" = local("db")  # type: ignore[assignment]
conf: Any = local("conf")  # type: ignore[assignment]
form_dict: Any = local("form_dict")  # type: ignore[assignment]
form = form_dict
request: Any = local("request")  # type: ignore[assignment]
job: Any = local("job")  # type: ignore[assignment]
response: Any = local("response")  # type: ignore[assignment]
session: Any = local("session")  # type: ignore[assignment]
user: str = local("user")  # type: ignore[assignment]
flags: Any = local("flags")  # type: ignore[assignment]
error_log: list[dict[str, str]] = local("error_log")  # type: ignore[assignment]
debug_log: list[str] = local("debug_log")  # type: ignore[assignment]
message_log: list[Any] = local("message_log")  # type: ignore[assignment]
lang: str = local("lang")  # type: ignore[assignment]
# cache is lazy-loaded from cache_manager via __getattr__


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════


def init(site: str, sites_path: str = ".", new_site: bool = False, force: bool = False) -> None:
    """Initialize frappe for the current site."""
    if hasattr(local, "initialised") and local.initialised and not force:
        return

    if site and not SITE_NAME_PATTERN.match(site):
        raise ValueError(f"Invalid site name `{site}`")

    ctx = initialize_context()

    ctx.error_log = []
    ctx.message_log = []
    ctx.debug_log = []
    ctx.flags = _dict(
        {
            "currently_saving": [],
            "redirect_location": "",
            "in_install_db": False,
            "in_install_app": False,
            "in_import": False,
            "in_test": in_test,
            "mute_messages": False,
            "ignore_links": False,
            "mute_emails": False,
            "has_dataurl": False,
            "new_site": new_site,
            "read_only": False,
        }
    )
    ctx.locked_documents = []
    ctx.test_objects = defaultdict(list)

    ctx.site = site
    ctx.site_name = site
    ctx.sites_path = sites_path
    site_path = os.path.join(sites_path, site)
    ctx.site_path = site_path
    ctx.all_apps = None

    ctx.request_ip = None
    ctx.response = _dict({"docs": []})
    ctx.response_headers = {}
    ctx.task_id = None

    # Load configuration
    from frappe.config import get_site_config

    ctx.conf = get_site_config(sites_path=sites_path, site_path=site_path, cached=False)
    ctx.lang = ctx.conf.lang or "en"

    ctx.module_app = None
    ctx.app_modules = None

    ctx.user = None
    ctx.user_perms = None
    ctx.role_permissions = {}
    ctx.valid_columns = {}
    ctx.new_doc_templates = {}

    ctx.request_cache = defaultdict(dict)
    ctx.jenv = None
    ctx.jloader = None
    ctx.cache = {}
    ctx.form_dict = _dict()
    ctx.preload_assets = {"style": [], "script": [], "icons": []}
    ctx.session = _dict(user="Guest", data=_dict())
    ctx.dev_server = _dev_server

    # Setup module map
    try:
        setup_module_map(include_all_apps=True)
    except Exception:
        pass

    ctx.initialised = True


def connect(site: str | None = None, db_name: str | None = None, set_admin_as_user: bool = True) -> None:
    """Connect to site database instance."""
    from frappe.database import get_db

    if site:
        init(site)

    conf = local.conf
    db_name_ = db_name or conf.db_name
    db_user = conf.get("db_user")
    db_password = conf.get("db_password")

    assert db_name_, "site must be fully initialized, db_name missing"

    # Construct proper DB path for SQLite (store DB in site directory)
    site_path = local.site_path
    db_type = conf.get("db_type", "sqlite")
    if db_type == "sqlite" and not os.path.isabs(db_name_):
        db_path = os.path.join(site_path, f"{db_name_}.db")
    else:
        db_path = db_name_

    local.db = get_db(
        host=conf.get("db_host", "localhost"),
        port=conf.get("db_port"),
        user=db_user,
        password=db_password,
        database=db_path,
    )

    if set_admin_as_user:
        set_user("Administrator")


def destroy() -> None:
    """Closes connection and releases local context."""
    if hasattr(local, "db") and local.db:
        try:
            local.db.close()
        except Exception:
            pass
    release_context()


class init_site:
    """Context manager for site initialization."""

    def __init__(self, site=None):
        self.site = site or ""

    def __enter__(self):
        init(self.site)
        return local

    def __exit__(self, type, value, traceback):
        destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOGGING & MESSAGING
# ═══════════════════════════════════════════════════════════════════════════════


def errprint(msg: str) -> None:
    """Log error sent back as `exc` in response."""
    from frappe.utils.data import as_unicode

    msg = as_unicode(msg)
    if not request or ("cmd" not in local.form_dict) or conf.developer_mode:
        print(msg)
    error_log.append({"exc": msg})


def log(msg: str) -> None:
    """Add to `debug_log`."""
    from frappe.utils.data import as_unicode

    print(msg, file=sys.stderr)
    debug_log.append(as_unicode(msg))


def clear_last_message() -> None:
    """Clear the last message from message_log."""
    if message_log:
        message_log.pop()


# ═══════════════════════════════════════════════════════════════════════════════
#  USER & SESSION
# ═══════════════════════════════════════════════════════════════════════════════


def set_user(username: str) -> None:
    """Set current user."""
    local.session.user = username
    local.session.sid = username
    local.cache = {}
    local.form_dict = _dict()
    local.jenv = None
    local.session.data = _dict()
    local.role_permissions = {}
    local.new_doc_templates = {}
    local.user_perms = None


def get_user():
    """Get current user's permission object."""
    from frappe.utils.user import UserPermissions

    if not local.user_perms:
        local.user_perms = UserPermissions(local.session.user)
    return local.user_perms


def get_roles(username=None) -> list[str]:
    """Return roles of current user."""
    if not local.session or not local.session.user:
        return ["Guest"]
    import frappe.permissions

    return frappe.permissions.get_roles(username or local.session.user)


def get_request_header(key, default=None):
    """Return HTTP request header."""
    return request.headers.get(key, default)


# ═══════════════════════════════════════════════════════════════════════════════
#  WHITELIST / API DECORATORS
# ═══════════════════════════════════════════════════════════════════════════════


whitelisted: set[Callable] = set()
guest_methods: set[Callable] = set()
xss_safe_methods: set[Callable] = set()
allowed_http_methods_for_whitelisted_func: dict[Callable, list[str]] = {}


def _in_request_or_test():
    return getattr(local, "request", None) or in_test


def whitelist(allow_guest=False, xss_safe=False, methods=None, force_types=None):
    """Decorator for whitelisting a function and making it accessible via HTTP."""
    if not methods:
        methods = ["GET", "POST", "PUT", "DELETE"]

    def innerfn(fn):
        global whitelisted, guest_methods, xss_safe_methods, allowed_http_methods_for_whitelisted_func

        whitelisted.add(fn)
        allowed_http_methods_for_whitelisted_func[fn] = methods

        if allow_guest:
            guest_methods.add(fn)
            if xss_safe:
                xss_safe_methods.add(fn)

        return fn

    return innerfn


def is_whitelisted(method):
    """Check if a method is whitelisted for HTTP access."""
    from frappe.utils.data import bold

    is_guest = session["user"] == "Guest"
    if method not in whitelisted or (is_guest and method not in guest_methods):
        summary = _("You are not permitted to access this resource. Login to access")
        detail = _("Function {0} is not whitelisted.").format(
            bold(f"{method.__module__}.{method.__name__}")
        )
        msg = f"<details><summary>{summary}</summary>{detail}</details>"
        throw(msg, PermissionError, title=_("Method Not Allowed"))

    if is_guest and method not in xss_safe_methods:
        from frappe.utils.data import sanitize_html

        for key, value in form_dict.items():
            if isinstance(value, str):
                form_dict[key] = sanitize_html(value)


# ═══════════════════════════════════════════════════════════════════════════════
#  PERMISSIONS
# ═══════════════════════════════════════════════════════════════════════════════


def only_for(roles: list[str] | tuple[str] | str, message=False):
    """Raises `frappe.PermissionError` if user does not have any of the permitted roles."""
    if local.session.user == "Administrator":
        return

    if isinstance(roles, str):
        roles = (roles,)

    if set(roles).isdisjoint(get_roles()):
        if not message:
            raise PermissionError
        throw(
            _("This action is only allowed for {}").format(
                ", ".join(bold(_(role)) for role in roles),
            ),
            PermissionError,
            _("Not Permitted"),
        )


def has_permission(
    doctype=None,
    ptype="read",
    doc=None,
    user=None,
    throw=False,
    *,
    parent_doctype=None,
    debug=False,
    ignore_share_permissions=False,
):
    """Return True if user has permission `ptype` for given `doctype` or `doc`."""
    import frappe.permissions

    if not doctype and doc:
        doctype = doc.doctype if hasattr(doc, "doctype") else str(doc)

    out = frappe.permissions.has_permission(
        doctype,
        ptype,
        doc=doc,
        user=user,
        verbose=throw,
        parent_doctype=parent_doctype,
    )

    if throw and not out:
        document_label = f"{_(doctype)} {doc if isinstance(doc, str) else getattr(doc, 'name', doc)}" if doc else _(doctype)
        frappe.flags.error_message = _("No permission for {0}").format(document_label)
        raise PermissionError

    return out


def only_has_select_perm(doctype, user=None, ignore_permissions=False):
    if ignore_permissions:
        return False

    from frappe.permissions import get_role_permissions

    user = user or local.session.user
    permissions = get_role_permissions(doctype, user=user)

    return permissions.get("select") and not permissions.get("read")


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCUMENT OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════


def get_doc(*args, **kwargs) -> "Document":
    """Return a Document object."""
    from frappe.model.document import get_doc as _get_doc

    return _get_doc(*args, **kwargs)


def get_cached_doc(*args, **kwargs) -> "Document":
    """Get a document from cache or database."""
    from frappe.model.document import get_cached_doc as _get_cached_doc

    return _get_cached_doc(*args, **kwargs)


def new_doc(doctype: str, parent_doc=None, parentfield=None, **kwargs) -> "Document":
    """Return a new Document."""
    from frappe.model.document import new_doc as _new_doc

    return _new_doc(doctype, parent_doc=parent_doc, parentfield=parentfield, **kwargs)


def get_single(doctype: str) -> "Document":
    """Get a Single DocType document."""
    from frappe.model.document import get_single as _get_single

    return _get_single(doctype)


def get_single_value(doctype: str, fieldname: str) -> Any:
    """Get a single value from a Single DocType."""
    from frappe.model.document import get_single_value as _get_single_value

    return _get_single_value(doctype, fieldname)


def get_last_doc(doctype: str, **kwargs) -> "Document":
    """Get the last created document."""
    from frappe.model.document import get_last_doc as _get_last_doc

    return _get_last_doc(doctype, **kwargs)


def get_cached_value(doctype, name, fieldname="name", as_dict=False) -> Any:
    """Get a cached value from a document."""
    from frappe.model.document import get_cached_value as _get_cached_value

    return _get_cached_value(doctype, name, fieldname=fieldname, as_dict=as_dict)


def get_meta(doctype: str, cached=True) -> "Document":
    """Get DocType metadata."""
    from frappe.model.meta import get_meta

    return get_meta(doctype, cached=cached)


def delete_doc(
    doctype: str | None = None,
    name=None,
    force: bool = False,
    ignore_doctypes=None,
    for_reload: bool = False,
    ignore_permissions: bool = False,
    flags=None,
    ignore_on_trash: bool = False,
    ignore_missing: bool = True,
    delete_permanently: bool = False,
):
    """Delete a document."""
    from frappe.model.delete_doc import delete_doc as _delete_doc

    return _delete_doc(
        doctype, name, force, ignore_doctypes, for_reload,
        ignore_permissions, flags, ignore_on_trash, ignore_missing, delete_permanently,
    )


def rename_doc(doctype, old, new, force=False, merge=False, *,
               ignore_if_exists=False, show_alert=True, rebuild_search=True) -> str:
    """Rename a doc and update all linked fields."""
    from frappe.model.rename_doc import rename_doc as _rename_doc

    return _rename_doc(
        doctype=doctype, old=old, new=new, force=force, merge=merge,
        ignore_if_exists=ignore_if_exists, show_alert=show_alert,
        rebuild_search=rebuild_search,
    )


def get_list(doctype, *args, **kwargs):
    """List database query with permission check."""
    from frappe.model.db_query import DatabaseQuery

    return DatabaseQuery(doctype).execute(*args, **kwargs)


def get_all(doctype, *args, **kwargs):
    """List database query without permission check."""
    kwargs["ignore_permissions"] = True
    if "limit_page_length" not in kwargs:
        kwargs["limit_page_length"] = 0
    return get_list(doctype, *args, **kwargs)


def get_value(*args, **kwargs):
    """Return a document property. Alias for frappe.db.get_value."""
    return local.db.get_value(*args, **kwargs)


def set_value(doctype, docname, fieldname, value=None):
    """Set document value."""
    import frappe.client

    return frappe.client.set_value(doctype, docname, fieldname, value)


def get_precision(doctype: str, fieldname: str, currency=None, doc=None) -> int:
    """Get precision for a given field."""
    from frappe.model.meta import get_field_precision

    meta = get_meta(doctype)
    field = None
    if meta and hasattr(meta, "fields"):
        for f in meta.fields:
            if f.fieldname == fieldname:
                field = f
                break
    return get_field_precision(field, doc, currency)


def generate_hash(txt=None, length: int = 56) -> str:
    """Generate random hash."""
    import math
    import secrets

    return secrets.token_hex(math.ceil(length / 2))[:length]


def is_table(doctype: str) -> bool:
    """Return True if `istable` property is set."""
    try:
        tables = db.get_values("DocType", filters={"istable": 1}, order_by=None, pluck=True)
        return doctype in (tables or [])
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE & APP MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════


def get_module(modulename: str):
    """Return a module object."""
    return importlib.import_module(modulename)


def scrub(txt: str) -> str:
    """Sluggify: `Sales Order` → `sales_order`."""
    from frappe.utils.data import cstr

    return cstr(txt).replace(" ", "_").replace("-", "_").lower()


def unscrub(txt: str) -> str:
    """Titlify: `sales_order` → `Sales Order`."""
    return txt.replace("_", " ").replace("-", " ").title()


def get_module_path(module, *joins):
    """Get path of given module name."""
    from os.path import join

    app = get_module_app(module)
    return get_pymodule_path(app + "." + scrub(module), *joins)


def get_app_path(app_name, *joins):
    """Return path of given app."""
    return get_pymodule_path(app_name, *joins)


def get_site_path(*joins):
    """Return path of current site."""
    from os.path import join

    return join(local.site_path, *joins)


def get_pymodule_path(modulename, *joins):
    """Return path of given Python module name."""
    from os.path import abspath, dirname, join

    if "public" not in joins:
        joins = [scrub(part) for part in joins]

    return abspath(join(dirname(get_module(scrub(modulename)).__file__ or ""), *joins))


def get_module_list(app_name):
    """Get list of modules for given app."""
    return get_file_items(get_app_path(app_name, "modules.txt"))


def get_all_apps(with_internal_apps=True, sites_path=None):
    """Get list of all apps."""
    if not sites_path:
        sites_path = getattr(local, "sites_path", ".")

    apps = get_file_items(os.path.join(sites_path, "apps.txt"), raise_not_found=True)

    if with_internal_apps:
        for app in get_file_items(os.path.join(getattr(local, "site_path", ""), "apps.txt")):
            if app not in apps:
                apps.append(app)

    if "frappe" in apps:
        apps.remove("frappe")
    apps.insert(0, "frappe")

    return apps


def get_installed_apps(*, _ensure_on_bench: bool = False) -> list[str]:
    """Get list of installed apps."""
    if getattr(flags, "in_install_db", True):
        return []

    if not db:
        connect()

    installed_str = db.get_global("installed_apps")
    installed = json.loads(installed_str) if installed_str else []
    return installed


def get_module_app(module):
    """Get the app that owns a module."""
    module_app = getattr(local, "module_app", {})
    return module_app.get(scrub(module), "frappe")


def setup_module_map(include_all_apps: bool = True) -> None:
    """Rebuild map of all modules."""
    try:
        if include_all_apps:
            apps = get_all_apps(with_internal_apps=True)
        else:
            apps = get_installed_apps(_ensure_on_bench=True)
    except Exception:
        apps = ["frappe"]

    app_modules = {}
    for app in apps:
        app_modules.setdefault(app, [])
        try:
            for mod in get_module_list(app):
                app_modules[app].append(scrub(mod))
        except Exception:
            pass

    module_app = {}
    for app, modules in app_modules.items():
        for module in modules:
            module_app[module] = app

    local.app_modules = app_modules
    local.module_app = module_app


# ═══════════════════════════════════════════════════════════════════════════════
#  HOOKS
# ═══════════════════════════════════════════════════════════════════════════════


def _load_app_hooks(app_name=None):
    """Load hooks from all installed apps."""
    import types

    hooks = {}
    try:
        apps = [app_name] if app_name else get_installed_apps(_ensure_on_bench=True)
    except Exception:
        apps = []

    for app in apps:
        try:
            app_hooks = get_module(f"{app}.hooks")
        except ImportError:
            continue

        for key, value in inspect.getmembers(
            app_hooks,
            lambda x: not isinstance(x, (types.ModuleType, types.FunctionType, type)),
        ):
            if not key.startswith("_"):
                append_hook(hooks, key, value)

    return hooks


def get_hooks(hook=None, default=None, app_name=None):
    """Get hooks via `app/hooks.py`."""
    if default is None:
        default = []

    hooks = _load_app_hooks(app_name)

    if hook:
        return hooks.get(hook, default)

    return _dict(hooks)


def get_doc_hooks():
    """Return hooked methods for given doc."""
    if not getattr(local, "doc_events_hooks", None):
        hooks = get_hooks("doc_events", {})
        out = {}
        for key, value in hooks.items():
            if isinstance(key, tuple):
                for doctype in key:
                    append_hook(out, doctype, value)
            else:
                append_hook(out, key, value)
        local.doc_events_hooks = out

    return local.doc_events_hooks


def append_hook(target, key, value):
    """Append a hook to target dict."""
    if isinstance(value, dict):
        target.setdefault(key, {})
        for inkey in value:
            append_hook(target[key], inkey, value[inkey])
    else:
        target.setdefault(key, [])
        if not isinstance(value, list):
            value = [value]
        target[key].extend(value)


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════


def get_file_items(path, raise_not_found=False, ignore_empty_lines=True):
    """Return items from text file as a list."""
    content = read_file(path, raise_not_found=raise_not_found)
    if content:
        return [
            p.strip()
            for p in content.splitlines()
            if (not ignore_empty_lines) or (p.strip() and not p.startswith("#"))
        ]
    return []


def get_file_json(path):
    """Read a file and return parsed JSON."""
    with open(path) as f:
        return json.load(f)


def read_file(path, raise_not_found=False, as_base64=False):
    """Open a file and return content."""
    if isinstance(path, str):
        path = path.encode("utf-8")

    if os.path.exists(path):
        if as_base64:
            import base64

            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        else:
            with open(path) as f:
                return f.read()
    elif raise_not_found:
        raise OSError(f"{path} Not Found")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  REFLECTION & DYNAMIC CALLING
# ═══════════════════════════════════════════════════════════════════════════════


def get_attr(method_string: str) -> Any:
    """Get python method object from its name."""
    app_name = method_string.split(".", 1)[0]
    try:
        if (
            not local.flags.in_uninstall
            and not local.flags.in_install
            and app_name not in get_installed_apps()
        ):
            throw(_("App {0} is not installed").format(app_name), AppNotInstalledError)
    except Exception:
        pass

    modulename = ".".join(method_string.split(".")[:-1])
    methodname = method_string.split(".")[-1]
    return getattr(get_module(modulename), methodname)


def call(fn, *args, **kwargs):
    """Call a function and match arguments."""
    if isinstance(fn, str):
        fn = get_attr(fn)

    newargs = get_newargs(fn, kwargs)
    return fn(*args, **newargs)


@functools.lru_cache(maxsize=1024)
def _get_cached_signature_params(fn):
    """Get cached parameters for a function."""
    signature = inspect.signature(fn)
    variable_kwargs_exist = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    return dict(signature.parameters), variable_kwargs_exist


def get_newargs(fn, kwargs):
    """Remove kwargs not supported by the function."""
    parameters, variable_kwargs_exist = _get_cached_signature_params(fn)
    newargs = (
        kwargs.copy()
        if variable_kwargs_exist
        else {key: value for key, value in kwargs.items() if key in parameters}
    )
    newargs.pop("ignore_permissions", None)
    newargs.pop("flags", None)
    return newargs


# ═══════════════════════════════════════════════════════════════════════════════
#  MISC UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════


def as_json(obj, indent=1, separators=None, ensure_ascii=True) -> str:
    """Return JSON string representation."""
    if separators is None:
        separators = (",", ": ")

    try:
        return json.dumps(obj, indent=indent, sort_keys=True, default=str,
                         separators=separators, ensure_ascii=ensure_ascii)
    except TypeError:
        sorted_obj = dict(sorted(obj.items(), key=lambda kv: str(kv[0])))
        return json.dumps(sorted_obj, indent=indent, default=str,
                         separators=separators, ensure_ascii=ensure_ascii)


def are_emails_muted():
    return flags.mute_emails or cint(conf.get("mute_emails", 0))


def task(**task_kwargs):
    """Decorator to mark a function as a background task."""
    def decorator_task(f):
        f.enqueue = lambda **fun_kwargs: enqueue(f, **task_kwargs, **fun_kwargs)
        return f

    return decorator_task


def get_doctype_app(doctype):
    """Get the app that owns a DocType."""
    try:
        doctype_module = local.db.get_value("DocType", doctype, "module")
        module_app = getattr(local, "module_app", {})
        return module_app.get(scrub(doctype_module), "frappe")
    except Exception:
        return "frappe"


def logger(module=None, with_more_info=False, allow_site=True, filter=None,
           max_size=100_000, file_count=20):
    """Return a python logger."""
    import logging

    name = module or "frappe"
    if name not in frappe.cache_manager._cache_store:
        log = logging.getLogger(name)
        log.setLevel(logging.DEBUG)
        if not log.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(logging.DEBUG)
            log.addHandler(handler)
        frappe.cache_manager._cache_store[name] = (log, None)

    return frappe.cache_manager._cache_store[name][0]


def build_match_conditions(doctype, as_condition=True):
    """Return match conditions for user permissions."""
    return "" if as_condition else []


def respond_as_web_page(title, html, success=None, http_status_code=None,
                        context=None, indicator_color=None,
                        primary_action="/", primary_label=None,
                        fullpage=False, width=None, template="message"):
    """Send response as a web page."""
    local.message_title = title
    local.message = html
    local.response["type"] = "page"
    local.response["route"] = template
    local.no_cache = 1

    if http_status_code:
        local.response["http_status_code"] = http_status_code

    if not context:
        context = {}

    if not indicator_color:
        if success:
            indicator_color = "green"
        elif http_status_code and http_status_code > 300:
            indicator_color = "red"
        else:
            indicator_color = "blue"

    context["indicator_color"] = indicator_color
    context["primary_label"] = primary_label
    context["primary_action"] = primary_action
    context["error_code"] = http_status_code
    context["fullpage"] = fullpage
    if width:
        context["card_width"] = width

    local.response["context"] = context


def redirect(url):
    """Raise a redirect."""
    flags.redirect_location = url
    raise Redirect


def redirect_to_message(title, html, http_status_code=None, context=None, indicator_color=None):
    """Redirect to a message page."""
    message_id = generate_hash(length=8)
    message = {"context": context or {}, "http_status_code": http_status_code or 200}
    message["context"].update({"header": title, "title": title, "message": html})

    if indicator_color:
        message["context"]["indicator_color"] = indicator_color

    cache_key = f"message:{message_id}"
    frappe.cache_manager.set_value(cache_key, message, expires_in_sec=60)

    location = f"/message?id={message_id}"

    if not getattr(local, "is_ajax", False):
        local.response["type"] = "redirect"
        local.response["location"] = location
    else:
        return location


def get_website_settings(key):
    """Get website setting."""
    try:
        ws = get_cached_doc("Website Settings", "Website Settings")
        return ws.get(key)
    except Exception:
        return None


def get_active_domains():
    """Get active domains."""
    return []


def is_setup_complete():
    """Check if setup is complete."""
    try:
        if not db or not db.table_exists("Installed Application"):
            return False
        results = get_all("Installed Application",
                         {"app_name": ("in", ["frappe", "erpnext"])},
                         pluck="is_setup_complete")
        return bool(results and all(results))
    except Exception:
        return False


@whitelist(allow_guest=True)
def ping():
    return "pong"


def validate_and_sanitize_search_inputs(fn):
    """Decorator to validate search inputs."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        kwargs.update(dict(zip(fn.__code__.co_varnames, args, strict=False)))
        kwargs["start"] = cint(kwargs.get("start", 0))
        kwargs["page_len"] = cint(kwargs.get("page_len", 20))

        if kwargs.get("doctype") and not db.exists("DocType", kwargs["doctype"]):
            return []

        return fn(**kwargs)

    return wrapper


def override_whitelisted_method(original_method: str) -> str:
    """Return override or original whitelisted method."""
    overrides = get_hooks("override_whitelisted_methods", {}).get(original_method, [])
    return overrides[-1] if overrides else original_method


def reload_doctype(doctype, force=False, reset_permissions=False):
    """Reload DocType from JSON files."""
    reload_doc(
        scrub(db.get_value("DocType", doctype, "module")),
        "doctype",
        scrub(doctype),
        force=force,
        reset_permissions=reset_permissions,
    )


def reload_doc(module, dt=None, dn=None, force=False, reset_permissions=False):
    """Reload Document from model JSON files."""
    from frappe.modules import reload_doc

    return reload_doc(module, dt, dn, force=force, reset_permissions=reset_permissions)


def get_meta_module(doctype):
    import frappe.modules

    return frappe.modules.load_doctype_module(doctype)


def make_property_setter(args, ignore_validate=False, validate_fields_for_doctype=True,
                         is_system_generated=True, *, module=None):
    """Create a Property Setter."""
    args = _dict(args)
    if not args.doctype_or_field:
        args.doctype_or_field = "DocField"

    if not args.doctype:
        doctype_list = db.get_values(
            "DocField",
            filters={"fieldname": args.fieldname},
            fieldname="parent",
            distinct=True,
            pluck=True,
        ) or []
    else:
        doctype_list = [args.doctype]

    for doctype in doctype_list:
        ps = get_doc({
            "doctype": "Property Setter",
            "doctype_or_field": args.doctype_or_field,
            "doc_type": doctype,
            "module": module,
            "field_name": args.fieldname,
            "row_name": args.row_name,
            "property": args.property,
            "value": args.value,
            "property_type": args.property_type or "Data",
            "is_system_generated": is_system_generated,
            "__islocal": 1,
        })
        ps.flags.ignore_validate = ignore_validate
        ps.flags.validate_fields_for_doctype = validate_fields_for_doctype
        ps.insert()


def clear_document_cache(doctype, name=None):
    """Clear cached document."""
    from frappe.model.document import clear_document_cache as _clear

    _clear(doctype, name)


# ═══════════════════════════════════════════════════════════════════════════════
#  I18N
# ═══════════════════════════════════════════════════════════════════════════════


def _(message, lang=None, context=None):
    """Translate a message."""
    return message


def _lt(message, lang=None, context=None):
    """Lazy translate."""
    return _(message, lang, context)


# ═══════════════════════════════════════════════════════════════════════════════
#  IMPORTS FROM SUBMODULES
# ═══════════════════════════════════════════════════════════════════════════════

from frappe.utils.data import (
    cint, cstr, flt, sbool,
    now, nowdate, nowtime, today,
    add_days, add_months, date_diff, getdate, get_datetime,
    formatdate, format_date, format_time, format_datetime,
    get_url, get_host_name, get_link_to_form,
    sanitize_html, strip_html,
    encode, parse_json, as_unicode,
    bold, safe_encode, safe_decode,
    to_markdown, get_datetime_str, get_date_str, get_time_str,
    unique, strip, comma_sep, comma_and, new_line_sep,
    money_in_words, to_csv,
)

from frappe.utils.user import UserPermissions

from frappe.model.document import (
    copy_doc,
    get_document_cache_key,
    can_cache_doc,
    _set_document_in_cache,
)

from frappe.cache_manager import clear_cache, reset_metadata_version

from frappe.utils.background_jobs import enqueue, enqueue_doc

from frappe.utils.error import log_error

from frappe.realtime import publish_progress, publish_realtime


def render_template(template_name_or_string: str, context: dict | None = None, is_path: bool = True) -> str:
    """Render a Jinja2 template.

    Args:
        template_name_or_string: Template file path or raw template string.
        context: Template context dictionary.
        is_path: When True, treat *template_name_or_string* as a file path;
                 when False, treat it as a raw template string.

    Returns:
        Rendered HTML string.
    """
    from frappe.website.serve import render_template as _render_template, render_string as _render_string

    if is_path:
        return _render_template(template_name_or_string, context or {})
    return _render_string(template_name_or_string, context or {})


# ═══════════════════════════════════════════════════════════════════════════════
#  LAZY SUBMODULE LOADING — prevents circular imports
# ═══════════════════════════════════════════════════════════════════════════════

_LAZY_SUBMODULES = {
    "permissions": "frappe.permissions",
    "auth": "frappe.auth",
    "client": "frappe.client",
    "boot": "frappe.boot",
    "defaults": "frappe.defaults",
    "cache": "frappe.cache_manager",
    "cache_manager": "frappe.cache_manager",
    "realtime": "frappe.realtime",
    "sessions": "frappe.sessions",
    "search": "frappe.search",
    "translation": "frappe.translation",
    "file_manager": "frappe.file_manager",
    "modules": "frappe.modules",
    "website": "frappe.website.serve",
    "desk": "frappe.desk.form",
    "installer": "frappe.installer",
    "integrations": "frappe.integrations",
    "geo": "frappe.geo",
    "workflow": "frappe.workflow",
    "data_import": "frappe.data_import",
    "email": "frappe.email",
    "printing": "frappe.printing",
    "rate_limiter": "frappe.rate_limiter",
    "api": "frappe.api",
    "handler": "frappe.handler",
    "app": "frappe.app",
}

def __getattr__(name: str):
    """Lazy-load submodules to prevent circular imports."""
    if name in _LAZY_SUBMODULES:
        import importlib
        module = importlib.import_module(_LAZY_SUBMODULES[name])
        # Cache it on the module
        import sys
        sys.modules[__name__].__dict__[name] = module
        return module
    raise AttributeError(f"module 'frappe' has no attribute '{name}'")
