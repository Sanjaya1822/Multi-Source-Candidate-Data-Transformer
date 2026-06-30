"""
Abstract base class for all source adapters.
Every adapter must implement can_handle(), extract(), and get_trust_score().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from data_transformer.schema.canonical import RawRecord, Source


class SourceAdapter(ABC):
    """
    Pluggable source adapter interface.

    Each concrete adapter knows how to:
      1. Detect if it can handle a given Source
      2. Extract raw fields into a RawRecord
      3. Report its trust score (used in confidence calculation)
    """

    @abstractmethod
    def can_handle(self, source: Source) -> bool:
        """Return True if this adapter can process the given Source."""
        ...

    @abstractmethod
    def extract(self, source: Source) -> RawRecord:
        """
        Parse the source and return a RawRecord with raw (un-normalized) fields.

        Fields dict should contain:
          full_name, emails, phones, location, links, skills,
          experience, education, linkedin_url
        """
        ...

    @abstractmethod
    def get_trust_score(self) -> float:
        """Return the base trust score for this source type (0.0 – 1.0)."""
        ...

    def safe_extract(self, source: Source) -> Optional[RawRecord]:
        """
        Wraps extract() with error handling.
        Returns None on failure instead of raising.
        """
        try:
            return self.extract(source)
        except Exception as exc:
            import structlog
            log = structlog.get_logger()
            log.warning(
                "adapter_extraction_failed",
                adapter=self.__class__.__name__,
                source_type=source.type,
                path=source.path,
                error=str(exc),
            )
            return None
