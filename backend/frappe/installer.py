from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Optional

import frappe
from frappe.types import _dict


def install_db(
    root_login: Optional[str] = None,
    root_password: Optional[str] = None,
    db_name: Optional[str] = None,
    site_config: Optional[dict] = None,
    admin_password: Optional[str] = None,
    verbose: bool = False,
) -> None:
    """Create a new site database.

    For SQLite: creates the .db file, sets up the core schema including
    the tabDocType, tabDocField, tabSingles, and other meta-tables.

    Args:
        root_login: Root database login (unused for SQLite).
        root_password: Root database password (unused for SQLite).
        db_name: Name of the database / site.
        site_config: Optional site configuration overrides.
        admin_password: Password for the Administrator user.
        verbose: Print verbose progress output.
    """
    db_name = db_name or frappe.local.site
    db_path = _get_db_path(db_name)

    if verbose:
        print(f"Creating database at {db_path}")

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create fresh SQLite database with core schema
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Enable WAL mode for better concurrency
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")

    _create_core_schema(cursor)

    conn.commit()
    conn.close()

    if verbose:
        print(f"Database created: {db_path}")


def _get_db_path(db_name: str) -> Path:
    """Resolve the filesystem path for a SQLite database."""
    sites_path = Path(frappe.local.sites_path)
    site_path = sites_path / db_name
    return site_path / f"{db_name}.db"


def _create_core_schema(cursor: sqlite3.Cursor) -> None:
    """Create the core Frappe schema tables in SQLite.

    This creates the minimal table structure needed for DocType-based
    ORM operation: meta-tables for DocTypes, DocFields, and Singles.
    """
    # DocType table - stores document type definitions
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabDocType" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            idx INTEGER DEFAULT 0,
            module TEXT,
            custom INTEGER DEFAULT 0,
            autoname TEXT,
            name_case TEXT,
            naming_rule TEXT,
            editable_grid INTEGER DEFAULT 1,
            track_changes INTEGER DEFAULT 1,
            track_seen INTEGER DEFAULT 0,
            track_views INTEGER DEFAULT 0,
            quick_entry INTEGER DEFAULT 0,
            sort_field TEXT,
            sort_order TEXT,
            read_only INTEGER DEFAULT 0,
            in_create INTEGER DEFAULT 0,
            __islocal INTEGER DEFAULT 0,
            __unsaved INTEGER DEFAULT 0,
            __owned INTEGER DEFAULT 0,
            is_virtual INTEGER DEFAULT 0,
            engine TEXT DEFAULT 'InnoDB',
            _user_tags TEXT,
            _comments TEXT,
            _assign TEXT,
            _liked_by TEXT
        )
        """
    )

    # DocField table - stores field definitions for each DocType
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabDocField" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            idx INTEGER DEFAULT 0,
            parent TEXT,
            parentfield TEXT,
            parenttype TEXT,
            fieldname TEXT,
            label TEXT,
            fieldtype TEXT,
            options TEXT,
            search_index INTEGER DEFAULT 0,
            hidden INTEGER DEFAULT 0,
            set_only_once INTEGER DEFAULT 0,
            allow_in_quick_entry INTEGER DEFAULT 0,
            print_hide INTEGER DEFAULT 0,
            report_hide INTEGER DEFAULT 0,
            reqd INTEGER DEFAULT 0,
            bold INTEGER DEFAULT 0,
            in_global_search INTEGER DEFAULT 0,
            collapsible INTEGER DEFAULT 0,
            unique_idx INTEGER DEFAULT 0,
            no_copy INTEGER DEFAULT 0,
            allow_on_submit INTEGER DEFAULT 0,
            show_on_timeline INTEGER DEFAULT 0,
            ignore_xss_filter INTEGER DEFAULT 0,
            translatable INTEGER DEFAULT 0,
            fetch_from TEXT,
            fetch_if_empty INTEGER DEFAULT 0,
            depends_on TEXT,
            mandatory_depends_on TEXT,
            read_only_depends_on TEXT,
            default_value TEXT,
            description TEXT,
            permlevel INTEGER DEFAULT 0,
            width TEXT,
            columns INTEGER DEFAULT 0,
            oldfieldname TEXT,
            oldfieldtype TEXT
        )
        """
    )

    # Singles table - stores single-record DocType values
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabSingles" (
            doctype TEXT NOT NULL,
            field TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (doctype, field)
        )
        """
    )

    # DocPerm table - stores permission rules
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabDocPerm" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            idx INTEGER DEFAULT 0,
            parent TEXT,
            parentfield TEXT,
            parenttype TEXT,
            role TEXT,
            permlevel INTEGER DEFAULT 0,
            read INTEGER DEFAULT 1,
            write INTEGER DEFAULT 1,
            create INTEGER DEFAULT 1,
            submit INTEGER DEFAULT 0,
            cancel INTEGER DEFAULT 0,
            delete INTEGER DEFAULT 1,
            amend INTEGER DEFAULT 0,
            report INTEGER DEFAULT 1,
            export INTEGER DEFAULT 1,
            import_perm INTEGER DEFAULT 0,
            share INTEGER DEFAULT 1,
            print_perm INTEGER DEFAULT 1,
            email_perm INTEGER DEFAULT 1,
            if_owner INTEGER DEFAULT 0,
            select_perm INTEGER DEFAULT 0
        )
        """
    )

    # Module Def table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabModule Def" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            app_name TEXT,
            custom INTEGER DEFAULT 0
        )
        """
    )

    # Patch Log table - tracks applied patches
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabPatch Log" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            patch TEXT
        )
        """
    )

    # DefaultValue table - user/session defaults
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabDefaultValue" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            parent TEXT,
            parenttype TEXT,
            parentfield TEXT,
            defkey TEXT,
            defvalue TEXT
        )
        """
    )

    # Has Role table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabHas Role" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            parent TEXT,
            parenttype TEXT,
            parentfield TEXT,
            role TEXT,
            parentfield_idx INTEGER DEFAULT 0
        )
        """
    )

    # Role table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabRole" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            idx INTEGER DEFAULT 0,
            desk_access INTEGER DEFAULT 1,
            two_factor_auth INTEGER DEFAULT 0,
            restrictions JSON,
            home_page TEXT,
            role_name TEXT
        )
        """
    )

    # User table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabUser" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            idx INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            email TEXT,
            first_name TEXT,
            middle_name TEXT,
            last_name TEXT,
            full_name TEXT,
            username TEXT,
            language TEXT,
            time_zone TEXT,
            send_welcome_email INTEGER DEFAULT 0,
            unread_count INTEGER DEFAULT 0,
            simultaneous_sessions INTEGER DEFAULT 0,
            user_type TEXT DEFAULT 'System User',
            last_password_reset_date DATE,
            last_active DATE,
            login_after INTEGER DEFAULT 0,
            login_before INTEGER DEFAULT 0,
            restrict_ip TEXT,
            bypass_restrict_ip_check IF NOT EXISTS INTEGER DEFAULT 0,
            birth_date DATE,
            location TEXT,
            interest TEXT,
            bio TEXT,
            banner_image TEXT,
            mobile_no TEXT,
            mute_sounds INTEGER DEFAULT 0,
            new_password TEXT,
            logout_all_sessions INTEGER DEFAULT 0,
            reset_password_key TEXT,
            last_qrcode_login DATE,
            document_follow_notify INTEGER DEFAULT 0,
            document_follow_frequency TEXT,
            follow_created_documents INTEGER DEFAULT 0,
            follow_commented_documents INTEGER DEFAULT 0,
            follow_liked_documents INTEGER DEFAULT 0,
            follow_assigned_documents INTEGER DEFAULT 0,
            follow_shared_documents INTEGER DEFAULT 0,
            thread_notify INTEGER DEFAULT 1,
            send_me_a_copy INTEGER DEFAULT 0,
            allowed_in_mentions INTEGER DEFAULT 1,
            await_password_auth INTEGER DEFAULT 0,
            home_settings TEXT,
            onboarding_status TEXT,
            _user_tags TEXT,
            _comments TEXT,
            _assign TEXT,
            _liked_by TEXT
        )
        """
    )

    # Version table - document version history
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabVersion" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            ref_doctype TEXT,
            docname TEXT,
            data TEXT
        )
        """
    )

    # Activity Log table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabActivity Log" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            user TEXT,
            operation TEXT,
            status TEXT,
            subject TEXT,
            communication_date TIMESTAMP,
            content TEXT,
            ip_address TEXT,
            reference_doctype TEXT,
            reference_name TEXT,
            reference_owner TEXT,
            timeline_doctype TEXT,
            timeline_name TEXT,
            link_doctype TEXT,
            link_name TEXT,
            reference_user TEXT
        )
        """
    )

    # Deleted Document table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabDeleted Document" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            deleted_doctype TEXT,
            deleted_name TEXT,
            data TEXT,
            restored INTEGER DEFAULT 0
        )
        """
    )

    # Error Log table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabError Log" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            method TEXT,
            error TEXT,
            traceback TEXT,
            reference_doctype TEXT,
            reference_docname TEXT,
            seen INTEGER DEFAULT 0
        )
        """
    )

    # Scheduled Job Type table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabScheduled Job Type" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            stopped INTEGER DEFAULT 0,
            method TEXT,
            frequency TEXT,
            cron_format TEXT,
            create_log INTEGER DEFAULT 1,
            last_execution DATE,
            next_execution DATE,
            dont_overlap INTEGER DEFAULT 1,
            times_log_is_kept INTEGER DEFAULT 90,
            timeout INTEGER DEFAULT 0
        )
        """
    )

    # Scheduled Job Log table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS "tabScheduled Job Log" (
            name TEXT PRIMARY KEY,
            creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            owner TEXT,
            docstatus INTEGER DEFAULT 0,
            scheduled_job_type TEXT,
            status TEXT,
            details TEXT,
            traceback TEXT
        )
        """
    )

    # Create indexes for common lookups
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_docfield_parent ON tabDocField(parent)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_docperm_parent ON tabDocPerm(parent)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_singles_dt ON tabSingles(doctype)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_version_ref ON tabVersion(ref_doctype, docname)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_log_user ON tabActivity Log(user)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_log_seen ON tabError Log(seen)"
    )


def install_app(
    name: str,
    verbose: bool = False,
    set_as_patched: bool = True,
    force: bool = False,
) -> None:
    """Install an app into the current site.

    Loads app hooks, creates DocTypes from the app's doctype JSON files,
    runs before_install / after_install hooks, and adds the app to
    ``installed_apps``.

    Args:
        name: The app name (e.g. ``"frappe"``, ``"erpnext"``).
        verbose: Print verbose progress output.
        set_as_patched: Mark all app patches as already applied.
        force: Re-install even if the app is already present.
    """
    if name in get_installed_apps() and not force:
        if verbose:
            print(f"App '{name}' already installed.")
        return

    if verbose:
        print(f"Installing app '{name}'...")

    # Load app hooks module
    try:
        hooks = frappe.get_hooks(app_name=name)
    except ImportError:
        hooks = _dict()

    # Run before_install hook
    before_install = hooks.get("before_install")
    if before_install:
        for hook in before_install if isinstance(before_install, list) else [before_install]:
            frappe.get_attr(hook)()

    # Create DocTypes from JSON files
    doctypes = _get_app_doctypes(name)
    if verbose:
        print(f"  Creating {len(doctypes)} DocTypes...")

    for dt_data in doctypes:
        _create_doctype_from_json(dt_data, verbose=verbose)

    # Run after_install hook
    after_install = hooks.get("after_install")
    if after_install:
        for hook in after_install if isinstance(after_install, list) else [after_install]:
            frappe.get_attr(hook)()

    # Add to installed_apps
    add_to_installed_apps(name, set_as_patched=set_as_patched)

    # Commit all changes
    frappe.db.commit()

    if verbose:
        print(f"App '{name}' installed successfully.")


def _create_doctype_from_json(dt_data: dict, verbose: bool = False) -> None:
    """Create a DocType from its JSON definition.

    Inserts the DocType record and all its field / permission records.
    Also creates the underlying data table if it is not a Single.
    """
    import frappe

    fields = dt_data.pop("fields", [])
    permissions = dt_data.pop("permissions", [])

    # Insert DocType record
    dt_doc = frappe.get_doc({"doctype": "DocType", **dt_data})
    dt_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

    # Insert field records
    for idx, field in enumerate(fields, start=1):
        field["doctype"] = "DocField"
        field["parent"] = dt_data.get("name")
        field["parentfield"] = "fields"
        field["parenttype"] = "DocType"
        field["idx"] = idx
        field_doc = frappe.get_doc(field)
        field_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

    # Insert permission records
    for idx, perm in enumerate(permissions, start=1):
        perm["doctype"] = "DocPerm"
        perm["parent"] = dt_data.get("name")
        perm["parentfield"] = "permissions"
        perm["parenttype"] = "DocType"
        perm["idx"] = idx
        perm_doc = frappe.get_doc(perm)
        perm_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

    # Create the underlying data table (not for Single / Virtual)
    if dt_data.get("issingle") or dt_data.get("is_virtual"):
        return

    _create_data_table(dt_data.get("name"), fields, verbose=verbose)


def _create_data_table(
    doctype_name: str, fields: list[dict], verbose: bool = False
) -> None:
    """Create the SQLite data table for a DocType."""
    table_name = f"tab{doctype_name}"

    # Build column definitions
    col_defs = [
        "name TEXT PRIMARY KEY",
        "creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "modified_by TEXT",
        "owner TEXT",
        "docstatus INTEGER DEFAULT 0",
        "idx INTEGER DEFAULT 0",
        "_user_tags TEXT",
        "_comments TEXT",
        "_assign TEXT",
        "_liked_by TEXT",
    ]

    sqlite_type_map = {
        "Data": "TEXT",
        "Text": "TEXT",
        "Long Text": "TEXT",
        "Small Text": "TEXT",
        "Text Editor": "TEXT",
        "Code": "TEXT",
        "Markdown Editor": "TEXT",
        "HTML Editor": "TEXT",
        "Int": "INTEGER",
        "Integer": "INTEGER",
        "Float": "REAL",
        "Currency": "REAL",
        "Percent": "REAL",
        "Check": "INTEGER DEFAULT 0",
        "Date": "DATE",
        "Datetime": "TIMESTAMP",
        "Time": "TEXT",
        "Link": "TEXT",
        "Dynamic Link": "TEXT",
        "Select": "TEXT",
        "Autocomplete": "TEXT",
        "Password": "TEXT",
        "Read Only": "TEXT",
        "Attach": "TEXT",
        "Attach Image": "TEXT",
        "Signature": "TEXT",
        "Color": "TEXT",
        "Barcode": "TEXT",
        "Geolocation": "TEXT",
        "Duration": "REAL",
        "JSON": "TEXT",
        "Rating": "INTEGER",
        "Phone": "TEXT",
        "Icon": "TEXT",
    }

    for field in fields:
        ft = field.get("fieldtype", "Data")
        fn = field.get("fieldname")
        if not fn:
            continue
        # Skip certain fieldtypes that don't need columns
        if ft in ("Section Break", "Column Break", "Tab Break", "Table", "Button", "HTML", "Fold"):
            continue
        col_type = sqlite_type_map.get(ft, "TEXT")
        col_defs.append(f'"{fn}" {col_type}')

    create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({', '.join(col_defs)})'

    try:
        frappe.db.sql(create_sql)
    except Exception:
        # Table may already exist
        pass


def add_to_installed_apps(
    app_name: str, set_as_patched: bool = True
) -> None:
    """Add an app to the ``installed_apps`` global list.

    Args:
        app_name: The app module name to add.
        set_as_patched: If True, mark all patches for this app as completed.
    """
    installed = get_installed_apps()
    if app_name not in installed:
        installed.append(app_name)
        frappe.db.set_global("installed_apps", json.dumps(installed))
        frappe.cache.delete_value("installed_apps")
        frappe.db.commit()

    if set_as_patched:
        set_all_patches_as_completed(app_name)


def remove_from_installed_apps(app_name: str) -> None:
    """Remove an app from the ``installed_apps`` global list.

    Args:
        app_name: The app module name to remove.
    """
    installed = get_installed_apps()
    if app_name in installed:
        installed.remove(app_name)
        frappe.db.set_global("installed_apps", json.dumps(installed))
        frappe.cache.delete_value("installed_apps")
        frappe.db.commit()


def get_installed_apps() -> list[str]:
    """Return the list of installed apps for the current site.

    Reads from the cached global value; falls back to the database.
    """
    apps = frappe.cache.get_value("installed_apps")
    if apps is None:
        raw = frappe.db.get_global("installed_apps")
        if raw:
            try:
                apps = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                apps = []
        else:
            apps = []
        frappe.cache.set_value("installed_apps", apps)
    return apps if isinstance(apps, list) else []


def make_site_dirs() -> None:
    """Create the full site directory structure.

    Creates::

        sites/{site}/
            private/
                backups/
                files/
                logs/
                templates/
            public/
                files/
            assets/
            locks/
    """
    site_path = Path(frappe.local.site_path)
    dirs = [
        site_path / "private" / "backups",
        site_path / "private" / "files",
        site_path / "private" / "logs",
        site_path / "private" / "templates",
        site_path / "public" / "files",
        site_path / "assets",
        site_path / "locks",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def update_site_config(
    key: str,
    value: Any,
    site_config_path: Optional[str] = None,
) -> None:
    """Update a single key in the site's ``site_config.json``.

    Args:
        key: The configuration key to update.
        value: The new value.
        site_config_path: Path to the config file (defaults to current site).
    """
    site_config_path = site_config_path or os.path.join(
        frappe.local.site_path, "site_config.json"
    )

    config: dict[str, Any] = {}
    if os.path.exists(site_config_path):
        with open(site_config_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                config = {}

    config[key] = value

    with open(site_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, sort_keys=True)


def get_site_config(
    site_path: Optional[str] = None,
    sites_path: Optional[str] = None,
) -> _dict:
    """Read ``site_config.json`` and return as an ``_dict``.

    Args:
        site_path: The site directory path.
        sites_path: The parent ``sites/`` directory path.

    Returns:
        An ``_dict`` of configuration key-value pairs.
    """
    from frappe.types import _dict

    sites_path = sites_path or frappe.local.sites_path
    site_path = site_path or frappe.local.site_path

    config: dict[str, Any] = {}

    # Read common_site_config.json first
    common_config_path = os.path.join(sites_path, "common_site_config.json")
    if os.path.exists(common_config_path):
        with open(common_config_path, "r", encoding="utf-8") as f:
            try:
                config.update(json.load(f))
            except json.JSONDecodeError:
                pass

    # Site-specific config overrides common
    site_config_path = os.path.join(site_path, "site_config.json")
    if os.path.exists(site_config_path):
        with open(site_config_path, "r", encoding="utf-8") as f:
            try:
                config.update(json.load(f))
            except json.JSONDecodeError:
                pass

    return _dict(config)


def make_conf(
    db_name: str,
    db_password: Optional[str] = None,
    db_type: str = "sqlite",
    db_host: str = "localhost",
    db_port: Optional[int] = None,
    db_user: Optional[str] = None,
    language: str = "en",
    country: Optional[str] = None,
    timezone: Optional[str] = None,
    admin_password: Optional[str] = None,
) -> dict[str, Any]:
    """Create a ``site_config.json`` content dictionary.

    Args:
        db_name: Database / site name.
        db_password: Database password (unused for SQLite).
        db_type: Database backend (``'sqlite'`` or ``'mariadb'``).
        db_host: Database host.
        db_port: Database port.
        db_user: Database user name.
        language: Default language code.
        country: Default country.
        timezone: Default timezone.
        admin_password: Administrator password.

    Returns:
        Dictionary suitable for writing to ``site_config.json``.
    """
    config: dict[str, Any] = {
        "db_name": db_name,
        "db_type": db_type,
        "db_host": db_host,
        "language": language,
    }

    if db_password:
        config["db_password"] = db_password
    if db_port:
        config["db_port"] = db_port
    if db_user:
        config["db_user"] = db_user
    if country:
        config["country"] = country
    if timezone:
        config["timezone"] = timezone
    if admin_password:
        config["admin_password"] = admin_password

    return config


def new_site(
    site_name: str,
    site_config: Optional[dict] = None,
    admin_password: Optional[str] = None,
    db_name: Optional[str] = None,
    db_type: str = "sqlite",
    db_host: Optional[str] = None,
    db_port: Optional[int] = None,
    db_user: Optional[str] = None,
    db_password: Optional[str] = None,
    verbose: bool = False,
    install_apps: Optional[list[str]] = None,
    source_sql: Optional[str] = None,
    force: bool = False,
) -> None:
    """Create a completely new site with database and directories.

    Steps:
        1. Create directories.
        2. Write ``site_config.json``.
        3. Initialize the database with core schema.
        4. Install the ``frappe`` app.
        5. Create the *Administrator* user.
        6. Install any additional apps.

    Args:
        site_name: Name of the new site.
        site_config: Extra config key-value pairs.
        admin_password: Password for the Administrator user.
        db_name: Database name (defaults to *site_name*).
        db_type: Database backend.
        db_host: Database host.
        db_port: Database port.
        db_user: Database user.
        db_password: Database password.
        verbose: Print progress.
        install_apps: Additional apps to install after frappe.
        source_sql: SQL file to restore from (instead of fresh schema).
        force: Overwrite existing site.
    """
    sites_path = frappe.local.sites_path
    site_path = os.path.join(sites_path, site_name)

    if os.path.exists(site_path) and not force:
        raise FileExistsError(f"Site '{site_name}' already exists. Use force=True to overwrite.")

    if force and os.path.exists(site_path):
        shutil.rmtree(site_path)

    if verbose:
        print(f"Creating new site: {site_name}")

    # 1. Create directories
    os.makedirs(site_path, exist_ok=True)
    frappe.local.site_path = site_path
    make_site_dirs()

    # 2. Create site_config.json
    db_name = db_name or site_name
    config = make_conf(
        db_name=db_name,
        db_password=db_password,
        db_type=db_type,
        db_host=db_host or "localhost",
        db_port=db_port,
        db_user=db_user,
        admin_password=admin_password,
    )
    if site_config:
        config.update(site_config)

    config_path = os.path.join(site_path, "site_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, sort_keys=True)

    # 3. Initialize database
    _new_site_db(
        site_name,
        site_config=config,
        db_name=db_name,
        db_type=db_type,
        verbose=verbose,
        source_sql=source_sql,
    )

    # 4. Install frappe app (core DocTypes)
    install_app("frappe", verbose=verbose, set_as_patched=True)

    # 5. Create Administrator user
    _create_admin_user(admin_password)

    # 6. Install additional apps
    if install_apps:
        for app in install_apps:
            if app != "frappe":
                install_app(app, verbose=verbose)

    if verbose:
        print(f"Site '{site_name}' created successfully.")


def drop_site(
    site_name: str,
    root_login: Optional[str] = None,
    root_password: Optional[str] = None,
    archived_sites_path: Optional[str] = None,
    force: bool = False,
    verbose: bool = False,
) -> None:
    """Delete a site and its database.

    Args:
        site_name: The site to drop.
        root_login: Unused (SQLite compatibility).
        root_password: Unused (SQLite compatibility).
        archived_sites_path: If set, move site here instead of deleting.
        force: Skip confirmation.
        verbose: Print progress.
    """
    sites_path = frappe.local.sites_path
    site_path = os.path.join(sites_path, site_name)

    if not os.path.exists(site_path):
        raise FileNotFoundError(f"Site '{site_name}' not found.")

    if verbose:
        print(f"Dropping site: {site_name}")

    # Delete the database file
    db_path = os.path.join(site_path, f"{site_name}.db")
    if os.path.exists(db_path):
        os.remove(db_path)
        if verbose:
            print(f"  Removed database: {db_path}")

    # Remove WAL files if present
    for wal in [f"{db_path}-wal", f"{db_path}-shm"]:
        if os.path.exists(wal):
            os.remove(wal)

    if archived_sites_path:
        archive_dir = os.path.join(archived_sites_path, site_name)
        os.makedirs(archived_sites_path, exist_ok=True)
        if os.path.exists(archive_dir):
            shutil.rmtree(archive_dir)
        shutil.move(site_path, archive_dir)
        if verbose:
            print(f"  Archived to: {archive_dir}")
    else:
        shutil.rmtree(site_path)
        if verbose:
            print(f"  Removed site directory.")

    if verbose:
        print(f"Site '{site_name}' dropped.")


def _new_site_db(
    site_name: str,
    site_config: Optional[dict] = None,
    db_name: Optional[str] = None,
    db_type: str = "sqlite",
    verbose: bool = False,
    source_sql: Optional[str] = None,
) -> None:
    """Initialize the database for a new site.

    Args:
        site_name: Site name.
        site_config: Site configuration dict.
        db_name: Database name.
        db_type: Database type.
        verbose: Print progress.
        source_sql: Optional SQL dump to restore.
    """
    db_name = db_name or site_name

    if db_type == "sqlite":
        db_path = _get_db_path(db_name)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        if source_sql and os.path.exists(source_sql):
            # Restore from SQL dump
            conn = sqlite3.connect(str(db_path))
            with open(source_sql, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.close()
            if verbose:
                print(f"  Restored database from {source_sql}")
        else:
            install_db(db_name=db_name, verbose=verbose)
    else:
        raise NotImplementedError(f"Database type '{db_type}' is not yet supported.")


def _create_admin_user(admin_password: Optional[str] = None) -> None:
    """Create the Administrator user with the given password.

    Args:
        admin_password: Plain-text password for Administrator.
    """
    from frappe.auth import hash_password

    admin = frappe.get_doc({
        "doctype": "User",
        "name": "Administrator",
        "first_name": "Administrator",
        "email": "admin@example.com",
        "enabled": 1,
        "roles": [{"role": "Administrator"}, {"role": "System Manager"}],
    })
    pw = admin_password or frappe.generate_hash(length=12)
    admin.new_password = pw
    admin.insert(ignore_permissions=True, ignore_if_duplicate=True)

    # Set password hash directly
    frappe.db.set_value(
        "User", "Administrator", "password", hash_password(pw)
    )
    frappe.db.commit()


def create_user_type(user_type_name: str, role: str) -> None:
    """Create a new User Type document.

    Args:
        user_type_name: Name of the user type.
        role: Default role assigned to this user type.
    """
    user_type = frappe.get_doc({
        "doctype": "User Type",
        "name": user_type_name,
        "role": role,
        "user_id_type": "System User",
    })
    user_type.insert(ignore_permissions=True, ignore_if_duplicate=True)
    frappe.db.commit()


def post_install(rebuild_website: bool = False) -> None:
    """Run post-install tasks.

    Args:
        rebuild_website: Trigger website rebuild after install.
    """
    if rebuild_website:
        try:
            frappe.website.utils.build_website_config()
        except Exception:
            pass

    # Clear caches
    frappe.cache.flushall()


def set_all_patches_as_completed(app: str) -> None:
    """Mark all patches defined by *app* as already applied.

    Args:
        app: The app whose patches should be marked completed.
    """
    patches = _get_app_patches(app)
    for patch in patches:
        if not frappe.db.exists("Patch Log", {"patch": patch}):
            patch_log = frappe.get_doc({
                "doctype": "Patch Log",
                "patch": patch,
            })
            patch_log.insert(ignore_permissions=True)

    frappe.db.commit()


def _get_app_doctypes(app_name: str) -> list[dict]:
    """Return DocType JSON definitions for *app_name*.

    Scans ``{app}/frappe/{app}/doctype/*/`` for ``*.json`` files.

    Args:
        app_name: The app to scan.

    Returns:
        List of parsed DocType JSON dictionaries.
    """
    doctypes: list[dict] = []

    try:
        import importlib.util

        spec = importlib.util.find_spec(app_name)
        if spec is None or spec.origin is None:
            return doctypes

        app_path = Path(spec.origin).parent
        doctype_dir = app_path / app_name / "doctype"

        if not doctype_dir.exists():
            return doctypes

        for dt_dir in doctype_dir.iterdir():
            if dt_dir.is_dir():
                json_file = dt_dir / f"{dt_dir.name}.json"
                if json_file.exists():
                    with open(json_file, "r", encoding="utf-8") as f:
                        try:
                            doctypes.append(json.load(f))
                        except json.JSONDecodeError:
                            continue
    except Exception:
        pass

    return doctypes


def _get_app_patches(app_name: str) -> list[str]:
    """Return the list of patch modules for *app_name*.

    Reads the ``patches.txt`` file from the app root.

    Args:
        app_name: The app to scan.

    Returns:
        List of patch module paths.
    """
    patches: list[str] = []

    try:
        import importlib.util

        spec = importlib.util.find_spec(app_name)
        if spec is None or spec.origin is None:
            return patches

        app_path = Path(spec.origin).parent
        patches_file = app_path / "patches.txt"

        if patches_file.exists():
            with open(patches_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patches.append(line)
    except Exception:
        pass

    return patches
