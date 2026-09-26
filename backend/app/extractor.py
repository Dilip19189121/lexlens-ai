"""
extractor.py — PDF text extraction for the LexLens AI backend.

Wraps pdfplumber so the rest of the app never touches PDF internals:
`extract_text_from_pdf()` takes raw uploaded bytes and returns plain text.
"""

import io
from typing import Tuple

import pdfplumber

from .config import MAX_UPLOAD_BYTES


class PdfExtractionError(Exception):
    """Raised when a PDF can't be read (corrupt file, encrypted, empty, etc.)."""


def validate_pdf(data: bytes, filename: str) -> None:
    """Sanity-check the upload before we spend any time parsing it.

    Rejects empty files, non-PDF extensions, and anything over the size cap
    (10 MB — plenty for a contract, small enough for the free tier).
    Raises PdfExtractionError with a user-friendly message.
    """
    if not data:
        raise PdfExtractionError("The uploaded file is empty.")
    if filename and not filename.lower().endswith(".pdf"):
        raise PdfExtractionError("Only .pdf files are accepted.")
    if len(data) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise PdfExtractionError(f"File too large — the limit is {mb} MB.")


def extract_text_from_pdf(data: bytes) -> Tuple[str, int]:
    """Extract plain text from raw PDF bytes.

    Returns:
        (text, page_count) — the concatenated page text (pages separated by
        newlines, and an empty string is never returned silently).

    Raises:
        PdfExtractionError: on encrypted, corrupt, or text-empty PDFs.
    """
    pages_text = []
    try:
        # pdfplumber accepts a path or a file-like object — raw bytes must be
        # wrapped in BytesIO first (bytes have no .seek, which pdfminer needs).
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pages_text.append(page_text.strip())
    except Exception as exc:  # pdfplumber raises assorted internal types
        raise PdfExtractionError(
            "Could not read the PDF — it may be corrupt or password-protected."
        ) from exc

    text = "\n".join(p for p in pages_text if p)
    if not text.strip():
        raise PdfExtractionError(
            "No selectable text found in the PDF — it looks like a scan. "
            "OCR support isn't available yet; try a text-based PDF."
        )
    return text, page_count
