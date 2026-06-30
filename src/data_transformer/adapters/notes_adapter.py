"""
Notes Adapter.

Reads free-text notes.
Trust score: 0.50
"""
from __future__ import annotations

import re
from pathlib import Path

from data_transformer.adapters.base import SourceAdapter
from data_transformer.schema.canonical import RawRecord, Source

# Basic regexes for notes
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(
    r"(?:\+?1[\s\-.]?)?"
    r"(?:\(?\d{3}\)?[\s\-.]?)?"
    r"\d{3}[\s\-\.]\d{4}"
)

class NotesAdapter(SourceAdapter):
    """
    Adapter for free-text notes.
    """

    TRUST_SCORE = 0.50

    def can_handle(self, source: Source) -> bool:
        if source.type == "notes":
            return True
        if source.path and source.path.endswith(".txt"):
            return True
        return False

    def get_trust_score(self) -> float:
        return self.TRUST_SCORE

    def extract(self, source: Source) -> RawRecord:
        text = self._load_text(source)
        
        emails = list(set(EMAIL_RE.findall(text)))
        phones = list(set(PHONE_RE.findall(text)))
        
        # Naive name extraction: assume the first line might contain the name if it's short
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        full_name = ""
        if lines and len(lines[0]) < 50 and "@" not in lines[0]:
            full_name = lines[0].replace("Name:", "").strip()

        return RawRecord(
            source="notes",
            source_id=source.path or "",
            fields={
                "full_name": full_name,
                "emails": emails,
                "phones": phones,
            },
        )

    def _load_text(self, source: Source) -> str:
        if source.content is not None and isinstance(source.content, str):
            return source.content
        if source.path:
            return Path(source.path).read_text(encoding="utf-8")
        raise ValueError("NotesAdapter: no content or path provided")
