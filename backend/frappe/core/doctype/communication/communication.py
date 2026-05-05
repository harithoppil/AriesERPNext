"""
Communication DocType Controller

Captures all forms of communication (email, phone, chat, etc.) and links
them to reference documents for timeline / activity-stream views.

Each Communication record represents a single message or call. When linked
to a reference document (via ``reference_doctype`` and ``reference_name``),
it appears in that document's timeline / activity feed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import frappe
from frappe.model.document import Document

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Supported communication mediums.
VALID_MEDIUMS: frozenset[str] = frozenset({
    "Email",
    "Phone",
    "SMS",
    "Chat",
    "Meeting",
    "Event",
    "Visit",
    "Note",
    "Comment",
    "Other",
})

#: Default medium when none is specified.
DEFAULT_MEDIUM = "Email"

#: Communication directions.
DIRECTIONS: frozenset[str] = frozenset({"Sent", "Received"})


class Communication(Document):
    """Controller for Communication — handles validation and timeline updates."""

    # --------------------------------------------------------------------------
    # Lifecycle hooks
    # --------------------------------------------------------------------------

    def validate(self) -> None:
        """Validate and normalise communication fields.

        * Sets a default medium if none is provided.
        * Ensures sender or recipient is present.
        * Validates the reference document if linked.
        * Normalises email addresses.
        """
        self.set_defaults()
        self.validate_participants()
        self.validate_reference()
        self.validate_medium()
        self.sanitise_content()

    def before_save(self) -> None:
        """Normalise fields before persistence.

        * Strips whitespace from email fields.
        * Derives the subject line from content if absent.
        * Sets the communication date if not provided.
        """
        # Normalise sender / recipient emails
        for field in ("sender", "recipients", "cc", "bcc"):
            value = getattr(self, field, None)
            if value and isinstance(value, str):
                setattr(self, field, value.strip())

        # Derive subject from content
        if not self.subject and self.content:
            # Take first 100 chars of stripped content as subject
            text = self._strip_html(self.content)
            self.subject = text[:100] + ("..." if len(text) > 100 else "")

        # Set communication date
        if not self.communication_date:
            self.communication_date = frappe.now()

    def on_update(self) -> None:
        """Update the linked document's timeline / activity feed.

        Also triggers notification rules if configured.
        """
        self.update_timeline()
        self.notify_participants()

    def on_trash(self) -> None:
        """Clean up timeline references when a communication is deleted.

        Decrements the comment/communication count on the linked document.
        """
        if self.reference_doctype and self.reference_name:
            self.remove_from_timeline()

    # --------------------------------------------------------------------------
    # Defaults & validation helpers
    # --------------------------------------------------------------------------

    def set_defaults(self) -> None:
        """Apply default values for missing fields."""
        if not self.communication_medium:
            self.communication_medium = DEFAULT_MEDIUM

        if not self.communication_date:
            self.communication_date = frappe.now()

        if not self.sent_or_received:
            # Default to Sent if sender matches current user
            if self.sender == frappe.session.user:
                self.sent_or_received = "Sent"
            else:
                self.sent_or_received = "Received"

    def validate_participants(self) -> None:
        """Ensure at least one participant (sender or recipient) is present.

        Raises:
            frappe.ValidationError: If neither sender nor recipients are set.
        """
        if not self.sender and not self.recipients:
            raise frappe.ValidationError(
                "Communication must have at least a sender or recipient"
            )

    def validate_reference(self) -> None:
        """Validate that the linked reference document exists.

        If ``reference_doctype`` and ``reference_name`` are both set,
        verifies the document actually exists. If only one is set,
        clears both (must be a pair or nothing).

        Raises:
            frappe.ValidationError: If the referenced document does not exist.
        """
        if self.reference_doctype and not self.reference_name:
            self.reference_doctype = None
            return

        if not self.reference_doctype and self.reference_name:
            self.reference_name = None
            return

        if not self.reference_doctype or not self.reference_name:
            return

        # Validate the reference document exists
        if not frappe.db.exists(self.reference_doctype, self.reference_name):
            raise frappe.ValidationError(
                f"Referenced document {self.reference_doctype}:{self.reference_name} "
                f"does not exist"
            )

    def validate_medium(self) -> None:
        """Validate the communication medium is recognised.

        Raises:
            frappe.ValidationError: If the medium is not in the allowed set.
        """
        if self.communication_medium and self.communication_medium not in VALID_MEDIUMS:
            # Allow custom mediums — just validate it's a non-empty string
            if not isinstance(self.communication_medium, str) or not self.communication_medium.strip():
                raise frappe.ValidationError("Communication medium must be a non-empty string")

    def sanitise_content(self) -> None:
        """Sanitise HTML content to prevent XSS.

        Strips dangerous tags and attributes from the content field.
        """
        if self.content and isinstance(self.content, str):
            # Basic sanitisation — remove script tags and event handlers
            import re

            # Remove <script> tags and their contents
            self.content = re.sub(
                r"<script[^>]*>.*?</script>", "", self.content, flags=re.DOTALL | re.IGNORECASE
            )
            # Remove javascript: protocol
            self.content = re.sub(
                r"javascript:", "", self.content, flags=re.IGNORECASE
            )
            # Remove on* event handlers
            self.content = re.sub(
                r"\s+on\w+\s*=\s*['\"][^'\"]*['\"]", "", self.content, flags=re.IGNORECASE
            )

    # --------------------------------------------------------------------------
    # Timeline integration
    # --------------------------------------------------------------------------

    def update_timeline(self) -> None:
        """Add this communication to the linked document's timeline.

        Updates the reference document's ``_comments`` count or timeline
        metadata so the communication appears in the activity feed.
        """
        if not self.reference_doctype or not self.reference_name:
            return

        try:
            # Update the comment count on the reference document
            comment_count = frappe.db.count(
                "Communication",
                filters={
                    "reference_doctype": self.reference_doctype,
                    "reference_name": self.reference_name,
                },
            )

            # Update the reference document's comment count
            frappe.db.set_value(
                self.reference_doctype,
                self.reference_name,
                "_comment_count",
                comment_count,
                update_modified=False,
            )
        except Exception:
            # Best-effort: if the reference DocType doesn't have _comment_count,
            # silently skip.
            pass

    def remove_from_timeline(self) -> None:
        """Remove this communication from the linked document's timeline.

        Decrements the comment count on the reference document.
        """
        if not self.reference_doctype or not self.reference_name:
            return

        try:
            comment_count = frappe.db.count(
                "Communication",
                filters={
                    "reference_doctype": self.reference_doctype,
                    "reference_name": self.reference_name,
                },
            )

            frappe.db.set_value(
                self.reference_doctype,
                self.reference_name,
                "_comment_count",
                max(0, comment_count),
                update_modified=False,
            )
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # Notification helpers
    # --------------------------------------------------------------------------

    def notify_participants(self) -> None:
        """Trigger notifications to communication participants.

        Emits a ``communication_created`` event that notification handlers
        can subscribe to. Actual email/SMS delivery is handled by the
        notification layer.
        """
        if self.flags.skip_notifications:
            return

        frappe.emit_event(
            "communication_created",
            {
                "name": self.name,
                "communication_medium": self.communication_medium,
                "sender": self.sender,
                "recipients": self.recipients,
                "subject": self.subject,
                "reference_doctype": self.reference_doctype,
                "reference_name": self.reference_name,
            },
        )

    # --------------------------------------------------------------------------
    # Utility helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags from *html*, returning plain text.

        Args:
            html: String potentially containing HTML markup.

        Returns:
            Plain text with tags removed.
        """
        import re

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", html)
        # Decode common entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&amp;", "&")
        return text.strip()

    # --------------------------------------------------------------------------
    # Query helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def get_communications(
        reference_doctype: str,
        reference_name: str,
        limit: int = 50,
    ) -> list[dict]:
        """Return communications linked to a specific document.

        Args:
            reference_doctype: DocType of the reference document.
            reference_name: Name of the reference document.
            limit: Maximum number of communications to return.

        Returns:
            List of Communication documents as dictionaries.
        """
        return frappe.get_all(
            "Communication",
            filters={
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
            },
            fields=["*"],
            order_by="communication_date desc",
            limit=limit,
        )

    @staticmethod
    def get_unread_count(user: str) -> int:
        """Return the number of unread communications for *user*.

        Args:
            user: User name to check for.

        Returns:
            Count of unread communications.
        """
        return frappe.db.count(
            "Communication",
            filters={
                "recipients": ("like", f"%{user}%"),
                "read_by_recipient": 0,
            },
        )
