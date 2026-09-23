"""Text normalization shared by extraction and eligibility.

The dataset contains PDF-generator artifacts that break naive regex matching
if left unhandled: zero-width spaces used as separators between icon-based
contact fields, decorative bullets/arrows, and stray control characters from
missing glyphs. This is intentionally lightweight (no NLP/section
classification) — just enough normalization to make regex matching reliable.
"""
from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = "​‌‍﻿"
_BULLET_LIKE = "•●◦◆→↑↓·"


def normalize_text(text: str) -> str:
    if not text:
        return ""
    for ch in _ZERO_WIDTH:
        text = text.replace(ch, " ")
    for ch in _BULLET_LIKE:
        text = text.replace(ch, " ")
    # Collapse control characters (e.g. missing-glyph artifacts like '\x00')
    text = "".join(c if (c == "\n" or unicodedata.category(c)[0] != "C") else " " for c in text)
    # Collapse runs of whitespace but keep newlines as section-ish separators
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
