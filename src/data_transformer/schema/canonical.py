"""
Canonical Pydantic v2 schema for the candidate merging pipeline.
All internal data flows through these models.

Internal schema matches the assignment specification exactly:
  candidate_id, full_name, emails[], phones[], location {city, region, country},
  links {linkedin, github, portfolio, other[]}, headline, years_experience,
  skills[], experience[], education[], provenance[], overall_confidence

The Projection Layer handles all output format variations.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


# ─── Provenance ───────────────────────────────────────────────────────────────

class ProvenanceEntry(BaseModel):
    """Records exactly where a value came from, how it was extracted, and why it was chosen."""
    field: Optional[str] = None           # field name this provenance applies to
    source: str                           # ats | linkedin | resume | csv | notes | github
    source_id: Optional[str] = None       # original record ID in that source
    method: Optional[str] = None          # extraction method: structured_json | regex_extraction | api_fetch | url_stub
    timestamp: Optional[str] = None       # ISO-8601 ingestion timestamp
    raw_value: Optional[str] = None       # value before normalization
    confidence: Optional[float] = None    # per-provenance confidence (0.0–1.0)
    reason: Optional[str] = None          # human-readable reason for selection/rejection
    ingested_at: Optional[str] = None     # alias kept for backward compat


# ─── Generic Field Value ──────────────────────────────────────────────────────

class FieldValue(BaseModel, Generic[T]):
    """Wraps any scalar field with confidence + full provenance."""
    value: Optional[T] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None    # human-readable resolution reasoning


# ─── Contact Fields ───────────────────────────────────────────────────────────

class EmailEntry(BaseModel):
    value: str
    is_primary: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


class PhoneEntry(BaseModel):
    value: str                            # E.164 format
    is_primary: bool = False
    type: Optional[str] = None            # mobile | home | work
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


# ─── Location ─────────────────────────────────────────────────────────────────

class LocationEntry(BaseModel):
    """Assignment-spec location: city, region, country (ISO-3166 alpha-2)."""
    city: Optional[str] = None
    region: Optional[str] = None          # state / province (renamed from 'state' to match spec)
    country: Optional[str] = None         # ISO-3166 alpha-2 (US, GB, IN, etc.)
    formatted: Optional[str] = None       # human-readable combined string
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None


# ─── Links ────────────────────────────────────────────────────────────────────

class LinksBundle(BaseModel):
    """Assignment-spec links object: structured by type, not a flat array."""
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)

    @classmethod
    def from_link_entries(cls, entries: "List[LinkEntry]") -> "LinksBundle":
        """Convert a flat list of LinkEntry objects into the structured bundle."""
        bundle = cls()
        seen_urls: set = set()
        for entry in entries:
            url_key = entry.url.lower().rstrip("/")
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)

            link_type = (entry.type or "other").lower()
            if link_type == "linkedin" and not bundle.linkedin:
                bundle.linkedin = entry.url
            elif link_type == "github" and not bundle.github:
                bundle.github = entry.url
            elif link_type == "portfolio" and not bundle.portfolio:
                bundle.portfolio = entry.url
            else:
                if entry.url not in bundle.other:
                    bundle.other.append(entry.url)
            # Aggregate confidence from highest-confidence link
            if entry.confidence > bundle.confidence:
                bundle.confidence = entry.confidence
            bundle.provenance.extend(entry.provenance)
        return bundle


# ─── Internal link entry (pre-bundle) ────────────────────────────────────────

class LinkEntry(BaseModel):
    """Internal flat representation used during extraction and merge."""
    url: str
    type: Optional[str] = None            # linkedin | github | portfolio | other
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


# ─── Skills ───────────────────────────────────────────────────────────────────

class SkillEntry(BaseModel):
    """Assignment-spec skill: structured object with name, confidence, sources[]."""
    name: str                             # canonical display name
    normalized: str                       # lower-cased canonical key
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sources: List[str] = Field(default_factory=list)   # list of source names that mentioned this skill
    provenance: List[ProvenanceEntry] = Field(default_factory=list)


# ─── Experience ───────────────────────────────────────────────────────────────

class ExperienceEntry(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None           # YYYY-MM
    end: Optional[str] = None             # YYYY-MM or None if current
    is_current: bool = False
    summary: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None

    from pydantic import model_validator
    
    @model_validator(mode="after")
    def validate_dates(self) -> "ExperienceEntry":
        if self.is_current and self.end is not None:
            raise ValueError("end_date must be null if is_current is true")
        return self


# ─── Education ────────────────────────────────────────────────────────────────

class EducationEntry(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    merge_reason: Optional[str] = None


# ─── Source Provenance (record-level) ────────────────────────────────────────

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
    merge_decisions: List[dict] = Field(default_factory=list)   # field-level explainable merge entries


# ─── Canonical Candidate Record ───────────────────────────────────────────────

class CandidateRecord(BaseModel):
    """
    The canonical internal representation of a merged candidate.

    This schema matches the Eightfold assignment specification exactly:
      candidate_id, full_name, emails[], phones[], location {city, region, country},
      links {linkedin, github, portfolio, other[]}, headline, years_experience,
      skills[], experience[], education[], provenance[], overall_confidence

    DO NOT expose internal structures directly — always go through the Projection Layer.
    """
    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Core identity
    full_name: FieldValue[str] = Field(default_factory=lambda: FieldValue[str]())
    emails: List[EmailEntry] = Field(default_factory=list)
    phones: List[PhoneEntry] = Field(default_factory=list)
    location: LocationEntry = Field(default_factory=LocationEntry)
    links: LinksBundle = Field(default_factory=LinksBundle)

    # Professional
    headline: FieldValue[str] = Field(default_factory=lambda: FieldValue[str]())
    years_experience: FieldValue[float] = Field(default_factory=lambda: FieldValue[float]())
    skills: List[SkillEntry] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)

    # Tracking
    provenance: List[SourceProvenance] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    merge_summary: MergeSummary = Field(default_factory=MergeSummary)

    def primary_email(self) -> Optional[str]:
        primary = next((e for e in self.emails if e.is_primary), None)
        if primary:
            return primary.value
        return self.emails[0].value if self.emails else None

    def primary_phone(self) -> Optional[str]:
        primary = next((p for p in self.phones if p.is_primary), None)
        if primary:
            return primary.value
        return self.phones[0].value if self.phones else None


# ─── Raw Source Record ────────────────────────────────────────────────────────

class RawRecord(BaseModel):
    """Output of a source adapter — raw extracted fields, not yet normalized."""
    source: str
    source_id: Optional[str] = None
    ingested_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    fields: dict[str, Any] = Field(default_factory=dict)
    extraction_stats: dict[str, Any] = Field(default_factory=dict)


# ─── Source descriptor ────────────────────────────────────────────────────────

class Source(BaseModel):
    """Describes an input to the pipeline."""
    type: str                             # ats | linkedin | linkedin_url | resume | csv | notes | github_url
    path: Optional[str] = None
    content: Optional[Any] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
