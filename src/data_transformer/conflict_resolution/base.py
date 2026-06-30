"""
Abstract base class for conflict resolvers.
"""
from abc import ABC, abstractmethod
from typing import Any, List, Optional
from dataclasses import dataclass

from data_transformer.schema.canonical import ProvenanceEntry

@dataclass
class SourceValue:
    """Wrapper for a value from a specific source."""
    value: Any
    source: str
    source_id: Optional[str]
    ingested_at: str
    trust_score: float
    raw_value: Optional[str] = None
    
    def to_provenance(self) -> ProvenanceEntry:
        return ProvenanceEntry(
            source=self.source,
            source_id=self.source_id,
            raw_value=self.raw_value,
            ingested_at=self.ingested_at
        )

@dataclass
class ResolvedValue:
    """The result of conflict resolution."""
    value: Any
    confidence: float
    provenance: List[ProvenanceEntry]
    reasoning: Optional[str] = None
    source: Optional[str] = None

class ConflictResolver(ABC):
    """Base class for all conflict resolution strategies."""
    
    @abstractmethod
    def resolve(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        """
        Resolve conflicts among multiple source values for a field.
        Must return a single ResolvedValue containing the chosen value, 
        confidence, provenance, and optional reasoning.
        """
        ...
