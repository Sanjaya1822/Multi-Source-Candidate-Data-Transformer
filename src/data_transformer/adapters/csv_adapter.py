"""
CSV Adapter.

Reads ALL rows from a CSV file, yielding one RawRecord per candidate row.
Trust score: 0.90 (structured recruiter data)
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import List

from data_transformer.adapters.base import SourceAdapter
from data_transformer.schema.canonical import RawRecord, Source


class CSVAdapter(SourceAdapter):
    """
    Adapter for recruiter CSV files.

    Each data row becomes one RawRecord. The adapter returns a list of records
    so the pipeline can process every candidate in the file.

    Supported column names (case-insensitive):
      name / full_name, email, phone, location, skills, linkedin_url,
      github_url, title / headline, company, id
    """

    TRUST_SCORE = 0.90

    def can_handle(self, source: Source) -> bool:
        if source.type == "csv":
            return True
        if source.path and source.path.lower().endswith(".csv"):
            return True
        return False

    def get_trust_score(self) -> float:
        return self.TRUST_SCORE

    def extract(self, source: Source) -> List[RawRecord]:  # type: ignore[override]
        """
        Extract ALL rows from the CSV source.
        Returns a List[RawRecord] — one per data row.
        Empty rows are skipped. Malformed rows are skipped with a warning.
        """
        rows = self._load_rows(source)
        records: List[RawRecord] = []

        for idx, row in enumerate(rows):
            # Normalise keys to lowercase
            row = {k.lower().strip(): v for k, v in row.items() if k}

            try:
                record = self._row_to_record(row, source, row_index=idx)
                records.append(record)
            except Exception:
                # Skip bad rows — robustness requirement
                pass

        return records

    # ─── Private ─────────────────────────────────────────────────────────────

    def _row_to_record(self, row: dict, source: Source, row_index: int) -> RawRecord:
        emails: list[str] = []
        raw_email = row.get("email", row.get("email_address", "")).strip()
        if raw_email:
            emails.append(raw_email)

        phones: list[str] = []
        raw_phone = row.get("phone", row.get("phone_number", "")).strip()
        if raw_phone:
            phones.append(raw_phone)

        skills: list[str] = []
        raw_skills = row.get("skills", row.get("skill_set", "")).strip()
        if raw_skills:
            skills = [s.strip() for s in raw_skills.replace(";", ",").split(",") if s.strip()]

        links: list[dict] = []
        li_url = row.get("linkedin_url", row.get("linkedin", "")).strip()
        gh_url = row.get("github_url", row.get("github", "")).strip()
        if li_url:
            links.append({"url": li_url, "type": "linkedin"})
        if gh_url:
            links.append({"url": gh_url, "type": "github"})

        full_name = row.get("full_name", row.get("name", "")).strip()
        location = row.get("location", row.get("city", "")).strip()
        headline = row.get("headline", row.get("title", row.get("current_title", ""))).strip()
        company = row.get("company", row.get("current_company", "")).strip()

        experience: list[dict] = []
        if company or headline:
            experience.append({
                "company": company,
                "title": headline,
                "is_current": True,
            })

        row_id = row.get("id", row.get("candidate_id", f"csv_row_{row_index}")).strip()

        return RawRecord(
            source="csv",
            source_id=str(row_id) if row_id else f"csv_row_{row_index}",
            ingested_at=datetime.utcnow().isoformat() + "Z",
            fields={
                "full_name": full_name,
                "emails": emails,
                "phones": phones,
                "location": location,
                "headline": headline,
                "links": links,
                "skills": skills,
                "experience": experience,
                "education": [],
            },
            extraction_stats={
                "row_index": row_index,
                "columns_found": list(row.keys()),
                "fields_extracted": sum(1 for v in [full_name, emails, phones, location] if v),
            }
        )

    def _load_rows(self, source: Source) -> list[dict]:
        """Load all rows from the source as a list of dicts."""
        if source.content is not None:
            if isinstance(source.content, list):
                return source.content
            if isinstance(source.content, dict):
                return [source.content]
            if isinstance(source.content, str):
                reader = csv.DictReader(io.StringIO(source.content))
                return list(reader)

        if source.path:
            with open(source.path, mode="r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)

        raise ValueError("CSVAdapter: no content or path provided")
