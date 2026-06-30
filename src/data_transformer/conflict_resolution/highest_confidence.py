"""
Highest Confidence strategy.
Weights source trust with cross-source agreement.
"""
from typing import Any, List
from .base import ConflictResolver, ResolvedValue, SourceValue


def _to_hashable(val: Any) -> Any:
    """Convert a value to a hashable form for grouping."""
    if isinstance(val, list):
        return tuple(sorted(str(x) for x in val))
    if isinstance(val, dict):
        return tuple(sorted((k, str(v)) for k, v in val.items()))
    return val


class HighestConfidenceResolver(ConflictResolver):
    """
    Chooses the value with the highest aggregated confidence.
    Base score is max trust among sources with that value.
    Bonus for cross-source agreement (0.05 per additional source).
    """

    def resolve(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        if not values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[])

        valid_values = [v for v in values if v.value not in (None, "", [], {})]
        if not valid_values:
            return ResolvedValue(value=None, confidence=0.0, provenance=[v.to_provenance() for v in values])

        # Group identical values
        grouped: dict[Any, List[SourceValue]] = {}
        for v in valid_values:
            h = _to_hashable(v.value)
            grouped.setdefault(h, []).append(v)

        best_hash = None
        best_score = -1.0

        for h, v_list in grouped.items():
            # Base score is max trust
            base = max(x.trust_score for x in v_list)
            # Bonus for agreement (up to 1.0)
            bonus = 0.05 * (len(v_list) - 1)
            score = min(1.0, base + bonus)

            if score > best_score:
                best_score = score
                best_hash = h

        chosen_group = grouped[best_hash]

        return ResolvedValue(
            value=chosen_group[0].value,
            confidence=round(best_score, 4),
            provenance=[v.to_provenance() for v in chosen_group],
            reasoning=f"Highest combined confidence score ({best_score:.2f}) from {len(chosen_group)} supporting sources"
        )
