"""
LinkedIn Adapter.

Reads structured LinkedIn profile JSON (sample data — ToS compliant).
Trust score: 0.90

Production notes: LinkedIn data must be obtained through official
Partnership API or user-authorized OAuth export. This adapter uses
the exported JSON format from LinkedIn's data download feature.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_transformer.adapters.base import SourceAdapter
from data_transformer.schema.canonical import RawRecord, Source


class LinkedInAdapter(SourceAdapter):
    """
    Adapter for LinkedIn profile JSON exports.

    Expected structure (LinkedIn data export format):
    {
        "profile_id": "johndoe",
        "full_name": "John Doe",
        "email": "john@example.com",
        "phone": "+14155552671",
        "headline": "Senior Software Engineer at Google",
        "location": "San Francisco, CA",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "positions": [
            {
                "title": "Senior Software Engineer",
                "company_name": "Google",
                "start_date": {"year": 2020, "month": 1},
                "end_date": null,
                "is_current": true,
                "description": "Led team..."
            }
        ],
        "educations": [...],
        "skills": ["Python", "Go", "Kubernetes"],
        "connections": 500,
        "updated_at": "2026-06-15T00:00:00Z"
    }
    """

    TRUST_SCORE = 0.90

    def can_handle(self, source: Source) -> bool:
        return source.type == "linkedin"

    def get_trust_score(self) -> float:
        return self.TRUST_SCORE

    def extract(self, source: Source) -> RawRecord:
        data = self._load(source)

        # Emails — LinkedIn may have multiple verified emails
        emails_raw = data.get("emails", [])
        if isinstance(emails_raw, str):
            emails_raw = [emails_raw]
        if not emails_raw and data.get("email"):
            emails_raw = [data["email"]]

        # Phones
        phones_raw = data.get("phones", [])
        if isinstance(phones_raw, str):
            phones_raw = [phones_raw]
        if not phones_raw and data.get("phone"):
            phones_raw = [data["phone"]]

        # Location
        location_raw = data.get("location", data.get("geo", {}).get("full", ""))

        # Links
        links = []
        if data.get("linkedin_url"):
            links.append({"url": data["linkedin_url"], "type": "linkedin"})
        if data.get("github_url"):
            links.append({"url": data["github_url"], "type": "github"})
        for url in data.get("websites", []):
            links.append({"url": url if isinstance(url, str) else url.get("url", ""), "type": "other"})

        # Experience
        experience = []
        for pos in data.get("positions", []):
            start = self._format_date(pos.get("start_date"))
            end = self._format_date(pos.get("end_date")) if pos.get("end_date") else None
            experience.append({
                "company": pos.get("company_name", pos.get("company", "")),
                "title": pos.get("title", ""),
                "start_date": start,
                "end_date": end,
                "is_current": pos.get("is_current", end is None),
                "description": pos.get("description", ""),
            })

        # Education
        education = []
        for edu in data.get("educations", []):
            education.append({
                "institution": edu.get("school_name", edu.get("institution", "")),
                "degree": edu.get("degree_name", edu.get("degree", "")),
                "field_of_study": edu.get("field_of_study", ""),
                "start_date": self._format_date(edu.get("start_date")),
                "end_date": self._format_date(edu.get("end_date")),
            })

        return RawRecord(
            source="linkedin",
            source_id=data.get("profile_id", ""),
            ingested_at=data.get("updated_at", ""),
            fields={
                "full_name": data.get("full_name", ""),
                "headline": data.get("headline", ""),
                "emails": emails_raw,
                "phones": phones_raw,
                "location": location_raw,
                "links": links,
                "skills": data.get("skills", []),
                "experience": experience,
                "education": education,
            },
        )

    @staticmethod
    def _format_date(date_obj: Any) -> str | None:
        if not date_obj:
            return None
        if isinstance(date_obj, str):
            return date_obj
        if isinstance(date_obj, dict):
            year = date_obj.get("year", "")
            month = date_obj.get("month", 1)
            if year:
                return f"{year}-{int(month):02d}"
        return None

    def _load(self, source: Source) -> dict[str, Any]:
        if source.content is not None:
            if isinstance(source.content, dict):
                return source.content
            return json.loads(source.content)
        if source.path:
            return json.loads(Path(source.path).read_text(encoding="utf-8"))
        raise ValueError("LinkedInAdapter: no content or path provided")
