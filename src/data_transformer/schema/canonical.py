"""
Canonical Pydantic v2 schema for the candidate merging pipeline.
All internal data flows through these models.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


# ─── Provenance ───────────────────────────────────────────────────────────────

class ProvenanceEntry(BaseModel):
    """Records where a value came from."""
    source: str                          # ats | linkedin | resume | csv | notes
    source_id: Optional[str] = None      # original record ID in that source
    raw_value: Optional[str] = None      # value before normalization
    ingested_at: Optional[str] = None    # ISO-8601 timestamp


# ─── Generic Field Value ──────────────────────────────────────────────────────

class FieldValue(BaseModel, Generic[T]):
    """Wraps any field with confidence + provenance."""
    value: Optional[T] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None   # human-readable resolution reasoning


# ─── Contact Fields ───────────────────────────────────────────────────────────

class EmailEntry(BaseModel):
    value: str
    is_primary: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


class PhoneEntry(BaseModel):
    value: str                           # E.164 format
    is_primary: bool = False
    type: Optional[str] = None           # mobile | home | work
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


# ─── Location ─────────────────────────────────────────────────────────────────

class LocationEntry(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    formatted: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None


# ─── Links ────────────────────────────────────────────────────────────────────

class LinkEntry(BaseModel):
    url: str
    type: Optional[str] = None           # linkedin | github | portfolio | other
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


# ─── Skills ───────────────────────────────────────────────────────────────────

class SkillEntry(BaseModel):
    name: str                            # canonical name
    normalized: str                      # lower-cased canonical
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


# ─── Experience ───────────────────────────────────────────────────────────────

class ExperienceEntry(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None     # YYYY-MM
    end_date: Optional[str] = None       # YYYY-MM or None if current
    is_current: bool = False
    description: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None


# ─── Education ────────────────────────────────────────────────────────────────

class EducationEntry(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None     # YYYY-MM
    end_date: Optional[str] = None       # YYYY-MM
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None


# ─── Source Provenance ────────────────────────────────────────────────────────

class SourceProvenance(BaseModel):
    source: str
    source_id: Optional[str] = None
    ingested_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ─── Merge Summary ────────────────────────────────────────────────────────────

class MergeSummary(BaseModel):
    sources_merged: List[str] = Field(default_factory=list)
    fields_conflicted: List[str] = Field(default_factory=list)
    fields_missing: List[str] = Field(default_factory=list)
    conflict_resolution_methods: dict[str, str] = Field(default_factory=dict)


# ─── Canonical Candidate Record ───────────────────────────────────────────────

class CandidateRecord(BaseModel):
    """
    The canonical internal representation of a merged candidate.
    All pipeline stages read/write this model.
    """
    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    full_name: FieldValue[str] = Field(default_factory=lambda: FieldValue[str]())
    emails: List[EmailEntry] = Field(default_factory=list)
    phones: List[PhoneEntry] = Field(default_factory=list)
    location: LocationEntry = Field(default_factory=LocationEntry)
    links: List[LinkEntry] = Field(default_factory=list)
    skills: List[SkillEntry] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)

    provenance: List[SourceProvenance] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    merge_summary: MergeSummary = Field(default_factory=MergeSummary)

    def primary_email(self) -> Optional[str]:
        primary = next((e for e in self.emails if e.is_primary), None)
        return (primary or (self.emails[0] if self.emails else None)) and \
               (primary.value if primary else (self.emails[0].value if self.emails else None))

    def primary_phone(self) -> Optional[str]:
        primary = next((p for p in self.phones if p.is_primary), None)
        return (primary.value if primary else (self.phones[0].value if self.phones else None))


# ─── Raw Source Record (pre-normalization) ────────────────────────────────────

class RawRecord(BaseModel):
    """
    Output of a source adapter — raw extracted fields, not yet normalized.
    Keys are field names, values are raw strings/lists.
    """
    source: str
    source_id: Optional[str] = None
    ingested_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    fields: dict[str, Any] = Field(default_factory=dict)


# ─── Source descriptor ────────────────────────────────────────────────────────

class Source(BaseModel):
    """Describes an input to the pipeline."""
    type: str                            # ats | linkedin | resume | csv | notes
    path: Optional[str] = None           # file path or None for in-memory
    content: Optional[Any] = None        # in-memory content (dict, str, bytes)
    metadata: dict[str, Any] = Field(default_factory=dict)
