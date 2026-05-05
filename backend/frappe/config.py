"""
Frappe Configuration — Site and Common Configuration Management

Replaces frappe.config — handles loading site_config.json, common_site_config.json,
and providing the `frappe.conf` dict that ERPNext relies on.
"""

from __future__ import annotations

import json
import os
from typing import Any

from frappe.types import _dict


def get_site_config(
    sites_path: str = ".",
    site_path: str | None = None,
    cached: bool = False,
) -> _dict:
    """Load site configuration from site_config.json.

    Returns a _dict with all configuration values. This becomes frappe.conf
    after init() is called.
    """
    config = _dict()

    # Load common_site_config.json (bench-level defaults)
    common_config_path = os.path.join(sites_path, "common_site_config.json")
    if os.path.exists(common_config_path):
        with open(common_config_path) as f:
            config.update(json.load(f))

    # Load site-specific config
    if site_path:
        site_config_path = os.path.join(site_path, "site_config.json")
        if os.path.exists(site_config_path):
            with open(site_config_path) as f:
                config.update(json.load(f))

    # Set defaults
    config.setdefault("db_type", "sqlite")
    config.setdefault("db_name", "site_database")
    config.setdefault("db_host", "localhost")
    config.setdefault("db_port", None)
    config.setdefault("developer_mode", 0)
    config.setdefault("lang", "en")
    config.setdefault("logging", 0)
    config.setdefault("server_script_enabled", False)
    config.setdefault("ignore_csrf", False)

    return config


def get_common_site_config(sites_path: str = ".") -> _dict:
    """Load only the common (bench-level) configuration."""
    config = _dict()
    common_config_path = os.path.join(sites_path, "common_site_config.json")
    if os.path.exists(common_config_path):
        with open(common_config_path) as f:
            config.update(json.load(f))
    return config


def get_conf(site: str | None = None) -> _dict:
    """Get configuration for a site.

    Convenience function used by various modules that need config
    without having initialized the full frappe context.
    """
    if site:
        sites_path = os.environ.get("SITES_PATH", ".")
        site_path = os.path.join(sites_path, site)
        return get_site_config(sites_path=sites_path, site_path=site_path)
    # Return empty config if no site specified
    return _dict()


def update_site_config(key: str, value: Any, site_path: str | None = None) -> None:
    """Update a value in site_config.json and save it back."""
    if not site_path:
        from frappe import local

        site_path = local.site_path

    site_config_path = os.path.join(site_path, "site_config.json")
    config = _dict()

    if os.path.exists(site_config_path):
        with open(site_config_path) as f:
            config.update(json.load(f))

    config[key] = value

    with open(site_config_path, "w") as f:
        json.dump(dict(config), f, indent=2)
