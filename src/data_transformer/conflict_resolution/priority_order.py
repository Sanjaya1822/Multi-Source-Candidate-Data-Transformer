"""
Priority Order strategy.
Chooses the value from the highest-priority source.
"""
from typing import List
from .base import ConflictResolver, ResolvedValue, SourceValue


class PriorityOrderResolver(ConflictResolver):
    """
    Resolves conflicts based on a predefined source priority list.
    """
    def __init__(self, priority_map: dict[str, int]):
        """
        priority_map: dict mapping source name to integer priority (lower is better)
        e.g., {'ats': 1, 'linkedin': 2, 'resume': 3}
        """
        self.priority_map = priority_map

    def resolve(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        if not values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[])

        # Filter out None/empty values
        valid_values = [v for v in values if v.value not in (None, "", [], {})]

        if not valid_values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[v.to_provenance() for v in values])

        # Sort by priority (lowest integer is highest priority), then by trust score (highest is best)
        sorted_values = sorted(
            valid_values,
            key=lambda x: (self.priority_map.get(x.source, 999), -x.trust_score)
        )

        chosen = sorted_values[0]

        return ResolvedValue(
            value=chosen.value,
            confidence=round(chosen.trust_score, 4),
            provenance=[chosen.to_provenance()],
            reasoning=f"Selected based on source priority ({chosen.source})"
        )
