"""Detect when the user asks for a specific output format in plain language."""
import re
from typing import Optional

_PATTERNS = [
    ("docx", re.compile(r"\b(?:docx|word\s+(?:file|doc|document|format)|ms\s*word|in\s+word|as\s+(?:a\s+)?word)\b", re.I)),
    ("pdf", re.compile(r"\bpdf\b", re.I)),
    ("md", re.compile(r"\b(?:markdown|\.md)\b", re.I)),
]


def detect_format(text: str) -> Optional[str]:
    for fmt, pattern in _PATTERNS:
        if pattern.search(text):
            return fmt
    return None
