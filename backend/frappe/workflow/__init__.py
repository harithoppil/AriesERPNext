"""
Frappe Workflow Engine

A fully-featured state-machine workflow engine that replaces the original
``frappe/workflow`` module.  Every workflow defines:

- **States** — the possible states a document can be in
- **Transitions** — rules for moving from one state to another
- **Actions** — side-effects (hooks, notifications, field updates) on transition
- **Conditions** — guard expressions that must evaluate to True for a transition

The engine is **DocType-aware**: each workflow is attached to exactly one
DocType, and the workflow state is stored in a designated ``status``-style
field on the document.

Key API::

    # Get available transitions for a document
    actions = get_transitions(doc)

    # Apply a transition
    apply_workflow(doc, action_name)

    # Get the full workflow definition
    wf = get_workflow(doctype)

    # Check if a document has an active workflow
    has_workflow(doctype) -> bool

    # Bulk workflow operations
    bulk_workflow_approval(documents, action)

Example::

    # In a controller or API endpoint
    doc = frappe.get_doc("Leave Application", "LA-00001")

    # See what the user can do
    for t in get_transitions(doc):
        print(f"Can '{t.action}' from {t.state} to {t.next_state}")

    # Approve it
    apply_workflow(doc, "Approve")
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any, Callable, Optional, Union

import frappe
from frappe.exceptions import PermissionError, ValidationError
from frappe.types import _dict
from frappe.utils import cint, cstr, now

logger = logging.getLogger("frappe.workflow")

# ─── Module-level exports ───────────────────────────────────────────────────

__all__ = [
    "get_workflow",
    "has_workflow",
    "get_workflow_state_field",
    "get_transitions",
    "get_document_state",
    "apply_workflow",
    "can_cancel_document",
    "bulk_workflow_approval",
    "Workflow",
    "WorkflowTransition",
    "WorkflowState",
]

# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════


def get_workflow(doctype: str) -> "Workflow":
    """Return the active :class:`Workflow` for a DocType.

    Raises ``DoesNotExistError`` if no workflow is configured.
    """
    if not hasattr(_workflow_cache, "workflows"):
        _workflow_cache.workflows = {}

    if doctype not in _workflow_cache.workflows:
        wf_doc = _load_workflow_document(doctype)
        if not wf_doc:
            from frappe.exceptions import DoesNotExistError

            raise DoesNotExistError(f"No workflow configured for {doctype}")
        _workflow_cache.workflows[doctype] = Workflow(wf_doc)

    return _workflow_cache.workflows[doctype]


def has_workflow(doctype: str) -> bool:
    """Return True if a workflow is configured for *doctype*."""
    try:
        get_workflow(doctype)
        return True
    except Exception:
        return False


def get_workflow_state_field(doctype: str) -> str:
    """Return the field name that stores the workflow state.

    Defaults to ``"workflow_state"`` or the field configured on the
    workflow document.
    """
    try:
        wf = get_workflow(doctype)
        return wf.workflow_state_field
    except Exception:
        return "workflow_state"


def get_transitions(
    doc,
    workflow: Optional["Workflow"] = None,
) -> list["WorkflowTransition"]:
    """Return the transitions that are currently valid for *doc*.

    A transition is valid when:
    1. The document is in the transition's ``from_state``.
    2. The user's roles intersect with the transition's allowed roles.
    3. The transition's condition evaluates to True.
    """
    if workflow is None:
        workflow = get_workflow(doc.doctype)

    current_state = _get_current_state(doc, workflow)
    user_roles = set(frappe.get_roles())

    valid: list[WorkflowTransition] = []
    for transition in workflow.transitions:
        if transition.state != current_state:
            continue

        # Role check
        if transition.allowed_roles:
            if not user_roles.intersection(set(transition.allowed_roles)):
                continue

        # Condition check
        if transition.condition:
            if not _eval_condition(doc, transition.condition):
                continue

        valid.append(transition)

    return valid


def get_document_state(
    doctype: str,
    state: str,
    workflow: Optional["Workflow"] = None,
) -> Optional["WorkflowState"]:
    """Get the :class:`WorkflowState` definition for a named state."""
    if workflow is None:
        workflow = get_workflow(doctype)
    return workflow.get_state(state)


def apply_workflow(
    doc,
    action: str,
    workflow: Optional["Workflow"] = None,
) -> Any:
    """Apply a workflow transition to a document.

    This is the primary API for moving a document through its workflow.
    It performs validation, updates the state field, runs hooks, and
    saves the document.

    Parameters
    ----------
    doc :
        Document object or dict with at least ``doctype`` and ``name``.
    action :
        The transition action name (e.g. ``"Approve"``, ``"Reject"``).
    workflow :
        Optional pre-loaded workflow (saves a DB query).

    Returns
    -------
    Document :
        The updated document after the transition.
    """
    if isinstance(doc, dict):
        doc = frappe.get_doc(doc["doctype"], doc["name"])

    if workflow is None:
        workflow = get_workflow(doc.doctype)

    # Find the matching transition
    transitions = get_transitions(doc, workflow)
    matching = [t for t in transitions if t.action == action]

    if not matching:
        valid_actions = ", ".join(t.action for t in transitions)
        raise ValidationError(
            f"Action '{action}' is not valid for {doc.doctype} {doc.name} "
            f"(current state: {_get_current_state(doc, workflow)}). "
            f"Valid actions: {valid_actions or 'none'}"
        )

    transition = matching[0]

    # Check document permission
    if not doc.has_permission("write") and not doc.flags.ignore_permissions:
        raise PermissionError(
            f"No write permission on {doc.doctype} {doc.name}"
        )

    # Run before_workflow_action hook
    doc.run_method("before_workflow_action", action=action, transition=transition)

    # Store old state for hooks
    old_state = _get_current_state(doc, workflow)

    # Update state
    _set_workflow_state(doc, workflow, transition.next_state)

    # Update any fields specified by the transition
    if transition.field_updates:
        for fieldname, value in transition.field_updates.items():
            setattr(doc, fieldname, value)

    # Save
    doc.save(ignore_permissions=doc.flags.get("ignore_permissions"))

    # Run after_workflow_action hook
    doc.run_method(
        "after_workflow_action",
        action=action,
        transition=transition,
        old_state=old_state,
    )

    # Send notifications if configured
    _send_transition_notifications(doc, workflow, transition, old_state)

    logger.info(
        "Workflow: %s/%s transitioned '%s' from '%s' to '%s' by %s",
        doc.doctype,
        doc.name,
        action,
        old_state,
        transition.next_state,
        frappe.session.user,
    )

    return doc


def can_cancel_document(doc) -> bool:
    """Return True if the document can be cancelled in its current state.

    A document can be cancelled when:
    1. It has no workflow, OR
    2. Its current workflow state allows cancelling.
    """
    if not has_workflow(doc.doctype):
        return True

    try:
        workflow = get_workflow(doc.doctype)
        current_state = _get_current_state(doc, workflow)
        state_def = workflow.get_state(current_state)
        if state_def:
            return state_def.allow_edit or "System Manager" in frappe.get_roles()
        return True
    except Exception:
        return True


def bulk_workflow_approval(
    documents: list[Union[str, dict, Any]],
    action: str,
    doctype: Optional[str] = None,
) -> dict[str, Any]:
    """Apply a workflow action to multiple documents.

    Parameters
    ----------
    documents :
        List of document names, dicts, or Document objects.
    action :
        Workflow action to apply.
    doctype :
        Required if *documents* contains name strings.

    Returns
    -------
    dict :
        ``{"success": list[str], "failure": list[str], "errors": list[str]}``
    """
    success: list[str] = []
    failure: list[str] = []
    errors: list[str] = []

    for item in documents:
        try:
            if isinstance(item, str):
                if not doctype:
                    raise ValueError("doctype is required when documents are strings")
                doc = frappe.get_doc(doctype, item)
            elif isinstance(item, dict):
                doc = frappe.get_doc(item["doctype"], item["name"])
            else:
                doc = item

            apply_workflow(doc, action)
            success.append(doc.name)

        except Exception as exc:
            name = item if isinstance(item, str) else getattr(item, "name", str(item))
            failure.append(name)
            errors.append(f"{name}: {exc}")

    return {"success": success, "failure": failure, "errors": errors}


# ═══════════════════════════════════════════════════════════════════════════════
#  WORKFLOW DATA MODEL
# ═══════════════════════════════════════════════════════════════════════════════


class WorkflowState:
    """Represents a single state in a workflow.

    Attributes
    ----------
    state : str
        The state name (stored in the document's state field).
    style : str
        Bootstrap-style color indicator (e.g. ``"Success"``, ``"Danger"``).
    doc_status : int
        Document status mapped to this state (0=draft, 1=submitted, 2=cancelled).
    allow_edit : str or None
        Role allowed to edit documents in this state.
    update_field : str or None
        Field to update when entering this state.
    update_value : Any
        Value to set on the update field.
    """

    def __init__(
        self,
        state: str,
        style: str = "",
        doc_status: int = 0,
        allow_edit: Optional[str] = None,
        update_field: Optional[str] = None,
        update_value: Any = None,
    ):
        self.state = state
        self.style = style
        self.doc_status = doc_status
        self.allow_edit = allow_edit
        self.update_field = update_field
        self.update_value = update_value


class WorkflowTransition:
    """Represents a single allowed transition in a workflow.

    Attributes
    ----------
    action : str
        Human-readable action name (e.g. ``"Approve"``).
    state : str
        Source state.
    next_state : str
        Destination state.
    allowed_roles : list[str]
        Roles that may trigger this transition.
    condition : str or None
        Python expression that must evaluate to True.
    field_updates : dict
        Field name → value updates applied on transition.
    """

    def __init__(
        self,
        action: str,
        state: str,
        next_state: str,
        allowed_roles: Optional[list[str]] = None,
        condition: Optional[str] = None,
        field_updates: Optional[dict[str, Any]] = None,
    ):
        self.action = action
        self.state = state
        self.next_state = next_state
        self.allowed_roles = allowed_roles or []
        self.condition = condition
        self.field_updates = field_updates or {}


class Workflow:
    """Full workflow definition for a DocType.

    Attributes
    ----------
    doctype : str
        The DocType this workflow applies to.
    name : str
        Workflow name (from the ``Workflow`` document).
    workflow_state_field : str
        Document field that stores the current workflow state.
    is_active : bool
    states : list[WorkflowState]
    transitions : list[WorkflowTransition]
    send_email_alert : bool
        Whether to send email notifications on transitions.
    """

    def __init__(self, doc: Any):
        """Build a Workflow from a ``Workflow`` Document object."""
        self.doctype = doc.document_type
        self.name = doc.name
        self.workflow_state_field = getattr(doc, "workflow_state_field", "workflow_state") or "workflow_state"
        self.is_active = cint(getattr(doc, "is_active", 1))
        self.send_email_alert = cint(getattr(doc, "send_email_alert", 0))

        self.states: list[WorkflowState] = []
        self.transitions: list[WorkflowTransition] = []

        # Parse states
        for state_row in getattr(doc, "states", []) or []:
            self.states.append(
                WorkflowState(
                    state=cstr(getattr(state_row, "state", "")),
                    style=cstr(getattr(state_row, "style", "")),
                    doc_status=cint(getattr(state_row, "doc_status", 0)),
                    allow_edit=cstr(getattr(state_row, "allow_edit", None)) or None,
                    update_field=cstr(getattr(state_row, "update_field", None)) or None,
                    update_value=getattr(state_row, "update_value", None),
                )
            )

        # Parse transitions
        for trans_row in getattr(doc, "transitions", []) or []:
            roles = []
            roles_raw = getattr(trans_row, "allowed", None)
            if roles_raw:
                if isinstance(roles_raw, str):
                    roles = [r.strip() for r in roles_raw.split(",") if r.strip()]
                elif isinstance(roles_raw, (list, tuple)):
                    roles = list(roles_raw)

            self.transitions.append(
                WorkflowTransition(
                    action=cstr(getattr(trans_row, "action", "")),
                    state=cstr(getattr(trans_row, "state", "")),
                    next_state=cstr(getattr(trans_row, "next_state", "")),
                    allowed_roles=roles,
                    condition=cstr(getattr(trans_row, "condition", None)) or None,
                    field_updates=self._parse_field_updates(
                        getattr(trans_row, "field_updates", None)
                    ),
                )
            )

    def get_state(self, state_name: str) -> Optional[WorkflowState]:
        """Return the WorkflowState with the given name."""
        for s in self.states:
            if s.state == state_name:
                return s
        return None

    @staticmethod
    def _parse_field_updates(raw: Any) -> dict[str, Any]:
        """Parse field updates from a string or dict."""
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


class _WorkflowCache:
    """Simple module-level cache for workflow definitions."""

    def __init__(self):
        self.workflows: dict[str, Workflow] = {}

    def clear(self, doctype: Optional[str] = None) -> None:
        if doctype:
            self.workflows.pop(doctype, None)
        else:
            self.workflows.clear()


_workflow_cache = _WorkflowCache()


def _load_workflow_document(doctype: str) -> Any:
    """Fetch the active Workflow document for a DocType.

    Returns ``None`` if no workflow is found.
    """
    try:
        workflows = frappe.db.get_all(
            "Workflow",
            filters={
                "document_type": doctype,
                "is_active": 1,
            },
            fields=["name"],
            limit=1,
            order_by="modified desc",
        )
        if not workflows:
            return None

        return frappe.get_doc("Workflow", workflows[0].name)
    except Exception:
        return None


def _get_current_state(doc, workflow: Workflow) -> str:
    """Read the current workflow state from a document."""
    state_field = workflow.workflow_state_field
    return cstr(getattr(doc, state_field, "")) or ""


def _set_workflow_state(doc, workflow: Workflow, state: str) -> None:
    """Set the workflow state on a document."""
    state_field = workflow.workflow_state_field
    setattr(doc, state_field, state)

    # Update docstatus if the state maps to one
    state_def = workflow.get_state(state)
    if state_def:
        doc.docstatus = state_def.doc_status


def _eval_condition(doc, condition: str) -> bool:
    """Evaluate a transition condition expression.

    The expression is evaluated in a restricted namespace with ``doc``
    available.  For safety, only a whitelist of builtins is allowed.
    """
    if not condition:
        return True

    namespace = {
        "doc": doc,
        "frappe": frappe,
        "True": True,
        "False": False,
        "None": None,
        "int": int,
        "float": float,
        "str": str,
        "len": len,
        "sum": sum,
        "any": any,
        "all": all,
        "max": max,
        "min": min,
        "round": round,
    }

    try:
        result = eval(condition, {"__builtins__": {}}, namespace)  # noqa: S307
        return bool(result)
    except Exception as exc:
        logger.warning("Workflow condition evaluation failed: %s  (condition: %s)", exc, condition)
        return False


def _send_transition_notifications(
    doc,
    workflow: Workflow,
    transition: WorkflowTransition,
    old_state: str,
) -> None:
    """Send email notifications on workflow transitions if configured."""
    if not workflow.send_email_alert:
        return

    try:
        subject = f"{doc.doctype} {doc.name}: {transition.action}"
        message = (
            f"<p>Document <b>{doc.doctype} {doc.name}</b> has been "
            f"<b>{transition.action}d</b> by <b>{frappe.session.user}</b>.</p>"
            f"<p>State changed from <i>{old_state}</i> to <i>{transition.next_state}</i>.</p>"
        )

        frappe.sendmail(
            recipients=_get_notification_recipients(doc, workflow, transition),
            subject=subject,
            message=message,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )
    except Exception:
        logger.debug("Workflow notification failed", exc_info=True)


def _get_notification_recipients(
    doc,
    workflow: Workflow,
    transition: WorkflowTransition,
) -> list[str]:
    """Determine who should receive workflow transition notifications."""
    recipients: list[str] = []

    # Document owner
    owner = getattr(doc, "owner", None)
    if owner:
        recipients.append(owner)

    # Allowed roles on the transition
    for role in transition.allowed_roles:
        users = frappe.db.get_all(
            "Has Role",
            filters={"role": role, "parenttype": "User"},
            pluck="parent",
        )
        for user in (users or []):
            if user not in recipients:
                recipients.append(user)

    return recipients


# ═══════════════════════════════════════════════════════════════════════════════
#  WORKFLOW SETUP UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════


def get_workflow_field_status(doctype: str, doc: Optional[Any] = None) -> dict[str, dict]:
    """Return field-level read/write status for the current workflow state.

    Used by form UIs to lock/unlock fields based on workflow state.

    Returns a dict of ``{fieldname: {"read_only": bool, "hidden": bool}}``.
    """
    try:
        workflow = get_workflow(doctype)
    except Exception:
        return {}

    if doc is None:
        current_state = ""
    else:
        current_state = _get_current_state(doc, workflow)

    state_def = workflow.get_state(current_state)
    if not state_def:
        return {}

    # Build field status based on state
    result: dict[str, dict] = {}
    for field in (doc.meta.fields if doc and hasattr(doc, "meta") else []):
        result[field.fieldname] = {
            "read_only": state_def.allow_edit is not None,
            "hidden": False,
        }

    return result


def get_all_workflows(doctype: Optional[str] = None) -> list[dict]:
    """Return a list of all workflow definitions.

    If *doctype* is given, filter to workflows for that DocType.
    """
    filters: dict[str, Any] = {"is_active": 1}
    if doctype:
        filters["document_type"] = doctype

    try:
        return frappe.db.get_all(
            "Workflow",
            filters=filters,
            fields=["name", "document_type", "workflow_state_field", "is_active", "modified"],
            order_by="document_type",
        )
    except Exception:
        return []


def clear_workflow_cache(doctype: Optional[str] = None) -> None:
    """Clear cached workflow definitions.

    Call this after modifying a workflow document.
    """
    _workflow_cache.clear(doctype)


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKWARDS COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════════════════


def get_workflow_name(doctype: str) -> Optional[str]:
    """Return the name of the workflow for a DocType, or None."""
    try:
        wf = get_workflow(doctype)
        return wf.name
    except Exception:
        return None
