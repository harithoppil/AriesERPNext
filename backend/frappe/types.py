"""Frappe type definitions.

This module provides the ``_dict`` type used throughout Frappe/ERPNext
whenever ``as_dict=True`` is passed to database methods.
"""
from __future__ import annotations

from collections.abc import Mapping


class _dict(dict):
	"""Dictionary subclass that allows attribute-style access.

	This is the primary dict type used by Frappe.  It enables both
	``d['key']`` and ``d.key`` access patterns, which is heavily relied
	on in ERPNext controller code.
	"""

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.__dict__ = self

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(
				f"'{type(self).__name__}' object has no attribute '{key}'"
			) from None

	def __setattr__(self, key, value):
		self[key] = value

	def __delattr__(self, key):
		try:
			del self[key]
		except KeyError:
			raise AttributeError(
				f"'{type(self).__name__}' object has no attribute '{key}'"
			) from None

	def copy(self) -> "_dict":
		"""Return a shallow copy as a new _dict."""
		return _dict(super().copy())

	@classmethod
	def from_keys(cls, keys, value=None):
		"""Create a _dict from an iterable of keys."""
		return cls(dict.fromkeys(keys, value))

	@classmethod
	def from_mapping(cls, mapping: Mapping):
		"""Create a _dict from any mapping."""
		return cls(mapping)

	def __repr__(self) -> str:
		items = ", ".join(f"{k!r}: {v!r}" for k, v in list(self.items())[:10])
		if len(self) > 10:
			items += ", ..."
		return f"_dict({{{items}}})"
