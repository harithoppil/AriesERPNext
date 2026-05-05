from __future__ import annotations

import base64
import hashlib
import imghdr
import mimetypes
import os
import re
import shutil
from datetime import datetime
from io import BytesIO
from typing import Any
from urllib.parse import unquote

import frappe
from frappe.types import _dict

# Maximum file size: 10MB default
MAX_FILE_SIZE = 10 * 1024 * 1024


class FileManager:
    """Handle file uploads, downloads, and management.

    Provides a centralized interface for file operations including
    uploading, reading, writing, and deleting files within the
    site's public and private directories.
    """

    def __init__(self) -> None:
        self.site_path = frappe.local.site_path

    def upload_file(
        self,
        filedata: bytes | str | None = None,
        filename: str | None = None,
        folder: str | None = None,
        is_private: int = 0,
        doctype: str | None = None,
        docname: str | None = None,
        fieldname: str | None = None,
        file_url: str | None = None,
        content_hash: str | None = None,
    ) -> "frappe.Document":
        """Upload a file from request data.

        Saves the file to disk (sites/{site}/public/files/ or private/files/)
        and creates a File document for tracking.

        Args:
            filedata: Raw file content as bytes, or base64-encoded string.
            filename: Original filename.
            folder: Subfolder path within files directory.
            is_private: 1 for private, 0 for public.
            doctype: Associated DocType.
            docname: Associated document name.
            fieldname: Field that stores this file.
            file_url: Existing file URL to reference.
            content_hash: Pre-calculated content hash.

        Returns:
            The created File document.
        """
        if not filename and file_url:
            filename = os.path.basename(file_url)

        if not filename:
            filename = "untitled"

        # Sanitize filename
        filename = self._sanitize_filename(filename)

        # Decode base64 content if needed
        content = self._decode_filedata(filedata) if filedata else b""

        # Validate file size
        if content:
            self.validate_file_size(content)

        # Calculate content hash
        if not content_hash and content:
            content_hash = self.get_file_hash(content)

        # Check for duplicate by hash
        if content_hash:
            existing = frappe.db.get_value(
                "File",
                {"content_hash": content_hash, "is_private": is_private},
                ["name", "file_url"],
                as_dict=True,
            )
            if existing:
                # Return existing file doc
                return frappe.get_doc("File", existing.name)

        # Determine file path and URL
        if file_url:
            file_path = self.get_file_path(file_url)
        else:
            file_path, file_url = save_file_on_filesystem(
                content, filename, is_private=is_private, folder=folder
            )

        # Create File document
        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": filename,
                "file_url": file_url,
                "file_size": len(content) if content else 0,
                "content_hash": content_hash,
                "is_private": is_private,
                "attached_to_doctype": doctype,
                "attached_to_name": docname,
                "attached_to_field": fieldname,
                "folder": folder or "Home",
            }
        )
        file_doc.insert(ignore_permissions=True)

        return file_doc

    def write_file(
        self,
        content: bytes,
        filename: str,
        folder: str | None = None,
        is_private: int = 0,
    ) -> str:
        """Write file content to disk.

        Args:
            content: Raw file bytes.
            filename: Name of the file.
            folder: Subfolder within files directory.
            is_private: 1 for private storage.

        Returns:
            The file URL path.
        """
        return save_file_on_filesystem(content, filename, is_private=is_private, folder=folder)[1]

    def delete_file(self, file_url: str) -> None:
        """Delete file from disk and database.

        Removes the physical file and any associated File documents.

        Args:
            file_url: The file URL to delete.
        """
        # Find and delete File document(s)
        file_docs = frappe.db.get_all("File", filters={"file_url": file_url}, pluck="name")
        for fid in file_docs:
            frappe.delete_doc("File", fid, ignore_permissions=True, delete_permanently=True)

        # Delete physical file
        file_path = self.get_file_path(file_url)
        if file_path and os.path.isfile(file_path):
            os.remove(file_path)

    def get_file(self, file_url: str) -> tuple[bytes, str, str]:
        """Read file content.

        Args:
            file_url: URL/path of the file.

        Returns:
            Tuple of (content_bytes, file_name, mime_type).
        """
        file_path = self.get_file_path(file_url)
        if not file_path or not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_url}")

        with open(file_path, "rb") as f:
            content = f.read()

        filename = os.path.basename(file_path)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        return content, filename, mime_type

    def get_file_path(self, file_url: str) -> str | None:
        """Resolve file URL to filesystem path.

        Args:
            file_url: URL path like "/files/document.pdf" or "/private/files/doc.pdf".

        Returns:
            Absolute filesystem path, or None if not resolvable.
        """
        if not file_url:
            return None

        file_url = unquote(file_url)

        if file_url.startswith("/private/"):
            path = os.path.join(self.site_path, file_url.lstrip("/"))
        elif file_url.startswith("/files/"):
            path = os.path.join(self.site_path, "public", file_url.lstrip("/"))
        elif file_url.startswith("file://"):
            path = file_url[7:]
        elif file_url.startswith("http://") or file_url.startswith("https://"):
            # External URL - not a local file
            return None
        else:
            # Assume relative path
            path = os.path.join(self.site_path, "public", "files", file_url)

        return path

    @staticmethod
    def extract_images_from_doc(doc: "frappe.Document", fieldname: str) -> list[str]:
        """Extract base64 images from HTML fields and save as files.

        Parses HTML content for base64-encoded images, saves them
        as separate File documents, and updates the HTML with file URLs.

        Args:
            doc: Document containing the HTML field.
            fieldname: Name of the HTML field.

        Returns:
            List of saved file URLs.
        """
        content = doc.get(fieldname) or ""
        if not content:
            return []

        saved_files: list[str] = []
        # Match base64 image data URIs
        pattern = re.compile(
            r'<img[^>]+src=["\']data:image/([^;]+);base64,([^"\']+)["\']',
            re.IGNORECASE,
        )

        def replace_image(match):
            img_format = match.group(1)
            b64_data = match.group(2)
            try:
                img_content = base64.b64decode(b64_data)
                ext = img_format if img_format in ("png", "jpg", "jpeg", "gif", "webp") else "png"
                fname = f"{doc.doctype.lower()}_{doc.name.lower()}_{fieldname}_{hashlib.md5(img_content).hexdigest()[:8]}.{ext}"

                fm = FileManager()
                file_path, file_url = save_file_on_filesystem(
                    img_content, fname, is_private=doc.get("is_private", 0)
                )

                # Create File document
                file_doc = frappe.get_doc(
                    {
                        "doctype": "File",
                        "file_name": fname,
                        "file_url": file_url,
                        "file_size": len(img_content),
                        "is_private": doc.get("is_private", 0),
                        "attached_to_doctype": doc.doctype,
                        "attached_to_name": doc.name,
                        "attached_to_field": fieldname,
                    }
                )
                file_doc.insert(ignore_permissions=True)
                saved_files.append(file_url)

                return f'<img src="{file_url}">'
            except Exception:
                return match.group(0)

        new_content = pattern.sub(replace_image, content)
        if new_content != content:
            doc.set(fieldname, new_content)

        return saved_files

    @staticmethod
    def get_file_hash(content: bytes) -> str:
        """Calculate SHA-256 hash of file content.

        Args:
            content: Raw file bytes.

        Returns:
            Hex-encoded SHA-256 hash string.
        """
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def validate_file_size(content: bytes, max_size: int | None = None) -> None:
        """Check file size against limit.

        Args:
            content: File content bytes.
            max_size: Maximum size in bytes (defaults to 10MB).

        Raises:
            ValueError: If file exceeds size limit.
        """
        limit = max_size or MAX_FILE_SIZE
        if len(content) > limit:
            raise ValueError(
                f"File size ({len(content)} bytes) exceeds maximum allowed ({limit} bytes)"
            )

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize a filename to prevent path traversal.

        Args:
            filename: Original filename.

        Returns:
            Sanitized filename.
        """
        # Remove path traversal
        filename = os.path.basename(filename)
        # Remove null bytes
        filename = filename.replace("\x00", "")
        # Remove control characters
        filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)
        return filename.strip()

    @staticmethod
    def _decode_filedata(filedata: bytes | str | None) -> bytes:
        """Decode file data from various input formats.

        Args:
            filedata: Raw bytes, base64 string, or None.

        Returns:
            Decoded bytes.
        """
        if not filedata:
            return b""

        if isinstance(filedata, bytes):
            return filedata

        if isinstance(filedata, str):
            # Try base64 decode
            try:
                return base64.b64decode(filedata)
            except Exception:
                return filedata.encode("utf-8")

        return b""


def get_files_path(*joins: str, is_private: bool = False) -> str:
    """Get path to files directory.

    Constructs the absolute path to the site's files directory.

    Args:
        *joins: Additional path components to join.
        is_private: Whether to use private files directory.

    Returns:
        Absolute filesystem path.
    """
    path = os.path.join(
        frappe.local.site_path,
        "private" if is_private else "public",
        "files",
        *joins,
    )
    return path


def get_file_path(file_url: str) -> str | None:
    """Resolve file URL to absolute path.

    Args:
        file_url: File URL like "/files/doc.pdf".

    Returns:
        Absolute filesystem path, or None.
    """
    fm = FileManager()
    return fm.get_file_path(file_url)


def save_file_on_filesystem(
    content: bytes,
    filename: str,
    is_private: int = 0,
    folder: str | None = None,
) -> tuple[str, str]:
    """Save file content to filesystem and return metadata.

    Args:
        content: Raw file bytes.
        filename: Name for the file.
        is_private: 1 for private, 0 for public.
        folder: Optional subfolder.

    Returns:
        Tuple of (absolute_path, file_url).
    """
    # Create files directory if it doesn't exist
    files_dir = get_files_path(is_private=bool(is_private))
    os.makedirs(files_dir, exist_ok=True)

    # Handle folder
    if folder:
        folder_path = os.path.join(files_dir, folder)
        os.makedirs(folder_path, exist_ok=True)
        target_dir = folder_path
    else:
        target_dir = files_dir

    # Ensure unique filename
    base, ext = os.path.splitext(filename)
    counter = 1
    final_filename = filename
    while os.path.exists(os.path.join(target_dir, final_filename)):
        final_filename = f"{base}_{counter}{ext}"
        counter += 1

    file_path = os.path.join(target_dir, final_filename)

    # Write file
    with open(file_path, "wb") as f:
        f.write(content)

    # Build file URL
    rel_path = os.path.relpath(file_path, frappe.local.site_path)
    file_url = "/" + rel_path.replace("\\", "/")

    return file_path, file_url


def remove_file(fid: str) -> None:
    """Remove file by ID.

    Deletes the File document and its associated physical file.

    Args:
        fid: Name/ID of the File document.
    """
    try:
        file_doc = frappe.get_doc("File", fid)
        file_url = file_doc.get("file_url")

        # Delete File document
        frappe.delete_doc("File", fid, ignore_permissions=True, delete_permanently=True)

        # Delete physical file if no other File docs reference it
        if file_url:
            other_refs = frappe.db.count("File", filters={"file_url": file_url, "name": ("!=", fid)})
            if other_refs == 0:
                fm = FileManager()
                fpath = fm.get_file_path(file_url)
                if fpath and os.path.isfile(fpath):
                    os.remove(fpath)
    except Exception:
        # File document may not exist
        pass
