"""
Latest Wins strategy.
Chooses the value from the source with the most recent ingestion timestamp.
"""
from typing import List
from dateutil import parser
from .base import ConflictResolver, ResolvedValue, SourceValue


class LatestWinsResolver(ConflictResolver):
    """
    Resolves conflicts by taking the value from the most recently updated source.
    """
    def resolve(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        if not values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[])

        valid_values = [v for v in values if v.value not in (None, "", [], {})]

        if not valid_values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[v.to_provenance() for v in values])

        def parse_date(date_str):
            try:
                return parser.parse(date_str)
            except Exception:
                from datetime import datetime
                return datetime.min

        # Sort by ingested_at descending
        sorted_values = sorted(
            valid_values,
            key=lambda x: parse_date(x.ingested_at),
            reverse=True
        )

        chosen = sorted_values[0]

        return ResolvedValue(
            value=chosen.value,
            confidence=round(chosen.trust_score, 4),
            provenance=[chosen.to_provenance()],
            reasoning=f"Selected most recent value (from {chosen.source} at {chosen.ingested_at})"
        )
