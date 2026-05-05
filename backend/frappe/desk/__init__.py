from __future__ import annotations

"""Desk UI Backend subpackage.

Provides the backend API endpoints and data utilities that power
the Frappe Desk UI, including list views, form views, reports,
workspaces, and tree views.
"""

from frappe.desk.reportview import get_list_data, get_count

__all__ = ["get_list_data", "get_count"]
