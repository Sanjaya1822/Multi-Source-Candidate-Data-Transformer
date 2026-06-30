"""
ATS (Applicant Tracking System) Adapter.

Reads structured JSON from ATS systems (Greenhouse, Lever, etc.).
Trust score: 0.95 — ATS data is the highest-quality structured source.

Production swap-in: Replace load_from_file() with an HTTP client
calling Greenhouse API: GET /v1/candidates/{id}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_transformer.adapters.base import SourceAdapter
from data_transformer.schema.canonical import RawRecord, Source


class ATSAdapter(SourceAdapter):
    """
    Adapter for ATS JSON records.

    Expected JSON structure (Greenhouse-like):
    {
        "id": "ats_001",
        "first_name": "John",
        "last_name": "Doe",
        "email_addresses": [{"value": "john@example.com", "type": "personal"}],
        "phone_numbers": [{"value": "+14155552671", "type": "mobile"}],
        "addresses": [{"value": "San Francisco, CA", "type": "home"}],
        "website_addresses": [{"value": "https://linkedin.com/in/johndoe", "type": "linkedin"}],
        "employments": [...],
        "educations": [...],
        "tags": ["Python", "FastAPI"],
        "updated_at": "2026-06-01T00:00:00Z"
    }
    """

    TRUST_SCORE = 0.95

    def can_handle(self, source: Source) -> bool:
        if source.type == "ats":
            return True
        if source.path and source.path.endswith(".json"):
            return source.type == "ats"
        return False

    def get_trust_score(self) -> float:
        return self.TRUST_SCORE

    def extract(self, source: Source) -> RawRecord:
        data = self._load(source)

        emails = [
            e.get("value", "") if isinstance(e, dict) else str(e)
            for e in data.get("email_addresses", [])
        ]
        phones = [
            p.get("value", "") if isinstance(p, dict) else str(p)
            for p in data.get("phone_numbers", [])
        ]

        # Location
        addresses = data.get("addresses", [])
        location_raw = addresses[0].get("value", "") if addresses else data.get("location", "")

        # Links
        websites = data.get("website_addresses", [])
        links = [
            {"url": w.get("value", ""), "type": w.get("type", "other")}
            if isinstance(w, dict) else {"url": str(w), "type": "other"}
            for w in websites
        ]

        # Experience
        experience = [
            {
                "company": e.get("employer_name", e.get("company", "")),
                "title": e.get("title", ""),
                "start_date": e.get("start_date", ""),
                "end_date": e.get("end_date", ""),
                "is_current": e.get("current", False),
                "description": e.get("description", ""),
            }
            for e in data.get("employments", [])
        ]

        # Education
        education = [
            {
                "institution": e.get("school_name", e.get("institution", "")),
                "degree": e.get("degree", ""),
                "field_of_study": e.get("discipline", e.get("field_of_study", "")),
                "start_date": e.get("start_date", ""),
                "end_date": e.get("end_date", ""),
            }
            for e in data.get("educations", [])
        ]

        # Name
        first = data.get("first_name", "")
        last = data.get("last_name", "")
        full_name = data.get("full_name", f"{first} {last}".strip())

        # Skills from tags
        skills = data.get("tags", data.get("skills", []))

        return RawRecord(
            source="ats",
            source_id=str(data.get("id", "")),
            ingested_at=data.get("updated_at", ""),
            fields={
                "full_name": full_name,
                "emails": emails,
                "phones": phones,
                "location": location_raw,
                "links": links,
                "skills": skills,
                "experience": experience,
                "education": education,
            },
        )

    def _load(self, source: Source) -> dict[str, Any]:
        if source.content is not None:
            if isinstance(source.content, dict):
                return source.content
            return json.loads(source.content)
        if source.path:
            return json.loads(Path(source.path).read_text(encoding="utf-8"))
        raise ValueError("ATSAdapter: no content or path provided")
