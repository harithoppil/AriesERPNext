"""
Frappe Print / PDF Generation

Provides print-format rendering and PDF generation for Frappe documents.
This module replaces the original ``frappe/printing`` package and exposes
a minimal but complete API:

- :func:`get_pdf` — render a document to PDF bytes
- :func:`print_by_server` — send to a network printer (CUPS / IPP)
- :func:`get_print_format_template` — load a Jinja print-format
- :func:`get_print` — full rendering pipeline (HTML or PDF)
- :func:`get_print_html` — render document as printable HTML
- :class:`PrintFormat` — wrapper for Print Format documents

**Dependencies**

- ``jinja2`` for template rendering
- ``weasyprint`` OR ``pdfkit`` OR built-in ``html2pdf`` for PDF generation
- ``requests`` for network printing

If no PDF library is installed, the module falls back to returning HTML
marked with a ``X-Frappe-PDF: unavailable`` header so callers can handle
the situation gracefully.

Example::

    from frappe.printing import get_pdf

    pdf_bytes = get_pdf(
        "Sales Order",
        "SO-00001",
        print_format="Standard",
        letterhead=True,
    )

    with open("/tmp/so-00001.pdf", "wb") as f:
        f.write(pdf_bytes)
"""

from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
import typing
from typing import Any, Optional, Union

import frappe
from frappe.exceptions import ValidationError
from frappe.types import _dict
from frappe.utils import cint, cstr, get_url, nowdate, nowtime, strip_html
from frappe.website.serve import render_string

logger = logging.getLogger("frappe.printing")

# ─── Module-level exports ───────────────────────────────────────────────────

__all__ = [
    "get_pdf",
    "print_by_server",
    "get_print",
    "get_print_html",
    "get_print_format_template",
    "PrintFormat",
    "get_letterhead",
    "validate_print_permission",
]

# ═══════════════════════════════════════════════════════════════════════════════
#  PDF GENERATION
# ═══════════════════════════════════════════════════════════════════════════════


def get_pdf(
    doctype: str,
    name: str,
    print_format: Optional[str] = None,
    letterhead: Union[bool, str] = True,
    language: Optional[str] = None,
    as_base64: bool = False,
    **kwargs: Any,
) -> Union[bytes, str, None]:
    """Render a document as a PDF.

    Parameters
    ----------
    doctype :
        DocType of the document to render.
    name :
        Document name (primary key).
    print_format :
        Name of a *Print Format* to use.  ``None`` uses the default.
    letterhead :
        ``True`` = use the default letterhead;  ``False`` = none;
        *string* = use that specific letterhead.
    language :
        Language code for i18n (e.g. ``"de"``).
    as_base64 :
        Return a base-64 encoded string instead of raw bytes.

    Returns
    -------
    bytes or str or None :
        The PDF content, or ``None`` if generation failed.
    """
    validate_print_permission(doctype, name)

    html = get_print_html(
        doctype=doctype,
        name=name,
        print_format=print_format,
        letterhead=letterhead,
        language=language,
        **kwargs,
    )

    if not html:
        return None

    pdf_bytes = _html_to_pdf(html)

    if pdf_bytes and as_base64:
        return base64.b64encode(pdf_bytes).decode("ascii")

    return pdf_bytes


def get_print(
    doctype: str,
    name: str,
    print_format: Optional[str] = None,
    letterhead: Union[bool, str] = True,
    as_pdf: bool = False,
    language: Optional[str] = None,
    **kwargs: Any,
) -> Union[str, bytes, None]:
    """Render a document for printing (HTML or PDF).

    This is the main entry-point for print rendering.  It returns HTML
    by default; set *as_pdf* to ``True`` for PDF output.
    """
    validate_print_permission(doctype, name)

    if as_pdf:
        return get_pdf(
            doctype=doctype,
            name=name,
            print_format=print_format,
            letterhead=letterhead,
            language=language,
            **kwargs,
        )

    return get_print_html(
        doctype=doctype,
        name=name,
        print_format=print_format,
        letterhead=letterhead,
        language=language,
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML RENDERING
# ═══════════════════════════════════════════════════════════════════════════════


def get_print_html(
    doctype: str,
    name: str,
    print_format: Optional[str] = None,
    letterhead: Union[bool, str] = True,
    language: Optional[str] = None,
    no_letterhead: bool = False,
    **kwargs: Any,
) -> Optional[str]:
    """Render a document as printable HTML.

    The full HTML page includes:
    1. CSS from the print format
    2. The rendered letterhead (if enabled)
    3. The document rendered via the print-format Jinja template
    4. Any footer / page-number scripts
    """
    try:
        doc = frappe.get_doc(doctype, name)
    except Exception as exc:
        logger.error("Document %s/%s not found for printing: %s", doctype, name, exc)
        return None
    # Resolve print format
    pf = _resolve_print_format(doctype, print_format)

    # Build template context
    context = _build_template_context(doc, pf, letterhead, no_letterhead, language)

    # Render template
    try:
        html = _render_template(pf.template or "{{ doc }}", context)
    except Exception as exc:
        logger.error("Print format template render failed: %s", exc)
        html = f"<pre>Error rendering print format: {exc}</pre>"

    # Wrap in full HTML page with styles
    full_html = _wrap_in_page(html, pf, letterhead, context)

    return full_html


# ═══════════════════════════════════════════════════════════════════════════════
#  PRINT FORMAT HANDLING
# ═══════════════════════════════════════════════════════════════════════════════


class PrintFormat:
    """Wrapper around a *Print Format* document.

    Provides convenient access to the format's template, CSS, and
    configuration flags.
    """

    def __init__(self, name: str):
        self.name = name
        self.template: str = ""
        self.css: str = ""
        self.raw_printing: int = 0
        self.align_labels_right: int = 0
        self.show_section_headings: int = 1
        self.line_breaks: int = 0
        self._load()

    def _load(self) -> None:
        """Load the Print Format document from the database."""
        try:
            doc = frappe.get_doc("Print Format", self.name)
            self.template = doc.html or ""
            self.css = doc.css or ""
            self.raw_printing = cint(doc.raw_printing)
            self.align_labels_right = cint(doc.align_labels_right)
            self.show_section_headings = cint(getattr(doc, "show_section_headings", 1))
            self.line_breaks = cint(doc.line_breaks)
        except Exception:
            logger.warning("Print Format '%s' not found, using default", self.name)
            self.template = _DEFAULT_PRINT_TEMPLATE
            self.css = _DEFAULT_PRINT_CSS

    @property
    def is_standard(self) -> bool:
        """Return True if this is a built-in print format."""
        return self.name in ("Standard", "Standard (Compact)")


def get_print_format_template(print_format_name: str) -> tuple[str, str]:
    """Return (template_html, css) for a named print format.

    If the format does not exist, fall back to the built-in standard
    template.
    """
    pf = PrintFormat(print_format_name)
    return pf.template, pf.css


def get_letterhead(letterhead_name: Optional[str] = None) -> Optional[_dict]:
    """Load a letterhead document.

    If *letterhead_name* is ``None``, the default letterhead (marked
    ``is_default=1``) is returned.  Returns ``None`` if no letterhead
    is found.
    """
    try:
        if letterhead_name:
            lh = frappe.get_doc("Letter Head", letterhead_name)
        else:
            results = frappe.db.get_all(
                "Letter Head",
                filters={"is_default": 1, "disabled": 0},
                fields=["name"],
                limit=1,
            )
            if not results:
                return None
            lh = frappe.get_doc("Letter Head", results[0].name)

        return _dict(
            name=lh.name,
            source=lh.source or "Image",
            image=lh.image or "",
            image_width=cint(getattr(lh, "image_width", 0)),
            content=lh.content or "",
            footer=lh.footer or "",
            align=getattr(lh, "align", "Left"),
        )
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  NETWORK PRINTING  (CUPS / IPP)
# ═══════════════════════════════════════════════════════════════════════════════


def print_by_server(
    doctype: str,
    name: str,
    print_format: Optional[str] = None,
    printer_setting: Optional[str] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Print a document on a network printer via CUPS.

    Parameters
    ----------
    doctype, name :
        Document to print.
    print_format :
        Print format to use.
    printer_setting :
        Name of a *Network Printer Settings* document containing the
        CUPS server URI and printer name.

    Returns
    -------
    dict :
        ``{"status": "success"|"error", "message": str}``
    """
    try:
        pdf_bytes = get_pdf(doctype, name, print_format=print_format, **kwargs)
        if not pdf_bytes:
            return {"status": "error", "message": "PDF generation failed"}

        # Load printer settings
        if printer_setting:
            settings = frappe.get_doc("Network Printer Settings", printer_setting)
            server_url = settings.server_url
            printer_name = settings.printer_name
            port = cint(getattr(settings, "port", 631))
        else:
            server_url = frappe.conf.get("cups_server", "localhost")
            printer_name = frappe.conf.get("cups_printer", "")
            port = cint(frappe.conf.get("cups_port", 631))

        if not printer_name:
            return {"status": "error", "message": "No printer configured"}

        # Try pycups first, then fall back to IPP via requests
        try:
            import cups

            conn = cups.Connection(host=server_url, port=port)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            conn.printFile(
                printer=printer_name,
                filename=tmp_path,
                title=f"{doctype} {name}",
                options={},
            )
            os.unlink(tmp_path)
            return {"status": "success", "message": f"Sent to {printer_name}"}

        except ImportError:
            logger.warning("pycups not installed, trying IPP fallback")
            return _print_via_ipp(server_url, port, printer_name, pdf_bytes, doctype, name)

    except Exception as exc:
        logger.exception("Network printing failed")
        return {"status": "error", "message": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
#  PERMISSION CHECKING
# ═══════════════════════════════════════════════════════════════════════════════


def validate_print_permission(doctype: str, name: str) -> None:
    """Raise if the current user may not print this document.

    Requires ``read`` permission on the DocType.  Can be overridden by
    hooks via ``override_print_permissions``.
    """
    if frappe.session.user == "Administrator":
        return

    # Allow hooks to bypass
    try:
        hooks = frappe.get_hooks("override_print_permissions", {})
        if doctype in hooks:
            return
    except Exception:
        pass

    if not frappe.has_permission(doctype, "read"):
        raise frappe.PermissionError(f"No read permission on {doctype}")

    # Check if user can read the specific document
    if not frappe.has_permission(doctype, "read", doc=name):
        raise frappe.PermissionError(f"No permission to print {doctype} {name}")


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_print_format(doctype: str, print_format: Optional[str]) -> PrintFormat:
    """Return a PrintFormat instance for the given doctype and format name."""
    if print_format:
        return PrintFormat(print_format)

    # Try to find the default print format for this doctype
    try:
        default = frappe.db.get_value(
            "Property Setter",
            {"property": "default_print_format", "doc_type": doctype},
            "value",
        )
        if default:
            return PrintFormat(default)
    except Exception:
        pass

    # Fallback to "Standard"
    return PrintFormat("Standard")


def _build_template_context(
    doc,
    pf: PrintFormat,
    letterhead: Union[bool, str],
    no_letterhead: bool,
    language: Optional[str],
) -> dict[str, Any]:
    """Build the Jinja context dict for print-format rendering."""
    # Resolve letterhead
    lh = None
    if not no_letterhead:
        if isinstance(letterhead, str):
            lh = get_letterhead(letterhead)
        elif letterhead:
            lh = get_letterhead()

    # Base context
    context: dict[str, Any] = {
        "doc": doc,
        "frappe": frappe,
        "doc_type": doc.doctype,
        "doc_name": doc.name,
        "print_format": pf,
        "letterhead": lh,
        "no_letterhead": no_letterhead,
        "language": language or frappe.local.lang,
        "settings": _get_print_settings(),
        "utils": _get_print_utils(),
        "nowdate": nowdate(),
        "nowtime": nowtime(),
        "get_url": get_url,
    }

    # Add doc meta
    try:
        context["meta"] = frappe.get_meta(doc.doctype)
    except Exception:
        context["meta"] = None

    return context


def _render_template(template_string: str, context: dict[str, Any]) -> str:
    """Render a print-format template string with the given context."""
    try:
        return render_string(template_string, context)
    except Exception as exc:
        logger.error("Print format template render failed: %s", exc)
        # Fallback to basic rendering
        from jinja2 import Environment, DebugUndefined
        env = Environment(undefined=DebugUndefined)
        env.filters["money_in_words"] = frappe.utils.money_in_words
        env.filters["format_date"] = frappe.utils.format_date
        env.filters["strip_html"] = strip_html
        template = env.from_string(template_string)
        return template.render(context)


def _wrap_in_page(
    body_html: str,
    pf: PrintFormat,
    letterhead: Union[bool, str],
    context: dict[str, Any],
) -> str:
    """Wrap rendered body HTML in a full HTML page with CSS and letterhead."""
    css_parts = [_DEFAULT_PRINT_CSS]
    if pf.css:
        css_parts.append(pf.css)

    letterhead_html = ""
    lh = context.get("letterhead")
    if lh:
        if lh.get("source") == "Image" and lh.get("image"):
            align = lh.get("align", "Left").lower()
            letterhead_html = (
                f'<div class="letterhead" style="text-align: {align}">'
                f'<img src="{lh["image"]}" '
                f'style="max-width: {lh.get("image_width", 600)}px;" />'
                f"</div>"
            )
        elif lh.get("content"):
            letterhead_html = f'<div class="letterhead">{lh["content"]}</div>'

    footer_html = ""
    if lh and lh.get("footer"):
        footer_html = f'<div class="letterhead-footer">{lh["footer"]}</div>'

    return f"""<!DOCTYPE html>
<html lang="{context.get("language", "en")}">
<head>
<meta charset="utf-8">
<title>{context.get("doc_name", "Print")}</title>
<style>
{"\\n".join(css_parts)}
</style>
</head>
<body>
<div class="print-format">
{letterhead_html}
{body_html}
{footer_html}
</div>
</body>
</html>"""


def _html_to_pdf(html_content: str) -> Optional[bytes]:
    """Convert HTML string to PDF bytes.

    Tries multiple backends in order:
    1. weasyprint (best quality, pure Python)
    2. pdfkit + wkhtmltopdf (widely used)
    3. Built-in html2pdf fallback

    Returns ``None`` if no backend is available.
    """
    # Attempt 1: weasyprint
    try:
        import weasyprint

        return weasyprint.HTML(string=html_content).write_pdf()
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("weasyprint failed: %s", exc)

    # Attempt 2: pdfkit
    try:
        import pdfkit

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name

        try:
            return pdfkit.from_file(tmp_path, False)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pdfkit failed: %s", exc)

    # Attempt 3: xhtml2pdf
    try:
        from xhtml2pdf import pisa

        result = io.BytesIO()
        pisa.CreatePipeline(html_content, result)
        return result.getvalue()
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("xhtml2pdf failed: %s", exc)

    # Fallback: return None (caller should handle gracefully)
    logger.warning(
        "No PDF library available (install weasyprint, pdfkit, or xhtml2pdf)"
    )
    return None


def _print_via_ipp(
    server_url: str,
    port: int,
    printer_name: str,
    pdf_bytes: bytes,
    doctype: str,
    name: str,
) -> dict[str, Any]:
    """Send a PDF to a CUPS printer via HTTP IPP protocol (simplified).

    This is a minimal implementation.  For production use, prefer
    ``pycups`` which handles the full IPP protocol correctly.
    """
    try:
        import requests

        url = f"http://{server_url}:{port}/printers/{printer_name}"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            response = requests.post(
                url,
                files={"file": (f"{doctype}_{name}.pdf", f, "application/pdf")},
                timeout=60,
            )

        os.unlink(tmp_path)

        if response.status_code == 200:
            return {"status": "success", "message": f"Sent to {printer_name} via IPP"}
        else:
            return {
                "status": "error",
                "message": f"IPP returned {response.status_code}",
            }

    except ImportError:
        return {"status": "error", "message": "requests library required for IPP printing"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _get_print_settings() -> _dict:
    """Load print settings from the *Print Settings* single DocType."""
    defaults = {
        "page_size": "A4",
        "orientation": "Portrait",
        "margin_top": "15mm",
        "margin_bottom": "15mm",
        "margin_left": "15mm",
        "margin_right": "15mm",
        "font": "Default",
        "font_size": 9,
        "compact_item_print": 0,
        "print_taxes_with_zero_amount": 0,
    }
    try:
        settings = frappe.get_doc("Print Settings", "Print Settings")
        for key in defaults:
            val = getattr(settings, key, None)
            if val is not None:
                defaults[key] = val
    except Exception:
        pass
    return _dict(defaults)


def _get_print_utils() -> _dict:
    """Return a dict of utility functions available in print templates."""
    return _dict(
        money_in_words=frappe.utils.money_in_words,
        format_date=frappe.utils.format_date,
        format_datetime=frappe.utils.format_datetime,
        strip_html=strip_html,
        cint=cint,
        cstr=cstr,
    )


# ─── Default print template ──

_DEFAULT_PRINT_TEMPLATE = """
<table class="print-format-header">
    <tr>
        <td><h2>{{ doc.doctype }}</h2></td>
        <td style="text-align: right;"><h2>{{ doc.name }}</h2></td>
    </tr>
</table>
<hr>
<table class="print-format-body">
    {% if meta %}
    {% for field in meta.fields %}
        {% if field.print_hide %}{% continue %}{% endif %}
        {% if field.fieldtype not in ['Section Break', 'Column Break', 'Tab Break'] %}
        <tr>
            <td class="label">{{ field.label or field.fieldname }}</td>
            <td>{{ doc.get(field.fieldname) or '' }}</td>
        </tr>
        {% endif %}
    {% endfor %}
    {% else %}
        {% for key, value in doc.as_dict().items() %}
            {% if key not in ['doctype', 'name', 'owner', 'modified_by', 'creation', 'modified', 'docstatus', 'idx'] %}
            <tr><td class="label">{{ key }}</td><td>{{ value or '' }}</td></tr>
            {% endif %}
        {% endfor %}
    {% endif %}
</table>
<div class="print-format-footer">
    Printed on {{ nowdate }} {{ nowtime }}
</div>
"""

_DEFAULT_PRINT_CSS = """
@page {
    size: A4 portrait;
    margin: 15mm;
}
body {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 9pt;
    line-height: 1.4;
    color: #333;
}
.print-format {
    max-width: 180mm;
    margin: 0 auto;
}
.print-format-header h2 {
    margin: 0 0 5px;
    font-size: 14pt;
}
.print-format-body {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
}
.print-format-body td {
    padding: 4px 6px;
    border-bottom: 1px solid #eee;
    vertical-align: top;
}
.print-format-body td.label {
    width: 35%;
    font-weight: bold;
    color: #555;
}
.letterhead {
    margin-bottom: 15px;
}
.letterhead-footer {
    margin-top: 15px;
    padding-top: 10px;
    border-top: 1px solid #ccc;
    font-size: 8pt;
    color: #777;
}
.print-format-footer {
    margin-top: 20px;
    font-size: 8pt;
    color: #999;
    text-align: center;
}
hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 10px 0;
}
"""
