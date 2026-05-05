from __future__ import annotations

import csv
import hashlib
import os
import re
from typing import Any

import frappe


# In-memory cache for translations per language
_translation_cache: dict[str, dict[str, str]] = {}

# Translation priority: user translations override file translations
_user_translation_cache: dict[str, dict[str, str]] = {}


def get_language(lang_list: list[str] | None = None) -> str:
    """Determine language from request headers or user preference.

    Resolution order:
    1. Explicit lang_list parameter
    2. frappe.form_dict._lang
    3. User's language preference from User document
    4. Accept-Language HTTP header
    5. Default system language (en)

    Args:
        lang_list: Optional list of language codes to try in order.

    Returns:
        The resolved language code (e.g., 'en', 'es', 'fr').
    """
    # 1. Explicit lang_list
    if lang_list:
        for lang in lang_list:
            if lang and isinstance(lang, str):
                return lang.strip()

    # 2. Form parameter
    if hasattr(frappe, "form_dict") and frappe.form_dict:
        lang = frappe.form_dict.get("_lang")
        if lang:
            return lang

    # 3. User preference
    if hasattr(frappe, "local") and hasattr(frappe.local, "session"):
        user = frappe.local.session.get("user")
        if user and user not in ("Guest", "Administrator"):
            try:
                user_lang = frappe.db.get_value("User", user, "language")
                if user_lang:
                    return user_lang
            except Exception:
                pass

    # 4. HTTP Accept-Language header
    if hasattr(frappe, "local") and hasattr(frappe.local, "request"):
        request = frappe.local.request
        if request:
            accept_lang = request.headers.get("Accept-Language", "")
            if accept_lang:
                # Parse first language from header: "en-US,en;q=0.9,fr;q=0.8"
                primary = accept_lang.split(",")[0].split(";")[0].strip()
                if primary:
                    # Normalize: "en-US" -> "en"
                    return primary.split("-")[0].lower()

    # 5. System default
    try:
        default_lang = frappe.db.get_default("lang")
        if default_lang:
            return default_lang
    except Exception:
        pass

    return "en"


def get_all_translations(lang: str) -> dict[str, str]:
    """Load all translations for a language from CSV files.

    Loads translations from all app translation directories,
    merging them into a single dictionary. Results are cached.

    Args:
        lang: Language code (e.g., 'en', 'es').

    Returns:
        Dictionary mapping source strings to translated strings.
    """
    if not lang or lang == "en":
        return {}

    # Check in-memory cache first
    if lang in _translation_cache:
        return _translation_cache[lang]

    # Check frappe cache
    cache_key = f"_translations:{lang}"
    cached = frappe.cache_manager.get(cache_key)
    if cached:
        _translation_cache[lang] = cached
        return cached

    translations: dict[str, str] = {}

    # Load from each app's translations directory
    apps = frappe.get_installed_apps() if hasattr(frappe, "get_installed_apps") else []
    if not apps:
        apps = ["frappe"]

    for app in apps:
        translations_dir = os.path.join(
            frappe.get_app_path(app), "translations"
        ) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app, "translations")

        if not os.path.isdir(translations_dir):
            continue

        csv_path = os.path.join(translations_dir, f"{lang}.csv")
        if os.path.isfile(csv_path):
            try:
                app_translations = get_translation_dict_from_file(csv_path, lang, app)
                translations.update(app_translations)
            except Exception:
                pass

    # Override with user translations
    user_trans = get_user_translations(lang)
    translations.update(user_trans)

    # Cache the result
    _translation_cache[lang] = translations
    frappe.cache_manager.set(cache_key, translations)

    return translations


def get_translation_dict_from_file(path: str, lang: str, app: str) -> dict[str, str]:
    """Read translations from a CSV file.

    Parses a translations CSV file with format:
        source_text, translated_text

    Args:
        path: Absolute path to the CSV file.
        lang: Language code.
        app: App name.

    Returns:
        Dictionary mapping source strings to translated strings.
    """
    translations: dict[str, str] = {}

    if not os.path.isfile(path):
        return translations

    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip empty rows and comments
                if not row or len(row) < 2:
                    continue
                source = row[0].strip()
                translated = row[1].strip()
                if source:
                    translations[source] = translated
    except (IOError, csv.Error):
        pass

    return translations


def write_translations_file(
    app: str,
    lang: str,
    translations: dict[str, str],
) -> str:
    """Write translations back to CSV.

    Writes a dictionary of translations to the app's translation CSV file.

    Args:
        app: App name.
        lang: Language code.
        translations: Dictionary of source -> translated mappings.

    Returns:
        Path to the written file.
    """
    translations_dir = os.path.join(
        frappe.get_app_path(app), "translations"
    ) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app, "translations")

    os.makedirs(translations_dir, exist_ok=True)

    csv_path = os.path.join(translations_dir, f"{lang}.csv")

    # Read existing translations to merge
    existing: dict[str, str] = {}
    if os.path.isfile(csv_path):
        existing = get_translation_dict_from_file(csv_path, lang, app)

    # Merge and write
    existing.update(translations)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for source, translated in sorted(existing.items()):
            writer.writerow([source, translated])

    return csv_path


def create_translation_key(
    source_text: str,
    translated_text: str,
    lang: str,
) -> dict:
    """Create a translation record.

    Creates a Translation DocType document to store a user-defined translation.

    Args:
        source_text: The original text.
        translated_text: The translated text.
        lang: Language code.

    Returns:
        The created Translation document as a dict.
    """
    doc = frappe.get_doc(
        {
            "doctype": "Translation",
            "source_text": source_text,
            "translated_text": translated_text,
            "language": lang,
        }
    )
    doc.insert(ignore_permissions=True)

    # Invalidate cache
    clear_translation_cache(lang)

    return doc.as_dict()


def get_user_translations(lang: str) -> dict[str, str]:
    """Get translations created by users (from Translation DocType).

    Queries the Translation DocType for user-defined translations
    that override file-based translations.

    Args:
        lang: Language code.

    Returns:
        Dictionary mapping source strings to translated strings.
    """
    if not lang or lang == "en":
        return {}

    # Check cache
    cache_key = f"_user_translations:{lang}"
    cached = frappe.cache_manager.get(cache_key)
    if cached:
        return cached

    translations: dict[str, str] = {}

    try:
        results = frappe.db.get_all(
            "Translation",
            filters={"language": lang, "docstatus": ("<", 2)},
            fields=["source_text", "translated_text"],
            limit=10000,
        )
        for r in results:
            if r.source_text:
                translations[r.source_text] = r.translated_text or ""
    except Exception:
        # Translation DocType may not exist
        pass

    frappe.cache_manager.set(cache_key, translations)
    return translations


def load_language(lang: str) -> dict[str, str]:
    """Pre-load language into cache.

    Ensures translations for the given language are loaded and cached.

    Args:
        lang: Language code.

    Returns:
        The loaded translation dictionary.
    """
    return get_all_translations(lang)


def get_lang_dict() -> dict[str, str]:
    """Get current language's translation dict.

    Returns translations for the currently active language context.

    Returns:
        Translation dictionary for the current language.
    """
    lang = get_language()
    if not hasattr(frappe.local, "lang_dict"):
        frappe.local.lang_dict = get_all_translations(lang)
    return frappe.local.lang_dict


def get_translated_doctypes() -> list[str]:
    """Get list of DocTypes that have translations.

    Returns DocTypes that are known to have translation data available.

    Returns:
        List of DocType names.
    """
    return [
        "DocType",
        "Print Format",
        "Report",
        "Role",
        "Workflow State",
        "Workflow Action",
        "Country",
        "Currency",
        "Time Zone",
    ]


def translate_values(
    values: list[list],
    fields: list[str],
    doctype: str,
) -> list[list]:
    """Translate values in a result set.

    Translates select field values in a query result set based on
    the DocType's field options.

    Args:
        values: List of row values from a query.
        fields: List of field names corresponding to values.
        doctype: The DocType for metadata lookup.

    Returns:
        Values with translated select options.
    """
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return values

    # Build map of fieldname -> options for Select fields
    select_fields: dict[str, list[str]] = {}
    for field in (meta.fields if hasattr(meta, "fields") else []):
        if getattr(field, "fieldtype", None) == "Select" and getattr(field, "options", None):
            select_fields[getattr(field, "fieldname", "")] = field.options.split("\n")

    if not select_fields:
        return values

    # Get translations
    lang = get_language()
    translations = get_all_translations(lang)

    # Find indices of translatable fields
    field_indices: dict[int, str] = {}
    for i, f in enumerate(fields):
        if f in select_fields:
            field_indices[i] = f

    if not field_indices:
        return values

    # Translate values
    translated = []
    for row in values:
        new_row = list(row)
        for idx, fieldname in field_indices.items():
            if idx < len(new_row) and new_row[idx]:
                source = str(new_row[idx])
                new_row[idx] = translations.get(source, source)
        translated.append(new_row)

    return translated


def get_messages_for_app(app: str) -> list[dict]:
    """Extract all translatable strings from an app.

    Scans Python and template files for _(...) translation calls
    and returns the found messages.

    Args:
        app: App name to scan.

    Returns:
        List of dicts with 'source' and 'context' keys.
    """
    messages: list[dict] = []
    seen: set[str] = set()

    app_path = frappe.get_app_path(app) if hasattr(frappe, "get_app_path") else os.path.join("apps", app, app)
    if not os.path.isdir(app_path):
        return messages

    for root, _dirs, files in os.walk(app_path):
        # Skip hidden and special directories
        if any(part.startswith(".") or part in ("node_modules", "__pycache__") for part in root.split(os.sep)):
            continue

        for fname in files:
            if not fname.endswith((".py", ".html", ".js", ".md")):
                continue

            fpath = os.path.join(root, fname)
            try:
                file_messages = get_messages_from_file(fpath)
                for msg in file_messages:
                    key = msg.get("source", "")
                    if key and key not in seen:
                        seen.add(key)
                        messages.append(msg)
            except Exception:
                pass

    return messages


def get_messages_from_doctype(doctype: str) -> list[dict]:
    """Extract translatable strings from a DocType.

    Collects translatable strings from a DocType's metadata including
    field labels, descriptions, and options.

    Args:
        doctype: The DocType to extract messages from.

    Returns:
        List of dicts with 'source' and 'context' keys.
    """
    messages: list[dict] = []

    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return messages

    # DocType name
    messages.append({"source": doctype, "context": f"DocType: {doctype}"})

    # Field labels and descriptions
    for field in (meta.fields if hasattr(meta, "fields") else []):
        label = getattr(field, "label", None)
        if label:
            messages.append({"source": label, "context": f"{doctype}: {getattr(field, 'fieldname', '')}"})

        desc = getattr(field, "description", None)
        if desc:
            messages.append({"source": desc, "context": f"{doctype}: {getattr(field, 'fieldname', '')}"})

        # Select options
        if getattr(field, "fieldtype", None) == "Select":
            options = getattr(field, "options", "")
            for opt in (options or "").split("\n"):
                if opt:
                    messages.append({"source": opt, "context": f"{doctype}: {getattr(field, 'fieldname', '')}"})

    return messages


def get_messages_from_file(path: str) -> list[dict]:
    """Extract _('...') calls from a Python/HTML file.

    Parses a file to find all translatable string markers.

    Args:
        path: Absolute path to the file.

    Returns:
        List of dicts with 'source' and optional 'context' keys.
    """
    messages: list[dict] = []
    seen: set[str] = set()

    if not os.path.isfile(path):
        return messages

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except IOError:
        return messages

    # Match _('...') calls - handle escaped quotes
    # Pattern matches _('string') or __("string") or _(text="string")
    patterns = [
        r"_\(\s*['\"](.+?)['\"]\s*\)",
        r"__\(\s*['\"](.+?)['\"]\s*\)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, content):
            source = match.group(1)
            # Unescape quotes
            source = source.replace("\\'", "'").replace('\\"', '"')
            if source and source not in seen:
                seen.add(source)
                messages.append({"source": source, "context": path})

    # Match {% trans "..." %} in templates
    trans_pattern = r"{%\s*trans\s+['\"](.+?)['\"]\s*%}"
    for match in re.finditer(trans_pattern, content):
        source = match.group(1)
        if source and source not in seen:
            seen.add(source)
            messages.append({"source": source, "context": path})

    # Match {{ _("...") }} in templates
    tmpl_pattern = r"\{\{\s*_\(\s*['\"](.+?)['\"]\s*\)\s*\}\}"
    for match in re.finditer(tmpl_pattern, content):
        source = match.group(1)
        if source and source not in seen:
            seen.add(source)
            messages.append({"source": source, "context": path})

    return messages


def _(msg: str, context: str | None = None) -> str:
    """Translate a message.

    Looks up the current language's translations and returns
    the translated string if available.

    Args:
        msg: The message to translate.
        context: Optional translation context.

    Returns:
        Translated string, or original if no translation found.
    """
    if not msg:
        return msg

    lang = get_language()
    if lang == "en":
        return msg

    translations = get_all_translations(lang)

    # Try context-specific lookup first
    if context:
        ctx_key = f"{msg}:{context}"
        if ctx_key in translations:
            return translations[ctx_key]

    return translations.get(msg, msg)


def clear_translation_cache(lang: str | None = None) -> None:
    """Clear translation cache.

    Removes cached translations, optionally for a specific language.

    Args:
        lang: Specific language to clear, or None for all.
    """
    global _translation_cache, _user_translation_cache

    if lang:
        _translation_cache.pop(lang, None)
        _user_translation_cache.pop(lang, None)
        frappe.cache_manager.delete(f"_translations:{lang}")
        frappe.cache_manager.delete(f"_user_translations:{lang}")
    else:
        _translation_cache.clear()
        _user_translation_cache.clear()
