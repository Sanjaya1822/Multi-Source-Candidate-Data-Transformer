"""Conflict Resolution package."""
from .base import ConflictResolver, ResolvedValue, SourceValue
from .priority_order import PriorityOrderResolver
from .majority_vote import MajorityVoteResolver
from .latest_wins import LatestWinsResolver
from .highest_confidence import HighestConfidenceResolver
from .llm_resolver import MockLLMResolver, PhiLLMResolver

__all__ = [
    "ConflictResolver",
    "ResolvedValue",
    "SourceValue",
    "PriorityOrderResolver",
    "MajorityVoteResolver",
    "LatestWinsResolver",
    "HighestConfidenceResolver",
    "MockLLMResolver",
    "PhiLLMResolver",
]
