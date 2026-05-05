from __future__ import annotations

from typing import Any

import frappe


def get_all_nodes(
    doctype: str,
    parent_field: str,
    label_field: str = "name",
    parent: str | None = None,
    filters: dict[str, Any] | None = None,
    is_root: bool = False,
) -> list[dict[str, Any]]:
    """Get all nodes for a tree view.

    Returns hierarchical data for rendering a tree UI component,
    with support for lazy loading of child nodes.

    Args:
        doctype: DocType that has the tree structure.
        parent_field: Field name that references the parent node.
        label_field: Field to use as the node label (default: 'name').
        parent: Parent node value (None for root nodes).
        filters: Additional filters to apply.
        is_root: Whether to fetch root-level nodes.

    Returns:
        List of node dicts with 'value', 'label', 'expandable', 'children'.
    """
    # Build the base query
    conditions = []
    params: list[Any] = []

    if is_root or parent is None:
        conditions.append(f"(`{parent_field}` IS NULL OR `{parent_field}` = '')")
    else:
        conditions.append(f"`{parent_field}` = ?")
        params.append(parent)

    # Apply additional filters
    if filters:
        for key, value in filters.items():
            conditions.append(f"`{key}` = ?")
            params.append(value)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Get nodes at this level
    fields = ["name", label_field, parent_field, "lft", "rgt", "is_group"]
    # Also get any standard fields that exist
    std_fields = ["modified", "creation", "owner"]

    fields_str = ", ".join(f"`{f}`" for f in fields)

    query = f"""
        SELECT {fields_str}
        FROM `tab{doctype}`
        WHERE {where_clause}
        ORDER BY `lft` ASC, `{label_field}` ASC
    """

    try:
        nodes = frappe.db.sql(query, params, as_dict=True)
    except Exception:
        # lft/rgt columns may not exist - fall back
        query = f"""
            SELECT `name`, `{label_field}`, `{parent_field}`
            FROM `tab{doctype}`
            WHERE {where_clause}
            ORDER BY `{label_field}` ASC
        """
        nodes = frappe.db.sql(query, params, as_dict=True)

    result: list[dict] = []

    for node in nodes:
        node_value = node.name
        node_label = node.get(label_field, node_value)

        # Check if this node has children
        has_children = _has_children(doctype, parent_field, node_value)

        # Determine if expandable
        is_group = node.get("is_group", has_children)
        expandable = bool(is_group) or has_children

        result.append({
            "value": node_value,
            "label": node_label,
            "parent": parent,
            "expandable": expandable,
            "data": node,
        })

    return result


def get_children(
    doctype: str,
    parent_field: str = "parent",
    parent: str | None = None,
    include_root: bool = True,
) -> list[dict[str, Any]]:
    """Get direct child nodes for a tree.

    Simplified version that returns only immediate children.

    Args:
        doctype: DocType of the tree.
        parent_field: Field referencing parent.
        parent: Parent node value.
        include_root: Include root nodes when parent is None.

    Returns:
        List of child node dicts.
    """
    conditions = []
    params: list[Any] = []

    if parent is None and include_root:
        conditions.append(f"(`{parent_field}` IS NULL OR `{parent_field}` = '')")
    elif parent:
        conditions.append(f"`{parent_field}` = ?")
        params.append(parent)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    try:
        results = frappe.db.sql(
            f"""
            SELECT name, `{parent_field}` as parent, is_group
            FROM `tab{doctype}`
            WHERE {where_clause}
            ORDER BY name
            """,
            params,
            as_dict=True,
        )
    except Exception:
        # Try without is_group
        results = frappe.db.sql(
            f"""
            SELECT name, `{parent_field}` as parent
            FROM `tab{doctype}`
            WHERE {where_clause}
            ORDER BY name
            """,
            params,
            as_dict=True,
        )

    children: list[dict] = []
    for r in results:
        child_value = r.name
        has_children = _has_children(doctype, parent_field, child_value)
        is_group = r.get("is_group", has_children)

        children.append({
            "value": child_value,
            "label": child_value,
            "parent": r.get("parent"),
            "expandable": bool(is_group) or has_children,
            "is_group": bool(is_group),
            "data": r,
        })

    return children


def add_node(
    doctype: str,
    parent_field: str,
    name: str,
    parent: str | None = None,
    properties: dict[str, Any] | None = None,
    is_group: bool = False,
) -> dict[str, Any]:
    """Add a new node to the tree.

    Creates a new document with the appropriate parent reference.

    Args:
        doctype: DocType of the tree.
        parent_field: Field referencing parent.
        name: Name for the new node.
        parent: Parent node value (None for root).
        properties: Additional properties to set.
        is_group: Whether this node can have children.

    Returns:
        Created node dict.
    """
    data: dict[str, Any] = {
        "doctype": doctype,
        "name": name,
        parent_field: parent,
        "is_group": 1 if is_group else 0,
    }

    if properties:
        data.update(properties)

    doc = frappe.get_doc(data)
    doc.insert(ignore_permissions=True)

    return {
        "value": doc.name,
        "label": doc.name,
        "parent": parent,
        "expandable": bool(is_group),
        "data": doc.as_dict(),
    }


def edit_node(
    doctype: str,
    name: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Edit an existing tree node.

    Args:
        doctype: DocType of the tree.
        name: Node name to edit.
        properties: Properties to update.

    Returns:
        Updated node dict.
    """
    doc = frappe.get_doc(doctype, name)

    for key, value in properties.items():
        if key not in ("name", "doctype"):
            doc.set(key, value)

    doc.save(ignore_permissions=True)

    return {
        "value": doc.name,
        "label": doc.name,
        "data": doc.as_dict(),
    }


def delete_node(doctype: str, name: str) -> None:
    """Delete a tree node.

    Prevents deletion if the node has children.

    Args:
        doctype: DocType of the tree.
        name: Node name to delete.
    """
    # Check for children
    meta = frappe.get_meta(doctype)
    parent_field = _get_parent_field(meta)

    children_count = frappe.db.count(doctype, filters={parent_field: name})
    if children_count > 0:
        frappe.throw(f"Cannot delete '{name}' because it has {children_count} child nodes.")

    frappe.delete_doc(doctype, name, ignore_permissions=True)


def move_node(
    doctype: str,
    name: str,
    new_parent: str | None = None,
    parent_field: str = "parent",
) -> dict[str, Any]:
    """Move a node to a new parent.

    Args:
        doctype: DocType of the tree.
        name: Node to move.
        new_parent: New parent value (None for root).
        parent_field: Field referencing parent.

    Returns:
        Updated node dict.
    """
    doc = frappe.get_doc(doctype, name)

    # Prevent circular references
    if new_parent:
        if new_parent == name:
            frappe.throw("A node cannot be its own parent.")

        # Check if new_parent is not a descendant of name
        if _is_descendant(doctype, parent_field, name, new_parent):
            frappe.throw("Cannot move a node under its own descendant.")

    doc.set(parent_field, new_parent)
    doc.save(ignore_permissions=True)

    return {
        "value": doc.name,
        "label": doc.name,
        "parent": new_parent,
        "data": doc.as_dict(),
    }


def get_tree_root(
    doctype: str,
    root_label: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get the root node of a tree.

    Some trees have a single virtual root node. This returns
    that root with its children.

    Args:
        doctype: DocType of the tree.
        root_label: Label for the virtual root.
        filters: Filters for root selection.

    Returns:
        Root node dict with 'value', 'label', 'children'.
    """
    children = get_all_nodes(
        doctype=doctype,
        parent_field="parent",
        parent=None,
        filters=filters,
        is_root=True,
    )

    return {
        "value": "root",
        "label": root_label or doctype,
        "expandable": len(children) > 0,
        "children": children,
        "is_root": True,
    }


def rebuild_tree(doctype: str, parent_field: str = "parent") -> None:
    """Rebuild the lft/rgt nested set values for a tree.

    Recalculates the left/right values for all nodes using the
    nested set model. This is useful for re-syncing the tree structure.

    Args:
        doctype: DocType of the tree.
        parent_field: Field referencing parent.
    """
    try:
        # Check if lft/rgt columns exist
        columns = [d[0] for d in frappe.db.sql(f"PRAGMA table_info(`tab{doctype}`)", as_dict=False)]
    except Exception:
        return

    if "lft" not in columns or "rgt" not in columns:
        return

    # Build tree structure in memory
    all_nodes = frappe.db.get_all(
        doctype,
        fields=["name", parent_field, "is_group"],
        order_by="creation",
    )

    # Build adjacency list
    children_map: dict[str | None, list[str]] = {}
    for node in all_nodes:
        parent = node.get(parent_field) or None
        if parent == "":
            parent = None
        if parent not in children_map:
            children_map[parent] = []
        children_map[parent].append(node.name)

    # Assign lft/rgt values using DFS
    counter = [0]  # Use list for mutable reference

    def assign_lft_rgt(node_name: str):
        counter[0] += 1
        lft = counter[0]

        for child in sorted(children_map.get(node_name, [])):
            assign_lft_rgt(child)

        counter[0] += 1
        rgt = counter[0]

        frappe.db.set_value(doctype, node_name, "lft", lft, update_modified=False)
        frappe.db.set_value(doctype, node_name, "rgt", rgt, update_modified=False)

    # Start from root nodes
    root_nodes = sorted(children_map.get(None, []))
    for root in root_nodes:
        assign_lft_rgt(root)

    frappe.db.commit()


def get_node_path(
    doctype: str,
    parent_field: str,
    name: str,
) -> list[dict[str, Any]]:
    """Get the path from root to a specific node.

    Args:
        doctype: DocType of the tree.
        parent_field: Field referencing parent.
        name: Target node name.

    Returns:
        List of node dicts from root to target.
    """
    path: list[dict] = []
    current = name
    visited: set[str] = set()

    while current and current not in visited:
        visited.add(current)
        try:
            node = frappe.db.get_value(
                doctype,
                current,
                ["name", parent_field, "is_group"],
                as_dict=True,
            )
            if not node:
                break
            path.insert(0, {
                "value": node.name,
                "label": node.name,
                "is_group": node.get("is_group", 0),
            })
            current = node.get(parent_field)
            if not current:
                break
        except Exception:
            break

    return path


def get_descendants(
    doctype: str,
    parent_field: str,
    name: str,
    include_self: bool = False,
) -> list[str]:
    """Get all descendant node names.

    Args:
        doctype: DocType of the tree.
        parent_field: Field referencing parent.
        name: Parent node name.
        include_self: Include the parent node in results.

    Returns:
        List of descendant node names.
    """
    descendants: list[str] = []
    if include_self:
        descendants.append(name)

    to_process = [name]
    visited: set[str] = set()

    while to_process:
        current = to_process.pop(0)
        if current in visited:
            continue
        visited.add(current)

        children = frappe.db.get_all(
            doctype,
            filters={parent_field: current},
            pluck="name",
        )
        descendants.extend(children)
        to_process.extend(children)

    return descendants


def get_siblings(
    doctype: str,
    parent_field: str,
    name: str,
    include_self: bool = False,
) -> list[dict[str, Any]]:
    """Get sibling nodes.

    Args:
        doctype: DocType of the tree.
        parent_field: Field referencing parent.
        name: Node name to find siblings for.
        include_self: Include the node itself in results.

    Returns:
        List of sibling node dicts.
    """
    # Get the parent of this node
    parent = frappe.db.get_value(doctype, name, parent_field)

    if not parent:
        filters = {
            parent_field: ("in", ["", None]),
        }
    else:
        filters = {parent_field: parent}

    siblings = frappe.db.get_all(
        doctype,
        filters=filters,
        fields=["name", "is_group"],
        order_by="name",
    )

    result = []
    for s in siblings:
        if not include_self and s.name == name:
            continue
        result.append({
            "value": s.name,
            "label": s.name,
            "is_group": s.get("is_group", 0),
        })

    return result


# --- Internal helpers ---


def _has_children(doctype: str, parent_field: str, parent_value: str) -> bool:
    """Check if a node has any children."""
    try:
        count = frappe.db.count(doctype, filters={parent_field: parent_value})
        return count > 0
    except Exception:
        return False


def _is_descendant(
    doctype: str,
    parent_field: str,
    ancestor: str,
    candidate: str,
) -> bool:
    """Check if candidate is a descendant of ancestor."""
    current = candidate
    visited: set[str] = set()

    while current:
        if current in visited:
            break  # Circular reference
        visited.add(current)

        parent = frappe.db.get_value(doctype, current, parent_field)
        if not parent:
            break
        if parent == ancestor:
            return True
        current = parent

    return False


def _get_parent_field(meta: Any) -> str:
    """Determine the parent field from DocType meta."""
    for field in meta.fields if hasattr(meta, "fields") else []:
        if getattr(field, "fieldtype", "") == "Link":
            options = getattr(field, "options", "")
            if options == meta.name:
                return getattr(field, "fieldname", "parent")
    return "parent"


def get_tree_filters(doctype: str) -> list[dict[str, Any]]:
    """Get available filters for a tree DocType.

    Args:
        doctype: DocType name.

    Returns:
        List of filter field dicts.
    """
    try:
        meta = frappe.get_meta(doctype)
        filters: list[dict] = []

        for field in meta.fields if hasattr(meta, "fields") else []:
            if getattr(field, "in_list_view", 0) or getattr(field, "fieldtype", "") in (
                "Data", "Select", "Link", "Check", "Date"
            ):
                filters.append({
                    "fieldname": getattr(field, "fieldname", ""),
                    "label": getattr(field, "label", ""),
                    "fieldtype": getattr(field, "fieldtype", "Data"),
                    "options": getattr(field, "options", ""),
                })

        return filters
    except Exception:
        return []
