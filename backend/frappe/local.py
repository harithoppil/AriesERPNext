"""
Frappe Local — Thread-Local Context Management

Replaces werkzeug.local.Local and LocalProxy with Python's contextvars,
which is the modern, type-safe approach for async-aware context storage.

Every ERPNext file accesses `frappe.db`, `frappe.session`, `frappe.user`, etc.
These are all proxies into a per-request context stored here.
"""

from __future__ import annotations

import contextvars
from typing import Any, Generic, TypeVar

from frappe.types import _dict

_T = TypeVar("_T")

# The master context variable — holds a _dict with all local state
_frappe_context: contextvars.ContextVar[_dict | None] = contextvars.ContextVar(
    "frappe_context", default=None
)


class Local:
    """Replacement for werkzeug.local.Local.

    Provides attribute-style access to context-local storage.
    Each request, background job, or CLI command gets its own context.
    """

    def __getattr__(self, name: str) -> Any:
        ctx = _frappe_context.get()
        if ctx is None:
            # Context not yet initialized — return None for hasattr checks
            # This is needed during init() before context is set up
            return None
        return ctx.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        ctx = _frappe_context.get()
        if ctx is None:
            raise RuntimeError(
                "Frappe context not initialized. "
                "Call frappe.init(site) first."
            )
        ctx[name] = value

    def __hasattr__(self, name: str) -> bool:
        ctx = _frappe_context.get()
        if ctx is None:
            return False
        return name in ctx

    def __delattr__(self, name: str) -> None:
        ctx = _frappe_context.get()
        if ctx is not None and name in ctx:
            del ctx[name]

    def get(self, name: str, default: Any = None) -> Any:
        """Get a value from local context with default."""
        ctx = _frappe_context.get()
        if ctx is None:
            return default
        return ctx.get(name, default)

    def __contains__(self, name: str) -> bool:
        ctx = _frappe_context.get()
        if ctx is None:
            return False
        return name in ctx

    def __call__(self, name: str, default: Any = None) -> "LocalProxy":
        """Return a LocalProxy for the given attribute name.

        Usage: db = local('db')  → returns LocalProxy that resolves to local.db
        """
        return LocalProxy(name, default=default)

    def __repr__(self) -> str:
        ctx = _frappe_context.get()
        if ctx is None:
            return "<Local (uninitialized)>"
        return f"<Local {dict(ctx)!r}>"


class LocalProxy:
    """Replacement for werkzeug.local.LocalProxy.

    Creates a proxy object that resolves to a value from the local context
    at access time. This is what makes `frappe.db` work — it's a proxy that
    resolves to the actual database connection when accessed.
    """

    def __init__(self, local_name: str, default: Any = None) -> None:
        self._local_name = local_name
        self._default = default

    def _get_current_object(self) -> Any:
        ctx = _frappe_context.get()
        if ctx is None:
            if self._default is not None:
                return self._default
            raise RuntimeError(
                f"Frappe context not initialized. "
                f"Cannot access 'frappe.{self._local_name}'."
            )
        return ctx.get(self._local_name, self._default)

    # Dict-like access
    def __getitem__(self, key: str) -> Any:
        return self._get_current_object()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._get_current_object()[key] = value

    def __delitem__(self, key: str) -> None:
        del self._get_current_object()[key]

    def __contains__(self, key: str) -> bool:
        return key in self._get_current_object()

    def get(self, key: str, default: Any = None) -> Any:
        return self._get_current_object().get(key, default)

    # Attribute access
    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_current_object(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_current_object(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._get_current_object(), name)

    # String representation
    def __repr__(self) -> str:
        try:
            obj = self._get_current_object()
        except RuntimeError:
            return f"<LocalProxy '{self._local_name}' (uninitialized)>"
        return repr(obj)

    def __str__(self) -> str:
        return str(self._get_current_object())

    # Callable
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._get_current_object()(*args, **kwargs)

    # Iteration
    def __iter__(self):
        return iter(self._get_current_object())

    def __len__(self) -> int:
        return len(self._get_current_object())

    # Comparison
    def __eq__(self, other: object) -> bool:
        return self._get_current_object() == other

    def __ne__(self, other: object) -> bool:
        return self._get_current_object() != other

    def __bool__(self) -> bool:
        return bool(self._get_current_object())

    # Arithmetic
    def __add__(self, other: Any) -> Any:
        return self._get_current_object() + other

    def __sub__(self, other: Any) -> Any:
        return self._get_current_object() - other


# Global instances
local = Local()


def initialize_context(initial: dict[str, Any] | None = None) -> None:
    """Initialize a new Frappe context.

    Called by frappe.init() to set up the local storage for a request/job.
    """
    ctx = _dict(initial or {})
    _frappe_context.set(ctx)
    return ctx


def release_context() -> None:
    """Release the current Frappe context.

    Called by frappe.destroy() to clean up after a request/job.
    """
    _frappe_context.set(None)


def get_context() -> _dict | None:
    """Get the current context dict (for inspection/debugging)."""
    return _frappe_context.get()
