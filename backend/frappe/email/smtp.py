"""
Frappe SMTP Backend

Provides ``SMTPConnection`` — the actual SMTP transport layer used by
:py:mod:`frappe.email` to deliver messages.  Supports both plain SMTP
and SMTP-over-SSL (SMTPS), STARTTLS, and SMTP authentication.

Configuration is read from the site config (``conf``)::

    mail_server      – SMTP host (default: "localhost")
    mail_port        – SMTP port (default: 25)
    mail_login       – Username for SMTP AUTH
    mail_password    – Password for SMTP AUTH
    use_ssl          – Use SMTPS wrapper (port 465)
    use_tls          – Use STARTTLS upgrade (port 587)

If no SMTP server is configured, the backend gracefully falls back to
logging the message instead of raising an error (safe for development).

Typical usage::

    from frappe.email.smtp import SMTPConnection

    conn = SMTPConnection()
    conn.send_message(
        sender="noreply@example.com",
        recipients=["user@example.com"],
        subject="Hello",
        message="<h1>Hello</h1>",
    )
"""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
import socket
import ssl
from base64 import b64encode
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from typing import Any, Optional, Union

import frappe
from frappe.utils import cint, cstr, strip_html

logger = logging.getLogger("frappe.email.smtp")

# ─── Module-level exports ───────────────────────────────────────────────────

__all__ = [
    "SMTPConnection",
    "get_smtp_server",
    "check_email_format",
    "get_port",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  SMTP CONNECTION
# ═══════════════════════════════════════════════════════════════════════════════


class SMTPConnection:
    """A context-manager-compatible SMTP session for sending email.

    Reads server configuration from ``frappe.conf`` and supports both
    authenticated and unauthenticated SMTP.  When no server is configured
    the message is logged instead of sent (development-safe).
    """

    def __init__(
        self,
        server: Optional[str] = None,
        port: Optional[int] = None,
        login: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: Optional[bool] = None,
        use_tls: Optional[bool] = None,
        timeout: int = 30,
    ):
        """Create an SMTP connection.

        All parameters fall back to values from ``frappe.conf`` when not
        provided explicitly.
        """
        conf = getattr(frappe, "conf", {})

        self.server: str = server or conf.get("mail_server", "localhost")
        self.port: int = port or cint(conf.get("mail_port", 0))
        self.login: Optional[str] = login or conf.get("mail_login")
        self.password: Optional[str] = password or conf.get("mail_password")
        self.use_ssl: bool = use_ssl if use_ssl is not None else cint(conf.get("use_ssl", 0))
        self.use_tls: bool = use_tls if use_tls is not None else cint(conf.get("use_tls", 0))
        self.timeout: int = timeout

        # Derive port if not set
        if not self.port:
            self.port = 465 if self.use_ssl else 587 if self.use_tls else 25

        self._session: Optional[smtplib.SMTP] = None

    # ── Context manager ──

    def __enter__(self) -> "SMTPConnection":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.quit()

    # ── Connection lifecycle ──

    def connect(self) -> "SMTPConnection":
        """Open the SMTP connection, upgrading via TLS if configured."""
        # Skip connection if in development mode without a real server
        if self._is_dummy_mode():
            logger.debug("SMTP in dummy mode – no real connection established")
            return self

        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                self._session = smtplib.SMTP_SSL(
                    self.server, self.port, timeout=self.timeout, context=context
                )
            else:
                self._session = smtplib.SMTP(self.server, self.port, timeout=self.timeout)
                if self.use_tls:
                    context = ssl.create_default_context()
                    self._session.starttls(context=context)

            # Authenticate if credentials provided
            if self.login and self.password:
                self._session.login(self.login, self.password)

            logger.debug("SMTP connected to %s:%s", self.server, self.port)
        except (smtplib.SMTPException, socket.error, OSError) as exc:
            logger.error("SMTP connection failed: %s", exc)
            self._session = None
            raise OutgoingEmailError(f"SMTP connection failed: {exc}") from exc

        return self

    def quit(self) -> None:
        """Close the SMTP connection gracefully."""
        if self._session:
            try:
                self._session.quit()
            except Exception:
                pass
            finally:
                self._session = None

    # ── Message sending ──

    def send_message(
        self,
        sender: str,
        recipients: list[str],
        subject: str,
        message: str,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[list[dict]] = None,
        reply_to: Optional[str] = None,
        read_receipt: bool = False,
        text_content: Optional[str] = None,
    ) -> None:
        """Build a MIME message and deliver it via SMTP.

        Parameters
        ----------
        sender :
            From address (email string).
        recipients :
            Primary recipient addresses.
        subject :
            Subject line.
        message :
            HTML body content.
        cc :
            Carbon-copy addresses.
        bcc :
            Blind carbon-copy addresses (not visible to other recipients).
        attachments :
            List of ``{"fname": str, "fcontent": bytes}`` dicts.
        reply_to :
            Reply-To header address.
        read_receipt :
            Add ``Disposition-Notification-To`` header.
        text_content :
            Explicit plain-text body.  Auto-generated from *message* if omitted.
        """
        if not recipients and not (cc or bcc):
            raise OutgoingEmailError("No recipients provided")

        # Build MIME message
        msg = self._build_mime_message(
            sender=sender,
            recipients=recipients,
            subject=subject,
            html_body=message,
            text_body=text_content,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            reply_to=reply_to,
            read_receipt=read_receipt,
        )

        # Determine envelope recipients (includes BCC)
        envelope_to = list(recipients)
        if cc:
            envelope_to.extend(cc)
        if bcc:
            envelope_to.extend(bcc)

        if self._is_dummy_mode():
            # Development mode: log instead of sending
            logger.info(
                "[DUMMY SMTP] From: %s  To: %s  Subject: %s",
                sender,
                ", ".join(envelope_to),
                subject,
            )
            return

        if not self._session:
            self.connect()

        try:
            self._session.sendmail(sender, envelope_to, msg.as_string())  # type: ignore[union-attr]
            logger.debug(
                "Email sent: %s -> %s  Subject: %s",
                sender,
                ", ".join(envelope_to),
                subject,
            )
        except smtplib.SMTPException as exc:
            logger.error("SMTP sendmail failed: %s", exc)
            raise OutgoingEmailError(f"SMTP send failed: {exc}") from exc

    # ── MIME message builder ──

    def _build_mime_message(
        self,
        sender: str,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: Optional[str],
        cc: Optional[list[str]],
        bcc: Optional[list[str]],
        attachments: Optional[list[dict]],
        reply_to: Optional[str],
        read_receipt: bool,
    ) -> MIMEMultipart:
        """Assemble a multipart MIME email message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Date"] = formatdate(localtime=True)
        msg["Message-Id"] = make_msgid(domain=self._get_domain())

        if cc:
            msg["Cc"] = ", ".join(cc)

        if reply_to:
            msg["Reply-To"] = reply_to

        if read_receipt:
            msg["Disposition-Notification-To"] = sender

        # Plain text part
        if text_body is None:
            text_body = strip_html(html_body) if html_body else ""

        msg.attach(MIMEText(text_body, "plain", "utf-8"))

        # HTML part
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Attachments
        if attachments:
            for att in attachments:
                fname = att.get("fname", "attachment")
                fcontent = att.get("fcontent", b"")
                self._attach_file(msg, fname, fcontent)

        return msg

    @staticmethod
    def _attach_file(msg: MIMEMultipart, filename: str, content: bytes) -> None:
        """Attach a binary file to the MIME message."""
        maintype, subtype = _guess_mime_type(filename)

        part = MIMEBase(maintype, subtype)
        part.set_payload(content)
        encoders.encode_base64(part)

        # RFC 5987 encoding for non-ASCII filenames
        try:
            filename.encode("ascii")
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{filename}"',
            )
        except UnicodeEncodeError:
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=("utf-8", "", filename),
            )

        msg.attach(part)

    # ── Internal helpers ──

    def _is_dummy_mode(self) -> bool:
        """Return True when we should log rather than actually send.

        Dummy mode is active when:
        1. Emails are explicitly muted in the site config.
        2. The server is localhost and no login is configured (dev default).
        3. Frappe is running in test mode.
        """
        if getattr(frappe, "in_test", False):
            return True

        if cint(frappe.conf.get("mute_emails", 0)):
            return True

        if self.server in ("localhost", "127.0.0.1", "") and not self.login:
            return True

        return False

    @staticmethod
    def _get_domain() -> str:
        """Return the site's domain for Message-ID generation."""
        try:
            url = frappe.utils.get_url()
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.hostname or "localhost"
        except Exception:
            return "localhost"


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE-LEVEL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def get_smtp_server(
    server: Optional[str] = None,
    port: Optional[int] = None,
    login: Optional[str] = None,
    password: Optional[str] = None,
) -> SMTPConnection:
    """Factory: create and return an :class:`SMTPConnection` instance.

    The returned object is **not** yet connected; call ``.connect()`` or
    use it as a context manager.
    """
    return SMTPConnection(
        server=server, port=port, login=login, password=password
    )


def check_email_format(email_string: str) -> bool:
    """Validate that *email_string* contains at least one well-formed email.

    Returns ``True`` if any address in the (comma-separated) string passes
    validation.
    """
    if not email_string:
        return False
    addresses = [a.strip() for a in email_string.split(",") if a.strip()]
    if not addresses:
        return False
    for addr in addresses:
        if frappe.utils.validate_email_address(addr):
            return True
    return False


def get_port(conf: Optional[dict] = None) -> int:
    """Return the SMTP port based on site configuration.

    Priority: explicit port > SSL port (465) > TLS port (587) > default (25).
    """
    if conf is None:
        conf = getattr(frappe, "conf", {})

    explicit = cint(conf.get("mail_port"))
    if explicit:
        return explicit
    if cint(conf.get("use_ssl")):
        return 465
    if cint(conf.get("use_tls")):
        return 587
    return 25


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERNAL UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════


def _guess_mime_type(filename: str) -> tuple[str, str]:
    """Return (maintype, subtype) for a filename.

    Falls back to ``application/octet-stream`` when the type cannot be
    determined.
    """
    ctype, _ = mimetypes.guess_type(filename)
    if ctype:
        maintype, _, subtype = ctype.partition("/")
        return maintype, subtype
    return "application", "octet-stream"


# OutgoingEmailError is defined in frappe.exceptions
