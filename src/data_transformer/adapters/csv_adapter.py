"""
CSV Adapter.

Reads CSV files mapping rows to candidate profiles.
Trust score: 0.70
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from data_transformer.adapters.base import SourceAdapter
from data_transformer.schema.canonical import RawRecord, Source


class CSVAdapter(SourceAdapter):
    """
    Adapter for CSV files.
    Assumes first row is header. Maps standard column names to fields.
    """

    TRUST_SCORE = 0.70

    def can_handle(self, source: Source) -> bool:
        if source.type == "csv":
            return True
        if source.path and source.path.endswith(".csv"):
            return True
        return False

    def get_trust_score(self) -> float:
        return self.TRUST_SCORE

    def extract(self, source: Source) -> RawRecord:
        row = self._load_row(source)
        
        # We assume the CSV adapter processes one row at a time.
        # In a real pipeline, a CSV reader would yield multiple Source objects (one per row).
        # For simplicity, we treat the source as a single row.

        emails = []
        if "email" in row and row["email"]:
            emails.append(row["email"])
            
        phones = []
        if "phone" in row and row["phone"]:
            phones.append(row["phone"])
            
        skills = []
        if "skills" in row and row["skills"]:
            skills = [s.strip() for s in row["skills"].split(",") if s.strip()]

        return RawRecord(
            source="csv",
            source_id=row.get("id", ""),
            fields={
                "full_name": row.get("name", row.get("full_name", "")),
                "emails": emails,
                "phones": phones,
                "location": row.get("location", ""),
                "skills": skills,
            },
        )

    def _load_row(self, source: Source) -> dict[str, str]:
        if source.content is not None:
            if isinstance(source.content, dict):
                return source.content
            # If content is string, assume it's a single CSV row with headers? 
            # Or assume the caller handles parsing. Let's assume the caller passes a dict for content.
            pass

        if source.path:
            # For simplicity, just read the first data row.
            with open(source.path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                try:
                    return next(reader)
                except StopIteration:
                    return {}
        
        raise ValueError("CSVAdapter: no content or path provided")
