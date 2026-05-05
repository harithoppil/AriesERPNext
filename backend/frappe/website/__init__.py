from __future__ import annotations

"""Website rendering and serving subpackage.

Provides the public website serving infrastructure for Frappe,
including route resolution, template rendering, and context building.
"""

from frappe.website.serve import render, resolve_route

__all__ = ["render", "resolve_route"]
