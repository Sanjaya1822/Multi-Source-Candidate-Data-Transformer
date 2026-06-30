"""
Recruiter Notes Adapter.

Reads free-text recruiter notes (.txt files or raw text strings).
Applies regex extraction for emails, phones, skills hints, and location.

Trust score: 0.60 — unstructured, subjective text.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from data_transformer.adapters.base import SourceAdapter
from data_transformer.schema.canonical import RawRecord, Source

# ─── Regex patterns ──────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(
    r"(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)?\d{3}[\s\-\.]\d{4}"
)
LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[\w\-]+/?", re.I)
GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/[\w\-]+/?", re.I)

# Skills hint: lines like "Skills: Python, React" or "Tech Stack: ..."
SKILLS_SECTION_RE = re.compile(
    r"(?:skills?|tech(?:nical)?\s+stack|technologies|tools?)\s*[:\-]\s*(.+)",
    re.I
)
# Location hint: "Location: San Francisco, CA" or "Based in New York"
LOCATION_RE = re.compile(
    r"(?:location|based\s+in|located\s+in|city)\s*[:\-]?\s*([A-Za-z ,]+)",
    re.I
)
# Name hint: "Candidate: John Doe" or "Name: John Doe"
NAME_RE = re.compile(r"(?:candidate|name)\s*[:\-]\s*(.+)", re.I)


class NotesAdapter(SourceAdapter):
    """
    Adapter for free-text recruiter notes (.txt files or string content).

    Extraction is best-effort: emails and phones via regex, skills via
    keyword section detection, location and name via hint patterns.
    All extracted values carry lower confidence than structured sources.
    """

    TRUST_SCORE = 0.60

    def can_handle(self, source: Source) -> bool:
        if source.type == "notes":
            return True
        if source.path and source.path.lower().endswith(".txt"):
            return True
        return False

    def get_trust_score(self) -> float:
        return self.TRUST_SCORE

    def extract(self, source: Source) -> RawRecord:
        text = self._load_text(source)

        emails = sorted(set(EMAIL_RE.findall(text)))
        phones = sorted(set(PHONE_RE.findall(text)))

        # LinkedIn / GitHub links
        links: list[dict] = []
        for u in sorted(set(LINKEDIN_RE.findall(text))):
            links.append({"url": u, "type": "linkedin"})
        for u in sorted(set(GITHUB_RE.findall(text))):
            links.append({"url": u, "type": "github"})

        # Name extraction: try explicit label, then first short non-email line
        full_name = ""
        name_match = NAME_RE.search(text)
        if name_match:
            full_name = name_match.group(1).strip()
        if not full_name:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for line in lines:
                if len(line) < 50 and "@" not in line and "http" not in line:
                    full_name = line.replace("Name:", "").replace("Candidate:", "").strip()
                    break

        # Skills from explicit section
        skills: list[str] = []
        skills_match = SKILLS_SECTION_RE.search(text)
        if skills_match:
            raw = skills_match.group(1)
            skills = [s.strip() for s in re.split(r"[,;|]", raw) if s.strip()]

        # Location
        location = ""
        loc_match = LOCATION_RE.search(text)
        if loc_match:
            location = loc_match.group(1).strip().rstrip(",").strip()

        extracted_count = sum(1 for v in [full_name, emails, phones, skills, location] if v)

        return RawRecord(
            source="notes",
            source_id=source.path or "notes_input",
            ingested_at=datetime.utcnow().isoformat() + "Z",
            fields={
                "full_name": full_name,
                "emails": emails,
                "phones": phones,
                "location": location,
                "headline": "",
                "links": links,
                "skills": skills,
                "experience": [],
                "education": [],
            },
            extraction_stats={
                "text_length": len(text),
                "fields_extracted": extracted_count,
                "extraction_method": "regex",
            },
        )

    def _load_text(self, source: Source) -> str:
        if source.content is not None and isinstance(source.content, str):
            return source.content
        if source.path:
            return Path(source.path).read_text(encoding="utf-8")
        raise ValueError("NotesAdapter: no content or path provided")
