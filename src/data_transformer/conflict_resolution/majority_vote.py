"""
Majority Vote strategy.
Chooses the value that appears most frequently across sources.
"""
from typing import Any, List
from collections import Counter
from .base import ConflictResolver, ResolvedValue, SourceValue
from .priority_order import PriorityOrderResolver


def _to_hashable(val: Any) -> Any:
    """Convert a value to a hashable form for counting."""
    if isinstance(val, list):
        return tuple(sorted(str(x) for x in val))
    if isinstance(val, dict):
        return tuple(sorted((k, str(v)) for k, v in val.items()))
    return val


class MajorityVoteResolver(ConflictResolver):
    """
    Resolves conflicts by taking the most common value.
    Falls back to priority order if there's a tie or no majority.
    """
    def __init__(self, fallback_resolver: ConflictResolver):
        self.fallback = fallback_resolver

    def resolve(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        if not values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[])

        # Filter valid values
        valid_values = [v for v in values if v.value not in (None, "", [], {})]

        if not valid_values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[v.to_provenance() for v in values])

        counts = Counter(_to_hashable(v.value) for v in valid_values)
        most_common = counts.most_common()

        if most_common[0][1] >= 2 and (len(most_common) == 1 or most_common[0][1] > most_common[1][1]):
            # Clear majority
            target_hashable = most_common[0][0]

            # Find all matching sources
            matching_sources = [v for v in valid_values if _to_hashable(v.value) == target_hashable]

            # Use the actual value from the first matching source, but collect all provenance
            chosen_value = matching_sources[0].value

            # Confidence gets a boost for agreement
            base_confidence = max(v.trust_score for v in matching_sources)
            confidence = round(min(1.0, base_confidence * 1.1), 4)

            return ResolvedValue(
                value=chosen_value,
                confidence=confidence,
                provenance=[v.to_provenance() for v in matching_sources],
                reasoning=f"Selected by majority vote ({len(matching_sources)} sources agree)"
            )

        # Fallback if no majority
        fallback_result = self.fallback.resolve(field_name, valid_values)
        fallback_result.reasoning = f"No majority found. {fallback_result.reasoning}"
        return fallback_result
