"""Frappe exception hierarchy.

All exceptions raised by the database layer are defined here so that
calling code can catch them using the same names as the original Frappe
framework.
"""
from __future__ import annotations


class FrappeException(Exception):
	"""Base exception for all Frappe errors."""


class ValidationError(FrappeException):
	"""Raised when a validation rule fails."""


class PermissionError(FrappeException):
	"""Raised when the user lacks permission for an operation."""


class DoesNotExistError(FrappeException):
	"""Raised when a referenced document does not exist."""
	http_status_code = 404
	doctype = None

	def __init__(self, msg=None, doctype=None, docname=None, **kwargs):
		if msg is None:
			if doctype and docname:
				msg = f"{doctype} {docname} not found"
			elif doctype:
				msg = f"{doctype} not found"
			else:
				msg = "Document not found"
		super().__init__(msg)
		self.doctype = doctype
		self.docname = docname


class DuplicateEntryError(FrappeException):
	"""Raised when a unique constraint is violated."""


# ---------------------------------------------------------------------------
# Database exceptions
# ---------------------------------------------------------------------------

class DatabaseError(FrappeException):
	"""Base exception for database-related errors."""


class SQLError(DatabaseError):
	"""Raised when a SQL syntax or execution error occurs."""


class IntegrityError(DatabaseError):
	"""Raised when an integrity constraint is violated."""


class OperationalError(DatabaseError):
	"""Raised when a database operation fails (connection loss, etc.)."""


class DataError(DatabaseError):
	"""Raised for invalid data (e.g., division by zero)."""


class NotSupportedError(DatabaseError):
	"""Raised when an unsupported database feature is used."""


class InterfaceError(DatabaseError):
	"""Raised for database interface-related errors."""


# ---------------------------------------------------------------------------
# Authentication / Session
# ---------------------------------------------------------------------------

class AuthenticationError(FrappeException):
	"""Raised on login/authentication failure."""


class SessionExpiredError(FrappeException):
	"""Raised when the user session has expired."""


SessionExpired = SessionExpiredError  # Alias used by Document model


# ---------------------------------------------------------------------------
# Document lifecycle exceptions
# ---------------------------------------------------------------------------

class MandatoryError(ValidationError):
	"""Raised when a mandatory field is missing."""


class LinkValidationError(ValidationError):
	"""Raised when link field validation fails."""


class CancelledLinkError(LinkValidationError):
	"""Raised when a linked document is cancelled."""


class DocumentLockedError(FrappeException):
	"""Raised when a document is locked by another process."""


class TimestampMismatchError(FrappeException):
	"""Raised when a document has been modified by another user/process."""


class NameError(FrappeException):
	"""Raised when there's an issue with a document name."""


class CircularLinkingError(ValidationError):
	"""Raised when circular linking is detected."""


class InvalidNamingSeriesError(ValidationError):
	"""Raised when an invalid naming series is specified."""


class InvalidUUIDValue(ValidationError):
	"""Raised when an invalid UUID value is specified."""


class DeleteFolderError(FrappeException):
	"""Raised when a folder cannot be deleted."""


class UnsupportedFeatureError(FrappeException):
	"""Raised when an unsupported feature is used."""


class IncompatibleApp(FrappeException):
	"""Raised when an app is incompatible with the current framework version."""


class ServerScriptNotEnabled(FrappeException):
	"""Raised when server scripts are not enabled."""


class IllegalMigrationError(FrappeException):
	"""Raised when an illegal migration is attempted."""


# ---------------------------------------------------------------------------
# HTTP / API
# ---------------------------------------------------------------------------

class HTTPError(FrappeException):
	"""Raised for HTTP-related errors."""


class RateLimitExceededError(FrappeException):
	"""Raised when an API rate limit is exceeded."""


class InvalidKeyError(FrappeException):
	"""Raised when an API key is invalid."""


# ---------------------------------------------------------------------------
# Background Jobs
# ---------------------------------------------------------------------------

class RetryBackgroundJobError(FrappeException):
	"""Signal that a background job should be retried."""


class OutgoingEmailError(FrappeException):
	"""Raised when sending an email fails."""


# ---------------------------------------------------------------------------
# Common aliases used in ERPNext
# ---------------------------------------------------------------------------

ImproperDBConfigurationError = OperationalError


class QueryDeadlockError(DatabaseError):
	"""Raised when a deadlock is detected."""


class QueryTimeoutError(DatabaseError):
	"""Raised when a query exceeds its timeout."""


# ---------------------------------------------------------------------------
# Mapping from Python DB-API exception names → Frappe exceptions
# ---------------------------------------------------------------------------

DBAPI_EXCEPTION_MAP = {
	"IntegrityError": IntegrityError,
	"OperationalError": OperationalError,
	"ProgrammingError": SQLError,
	"DataError": DataError,
	"NotSupportedError": NotSupportedError,
	"InterfaceError": InterfaceError,
	"DatabaseError": DatabaseError,
}
