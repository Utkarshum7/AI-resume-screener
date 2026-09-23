"""Deterministic PDF extraction: text + hyperlink annotations.

Critical design decision (confirmed by inspecting the actual 50-resume
dataset): ~24/50 resumes only expose their GitHub profile as a clickable
PDF link annotation, with the visible text being just the word "GitHub".
Regexing extracted text alone would silently miss half the GitHub profiles.
So this module returns both the plain text AND the raw URI list from
/Annots -> /A -> /URI, and callers combine both sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pdfplumber
import pypdf


@dataclass
class PdfExtractionResult:
    ok: bool
    text: str = ""
    pages: int = 0
    hyperlinks: list[str] = field(default_factory=list)
    error: str | None = None


def extract_pdf(path: str) -> PdfExtractionResult:
    """Extract text and hyperlink annotations from a single PDF.

    Never raises: any failure is captured in the result's `ok`/`error` fields
    so a single bad file cannot crash the batch.
    """
    text = ""
    pages = 0
    try:
        with pdfplumber.open(path) as pdf:
            pages = len(pdf.pages)
            parts = []
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
            text = "\n".join(parts)
    except Exception as e:  # noqa: BLE001 - deliberately broad, isolate per-file
        return PdfExtractionResult(ok=False, error=f"text_extraction_failed: {e}")

    hyperlinks: list[str] = []
    try:
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            for a in annots:
                try:
                    obj = a.get_object()
                    action = obj.get("/A")
                    if action and "/URI" in action:
                        uri = str(action["/URI"])
                        if uri:
                            hyperlinks.append(uri)
                except Exception:  # noqa: BLE001 - a single bad annotation shouldn't fail the file
                    continue
    except Exception as e:  # noqa: BLE001
        # Hyperlink extraction failing is not fatal — we still have text.
        return PdfExtractionResult(ok=True, text=text, pages=pages, hyperlinks=[],
                                    error=f"hyperlink_extraction_failed: {e}")

    if not text.strip():
        return PdfExtractionResult(ok=False, pages=pages, error="empty_text_extraction")

    return PdfExtractionResult(ok=True, text=text, pages=pages, hyperlinks=hyperlinks)
