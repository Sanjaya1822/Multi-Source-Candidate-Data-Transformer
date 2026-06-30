"""
Merge Engine.

Takes groups of matched RawRecords, applies conflict resolution per field,
and constructs the final canonical CandidateRecord.

Every merged field carries:
  - Confidence score (source reliability × extraction quality × cross-source agreement)
  - Provenance (source, method, reason, raw_value, timestamp)
  - Merge reason (human-readable explanation of why a value was chosen)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from data_transformer.schema.canonical import (
    CandidateRecord,
    MergeSummary,
    ProvenanceEntry,
    FieldValue,
    EmailEntry,
    PhoneEntry,
    LocationEntry,
    LinksBundle,
    LinkEntry,
    SkillEntry,
    ExperienceEntry,
    EducationEntry,
    SourceProvenance,
    RawRecord,
)
from data_transformer.deduplication.matcher import MatchGroup
from data_transformer.conflict_resolution.base import ConflictResolver, SourceValue
from data_transformer.normalizers import (
    normalize_email, normalize_phone, normalize_date, normalize_location_string
)
from data_transformer.normalizers.skills import normalize_skill, get_alias_reason


# ── Source reliability labels ─────────────────────────────────────────────────
SOURCE_LABELS: Dict[str, str] = {
    "ats": "ATS (structured)",
    "csv": "Recruiter CSV (structured)",
    "linkedin": "LinkedIn JSON (structured)",
    "linkedin_url": "LinkedIn URL (stub)",
    "resume": "Resume (unstructured)",
    "github": "GitHub (API)",
    "notes": "Recruiter Notes (unstructured)",
}

# Extraction quality multipliers per source type (structural quality, not trust)
EXTRACTION_QUALITY: Dict[str, float] = {
    "ats": 1.0,
    "csv": 0.95,
    "linkedin": 0.95,
    "github": 0.85,
    "resume": 0.75,
    "notes": 0.65,
    "linkedin_url": 0.30,
}


class MergeEngine:
    """
    Orchestrates the merge of a MatchGroup into a CandidateRecord.

    Confidence engine:
      - base = source trust_score × extraction quality multiplier
      - cross-source agreement bonus (up to +0.08)
      - conflict penalty per conflicting field (−0.01)
      - missing-value penalty per missing required field (−0.03)
      - overall = clamp(base + bonus − penalties, 0, 1)
    """

    def __init__(
        self,
        default_resolver: ConflictResolver,
        field_overrides: Dict[str, ConflictResolver],
        trust_scores: Dict[str, float],
    ):
        self.default_resolver = default_resolver
        self.field_overrides = field_overrides
        self.trust_scores = trust_scores

    def merge(self, group: MatchGroup) -> CandidateRecord:
        """Merge a group of raw records into a single CandidateRecord."""
        record_id = str(uuid.uuid4())

        # Source-level provenance
        prov_list: List[SourceProvenance] = []
        sources_merged: List[str] = []

        for r in group.records:
            sources_merged.append(r.source)
            prov_list.append(SourceProvenance(
                source=r.source,
                source_id=r.source_id,
                ingested_at=r.ingested_at,
            ))

        summary = MergeSummary(
            sources_merged=sorted(set(sources_merged)),
        )
        # Keep a reference to the same list so appends are visible on summary
        merge_decisions = summary.merge_decisions

        # ── Scalar field resolver ─────────────────────────────────────────────
        def resolve_scalar(field_name: str) -> FieldValue:
            values = self._extract_source_values(group.records, field_name)
            if not values:
                summary.fields_missing.append(field_name)
                return FieldValue()

            # Filter out None/empty/blank values — never overwrite a good value with null
            valid_values = [
                v for v in values
                if v.value not in (None, "", [], {})
                and str(v.value).strip() not in ("", "null", "None")
            ]
            if not valid_values:
                summary.fields_missing.append(field_name)
                return FieldValue()

            resolver = self.field_overrides.get(field_name, self.default_resolver)
            resolved = resolver.resolve(field_name, valid_values)

            # Populate source on resolved if the resolver didn't set it
            if resolved.source is None and resolved.provenance:
                resolved.source = resolved.provenance[0].source
            elif resolved.source is None and values:
                resolved.source = values[0].source

            has_conflict = (
                len(valid_values) > 1
                and len({str(v.value) for v in valid_values if v.value}) > 1
            )
            if has_conflict:
                summary.fields_conflicted.append(field_name)
                summary.conflict_resolution_methods[field_name] = resolver.__class__.__name__

            winning_source = resolved.source or "unknown"

            # Build per-value provenance with explainability
            provenance: List[ProvenanceEntry] = []
            for sv in valid_values:
                is_winner = sv.source == winning_source
                quality = EXTRACTION_QUALITY.get(sv.source, 0.7)
                adjusted_conf = round(sv.trust_score * quality, 4)
                reason = self._build_merge_reason(
                    field_name=field_name,
                    source=sv.source,
                    is_winner=is_winner,
                    has_conflict=has_conflict,
                    resolver_name=resolver.__class__.__name__,
                    winning_source=winning_source,
                )
                provenance.append(ProvenanceEntry(
                    field=field_name,
                    source=sv.source,
                    source_id=sv.source_id,
                    method=self._get_extraction_method(sv.source),
                    timestamp=sv.ingested_at,
                    raw_value=str(sv.value) if sv.value is not None else None,
                    confidence=adjusted_conf,
                    reason=reason,
                    ingested_at=sv.ingested_at,
                ))

            # Compute field confidence: winner's adjusted confidence
            winning_sv = next((sv for sv in valid_values if sv.source == winning_source), valid_values[0])
            quality = EXTRACTION_QUALITY.get(winning_sv.source, 0.7)
            field_conf = round(winning_sv.trust_score * quality, 4)

            # Cross-source agreement bonus
            if len(valid_values) > 1 and not has_conflict:
                field_conf = min(1.0, field_conf + 0.04 * (len(valid_values) - 1))

            merge_decisions.append({
                "field": field_name,
                "chosen_source": winning_source,
                "chosen_value": str(resolved.value) if resolved.value is not None else None,
                "source_count": len(valid_values),
                "had_conflict": has_conflict,
                "resolver": resolver.__class__.__name__,
                "reason": resolved.reasoning or f"Chosen from {SOURCE_LABELS.get(winning_source, winning_source)}",
            })

            return FieldValue(
                value=resolved.value,
                confidence=round(field_conf, 4),
                provenance=provenance,
                merge_reason=resolved.reasoning or f"Chosen from {SOURCE_LABELS.get(winning_source, winning_source)}",
            )

        # ── Build candidate ───────────────────────────────────────────────────
        candidate = CandidateRecord(
            candidate_id=record_id,
            provenance=prov_list,
            merge_summary=summary,
        )

        candidate.full_name = resolve_scalar("full_name")
        candidate.headline = resolve_scalar("headline")

        # List fields
        candidate.emails     = self._merge_emails(group)
        candidate.phones     = self._merge_phones(group)
        candidate.skills     = self._merge_skills(group)
        candidate.experience = self._merge_experience(group)
        candidate.education  = self._merge_education(group)

        # Pass-through fields (union merged, stored in merge_summary extras)
        candidate.merge_summary.merge_decisions  # already a ref
        self._collect_extras(group, candidate)

        # Structured location
        loc_val = resolve_scalar("location")
        if loc_val.value:
            raw_loc = str(loc_val.value) if not isinstance(loc_val.value, dict) else None
            if isinstance(loc_val.value, dict):
                loc_dict = loc_val.value
                candidate.location = LocationEntry(
                    city=loc_dict.get("city"),
                    region=loc_dict.get("region", loc_dict.get("state")),
                    country=loc_dict.get("country"),
                    formatted=loc_dict.get("formatted"),
                    confidence=loc_val.confidence,
                    provenance=loc_val.provenance,
                    merge_reason=loc_val.merge_reason,
                )
            else:
                parsed = normalize_location_string(raw_loc)
                candidate.location = LocationEntry(
                    city=parsed.get("city"),
                    region=parsed.get("region"),
                    country=parsed.get("country"),
                    formatted=parsed.get("formatted") or raw_loc,
                    confidence=loc_val.confidence,
                    provenance=loc_val.provenance,
                    merge_reason=loc_val.merge_reason,
                )

        # Structured links bundle
        candidate.links = self._merge_links_bundle(group)

        # Computed years of experience
        candidate.years_experience = self._compute_years_experience(candidate)

        # Final overall confidence
        candidate.overall_confidence = self._calculate_overall_confidence(candidate)

        return candidate

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _extract_source_values(
        self, records: List[RawRecord], field_name: str
    ) -> List[SourceValue]:
        values = []
        for r in records:
            val = r.fields.get(field_name)
            if val not in (None, "", [], {}):
                values.append(SourceValue(
                    value=val,
                    source=r.source,
                    source_id=r.source_id,
                    ingested_at=r.ingested_at,
                    trust_score=self.trust_scores.get(r.source, 0.5),
                ))
        return values

    def _get_extraction_method(self, source: str) -> str:
        return {
            "ats": "structured_json",
            "csv": "structured_csv",
            "linkedin": "structured_json",
            "linkedin_url": "url_stub",
            "resume": "regex_extraction",
            "github": "api_fetch",
            "notes": "regex_extraction",
        }.get(source, "unknown")

    def _build_merge_reason(
        self,
        field_name: str,
        source: str,
        is_winner: bool,
        has_conflict: bool,
        resolver_name: str,
        winning_source: str,
    ) -> str:
        label = SOURCE_LABELS.get(source, source)
        winning_label = SOURCE_LABELS.get(winning_source, winning_source)
        if is_winner:
            if has_conflict:
                return (
                    f"'{field_name}' chosen from {label} "
                    f"via {resolver_name} — higher source reliability"
                )
            return f"'{field_name}' from {label} — only available source"
        return (
            f"'{field_name}' from {label} NOT selected — "
            f"{winning_label} had higher confidence or priority"
        )

    def _field_confidence(self, source: str) -> float:
        """Compute adjusted confidence for a field from a given source."""
        trust = self.trust_scores.get(source, 0.5)
        quality = EXTRACTION_QUALITY.get(source, 0.7)
        return round(trust * quality, 4)

    def _calculate_overall_confidence(self, candidate: CandidateRecord) -> float:
        """
        Overall confidence engine:
          - Collect field-level confidence scores
          - Weight by field importance
          - Apply cross-source agreement bonus
          - Apply missing-field penalties
          - Apply conflict penalties
        """
        # Weighted field scores (importance weights)
        FIELD_WEIGHTS = {
            "full_name": 3.0,
            "emails": 2.5,
            "phones": 1.5,
            "location": 1.0,
            "skills": 1.5,
        }

        weighted_sum = 0.0
        weight_total = 0.0

        if candidate.full_name.confidence:
            w = FIELD_WEIGHTS["full_name"]
            weighted_sum += candidate.full_name.confidence * w
            weight_total += w

        if candidate.emails:
            best_email_conf = max(e.confidence for e in candidate.emails)
            w = FIELD_WEIGHTS["emails"]
            weighted_sum += best_email_conf * w
            weight_total += w

        if candidate.phones:
            best_phone_conf = max(p.confidence for p in candidate.phones)
            w = FIELD_WEIGHTS["phones"]
            weighted_sum += best_phone_conf * w
            weight_total += w

        if candidate.location.confidence:
            w = FIELD_WEIGHTS["location"]
            weighted_sum += candidate.location.confidence * w
            weight_total += w

        if candidate.skills:
            avg_skill_conf = sum(s.confidence for s in candidate.skills) / len(candidate.skills)
            w = FIELD_WEIGHTS["skills"]
            weighted_sum += avg_skill_conf * w
            weight_total += w

        if weight_total == 0:
            return 0.0

        base_conf = weighted_sum / weight_total

        # Cross-source agreement bonus (up to +0.08, more sources = higher agreement)
        n_sources = len(candidate.merge_summary.sources_merged)
        source_bonus = min(0.08, (n_sources - 1) * 0.03)

        # Missing required field penalty (−0.03 each, max −0.15)
        required_fields = ["full_name", "emails", "phones", "location", "skills"]
        missing_count = len(candidate.merge_summary.fields_missing)
        missing_penalty = min(0.15, missing_count * 0.03)

        # Conflict penalty (−0.01 per conflict, max −0.05)
        conflict_count = len(candidate.merge_summary.fields_conflicted)
        conflict_penalty = min(0.05, conflict_count * 0.01)

        return round(
            min(1.0, max(0.0, base_conf + source_bonus - missing_penalty - conflict_penalty)),
            4,
        )

    def _compute_years_experience(self, candidate: CandidateRecord) -> FieldValue[float]:
        """Estimate years of experience from the experience list dates."""
        if not candidate.experience:
            return FieldValue[float]()

        total_months = 0
        now = datetime.utcnow()

        for exp in candidate.experience:
            try:
                if exp.start:
                    parts = exp.start.split("-")
                    sy = int(parts[0])
                    sm = int(parts[1]) if len(parts) > 1 else 1
                    if exp.end:
                        eparts = exp.end.split("-")
                        ey = int(eparts[0])
                        em = int(eparts[1]) if len(eparts) > 1 else 12
                    else:
                        ey, em = now.year, now.month
                    months = (ey - sy) * 12 + (em - sm)
                    if months > 0:
                        total_months += months
            except (ValueError, IndexError, TypeError):
                pass

        if total_months == 0:
            return FieldValue[float]()

        years = round(total_months / 12, 1)
        return FieldValue[float](
            value=years,
            confidence=0.65,
            merge_reason="Computed from experience start/end date ranges",
        )

    # ─── Union merge helpers ──────────────────────────────────────────────────

    def _merge_emails(self, group: MatchGroup) -> List[EmailEntry]:
        unique: Dict[str, EmailEntry] = {}
        for r in group.records:
            trust = self._field_confidence(r.source)
            for email in r.fields.get("emails", []):
                normed = normalize_email(email)
                if not normed:
                    continue
                if normed not in unique:
                    unique[normed] = EmailEntry(
                        value=normed,
                        confidence=trust,
                        provenance=[ProvenanceEntry(
                            field="emails",
                            source=r.source,
                            source_id=r.source_id,
                            method=self._get_extraction_method(r.source),
                            timestamp=r.ingested_at,
                            raw_value=email,
                            confidence=trust,
                            reason=f"Email extracted from {SOURCE_LABELS.get(r.source, r.source)}",
                            ingested_at=r.ingested_at,
                        )],
                    )
                else:
                    unique[normed].provenance.append(ProvenanceEntry(
                        field="emails",
                        source=r.source,
                        method=self._get_extraction_method(r.source),
                        timestamp=r.ingested_at,
                        raw_value=email,
                        confidence=trust,
                        reason=f"Email confirmed by {SOURCE_LABELS.get(r.source, r.source)}",
                        ingested_at=r.ingested_at,
                    ))
                    # Cross-source confirmation boosts confidence (capped at 1.0)
                    unique[normed].confidence = round(min(1.0, unique[normed].confidence + 0.03), 4)

        result = list(unique.values())
        if result:
            result.sort(key=lambda x: x.confidence, reverse=True)
            result[0].is_primary = True
        return result

    def _merge_phones(self, group: MatchGroup) -> List[PhoneEntry]:
        unique: Dict[str, PhoneEntry] = {}
        for r in group.records:
            trust = self._field_confidence(r.source)
            for phone in r.fields.get("phones", []):
                normed = normalize_phone(phone)
                if not normed:
                    continue
                # Try to get phone type from raw field if structured
                phone_type = None
                if isinstance(phone, dict):
                    phone_type = phone.get("type")
                if normed not in unique:
                    unique[normed] = PhoneEntry(
                        value=normed,
                        type=phone_type,
                        confidence=trust,
                        provenance=[ProvenanceEntry(
                            field="phones",
                            source=r.source,
                            source_id=r.source_id,
                            method=self._get_extraction_method(r.source),
                            timestamp=r.ingested_at,
                            raw_value=str(phone),
                            confidence=trust,
                            reason=f"Phone extracted from {SOURCE_LABELS.get(r.source, r.source)}",
                            ingested_at=r.ingested_at,
                        )],
                    )
                else:
                    unique[normed].provenance.append(ProvenanceEntry(
                        field="phones",
                        source=r.source,
                        method=self._get_extraction_method(r.source),
                        timestamp=r.ingested_at,
                        raw_value=str(phone),
                        confidence=trust,
                        reason=f"Phone confirmed by {SOURCE_LABELS.get(r.source, r.source)}",
                        ingested_at=r.ingested_at,
                    ))
                    unique[normed].confidence = round(min(1.0, unique[normed].confidence + 0.03), 4)

        result = list(unique.values())
        if result:
            result.sort(key=lambda x: x.confidence, reverse=True)
            result[0].is_primary = True
        return result

    def _merge_skills(self, group: MatchGroup) -> List[SkillEntry]:
        unique: Dict[str, SkillEntry] = {}
        for r in group.records:
            trust = self._field_confidence(r.source)
            extraction_method = r.extraction_stats.get(
                "skill_extraction_method", self._get_extraction_method(r.source)
            )
            for skill in r.fields.get("skills", []):
                if not skill:
                    continue
                canonical = normalize_skill(str(skill))
                if not canonical:
                    continue
                key = canonical.lower()
                alias_reason = get_alias_reason(str(skill))

                if key not in unique:
                    unique[key] = SkillEntry(
                        name=canonical,
                        normalized=key,
                        confidence=trust,
                        sources=[r.source],
                        provenance=[ProvenanceEntry(
                            field="skills",
                            source=r.source,
                            source_id=r.source_id,
                            method=extraction_method,
                            timestamp=r.ingested_at,
                            raw_value=str(skill),
                            confidence=trust,
                            reason=alias_reason,
                            ingested_at=r.ingested_at,
                        )],
                    )
                else:
                    if r.source not in unique[key].sources:
                        unique[key].sources.append(r.source)
                    unique[key].provenance.append(ProvenanceEntry(
                        field="skills",
                        source=r.source,
                        method=extraction_method,
                        timestamp=r.ingested_at,
                        raw_value=str(skill),
                        confidence=trust,
                        reason=f"Confirmed by {SOURCE_LABELS.get(r.source, r.source)}",
                        ingested_at=r.ingested_at,
                    ))
                    # Boost per additional confirming source
                    unique[key].confidence = round(
                        min(1.0, unique[key].confidence + 0.04), 4
                    )

        result = list(unique.values())
        result.sort(key=lambda x: (-x.confidence, x.name))
        return result

    def _merge_experience(self, group: MatchGroup) -> List[ExperienceEntry]:
        all_exp: List[ExperienceEntry] = []
        for r in group.records:
            trust = self._field_confidence(r.source)
            for exp in r.fields.get("experience", []):
                if not isinstance(exp, dict):
                    continue
                try:
                    # Normalize dates
                    raw_start = exp.get("start_date", "") or ""
                    raw_end = exp.get("end_date", "") or ""
                    norm_start = normalize_date(raw_start) if raw_start else None
                    norm_end = normalize_date(raw_end) if raw_end else None

                    entry = ExperienceEntry(
                        company=exp.get("company") or exp.get("employer_name") or None,
                        title=exp.get("title") or None,
                        start=norm_start,
                        end=norm_end,
                        is_current=bool(exp.get("is_current", False)),
                        summary=exp.get("description") or None,
                        confidence=trust,
                        provenance=[ProvenanceEntry(
                            field="experience",
                            source=r.source,
                            source_id=r.source_id,
                            method=self._get_extraction_method(r.source),
                            timestamp=r.ingested_at,
                            confidence=trust,
                            reason=f"Experience record from {SOURCE_LABELS.get(r.source, r.source)}",
                            ingested_at=r.ingested_at,
                        )],
                    )
                    all_exp.append(entry)
                except Exception:
                    continue  # skip malformed entries, log nothing — robustness

        # 1. Normalize companies and titles
        for e in all_exp:
            company_norm = (e.company or "").lower().strip()
            # Strip corporate suffixes for better grouping
            for suffix in [" inc", " inc.", " llc", " corp", " ltd", " corporation"]:
                if company_norm.endswith(suffix):
                    company_norm = company_norm[:-len(suffix)].strip()
            # If no company, use a unique key so it doesn't merge with other no-company jobs
            company_key = company_norm if company_norm else f"__unknown_{uuid.uuid4()}"
            e._merge_group = company_key

        # Group by company
        grouped = {}
        for e in all_exp:
            grouped.setdefault(e._merge_group, []).append(e)

        merged_exp = []
        for company_key, entries in grouped.items():
            if company_key.startswith("__unknown_"):
                merged_exp.extend(entries)
                continue

            # Sort entries by start date
            def parse_start(x):
                if not x.start: return "9999-99"
                return x.start
            entries.sort(key=parse_start)

            # Merge overlapping or contiguous entries
            merged_list = []
            for e in entries:
                if not merged_list:
                    merged_list.append(e)
                    continue

                prev = merged_list[-1]
                # Check overlap
                prev_end = prev.end if not prev.is_current else "9999-99"
                curr_start = e.start or "9999-99"

                if curr_start <= prev_end:
                    # Merge e into prev
                    prev.end = e.end if (not prev.is_current and not e.is_current) else None
                    if prev.is_current or e.is_current:
                        prev.is_current = True
                        prev.end = None
                    # Decide title (keep the later/more senior one)
                    # For simplicity, if e starts later, we assume e is the promotion
                    if e.start and prev.start and e.start >= prev.start:
                        if e.title:
                            if prev.title and prev.title != e.title:
                                prev.summary = f"[{prev.title}] {prev.summary or ''} | [{e.title}] {e.summary or ''}".strip(" |")
                            prev.title = e.title
                    
                    prev.confidence = max(prev.confidence, e.confidence)
                    prev.provenance.extend(e.provenance)
                else:
                    merged_list.append(e)

            merged_exp.extend(merged_list)

        result = merged_exp
        # Sort: current jobs first, then by start date descending
        result.sort(key=lambda x: (
            0 if x.is_current else 1,
            -(int(x.start.replace("-", "")) if x.start and len(x.start) >= 7 else 0)
        ))
        return result

    def _merge_education(self, group: MatchGroup) -> List[EducationEntry]:
        all_edu: List[EducationEntry] = []
        for r in group.records:
            trust = self._field_confidence(r.source)
            for edu in r.fields.get("education", []):
                if not isinstance(edu, dict):
                    continue
                try:
                    raw_end = edu.get("end_date", "") or ""
                    norm_end = normalize_date(raw_end) if raw_end else None
                    end_year = None
                    if norm_end:
                        try:
                            end_year = int(norm_end.split("-")[0])
                        except ValueError:
                            pass

                    entry = EducationEntry(
                        institution=edu.get("institution") or edu.get("school_name") or None,
                        degree=edu.get("degree") or None,
                        field=edu.get("field_of_study") or edu.get("discipline") or None,
                        end_year=end_year,
                        confidence=trust,
                        provenance=[ProvenanceEntry(
                            field="education",
                            source=r.source,
                            source_id=r.source_id,
                            method=self._get_extraction_method(r.source),
                            timestamp=r.ingested_at,
                            confidence=trust,
                            reason=f"Education from {SOURCE_LABELS.get(r.source, r.source)}",
                            ingested_at=r.ingested_at,
                        )],
                    )
                    all_edu.append(entry)
                except Exception:
                    continue

        deduped: Dict[str, EducationEntry] = {}
        for e in all_edu:
            key = f"{(e.institution or '').lower()}|{(e.degree or '').lower()}"
            if key not in deduped or deduped[key].confidence < e.confidence:
                deduped[key] = e

        result = list(deduped.values())
        result.sort(key=lambda x: x.end_year or 0, reverse=True)
        return result

    def _collect_extras(self, group: MatchGroup, candidate: CandidateRecord) -> None:
        """
        Collect projects and certifications from all records and store them
        in merge_summary as extra_fields so the projector can surface them.
        """
        projects: list = []
        project_names: set = set()
        certifications: list = []
        cert_names: set = set()

        for r in group.records:
            for proj in r.fields.get("projects", []):
                name = (proj.get("name") or "").strip().lower() if isinstance(proj, dict) else str(proj).lower()
                if name and name not in project_names:
                    project_names.add(name)
                    projects.append(proj)

            for cert in r.fields.get("certifications", []):
                cert_str = str(cert).strip()
                key = cert_str.lower()
                if key and key not in cert_names:
                    cert_names.add(key)
                    certifications.append(cert_str)

        # Store in an extra dict on merge_summary so it survives into projection
        if not hasattr(candidate.merge_summary, "_extras"):
            object.__setattr__(candidate.merge_summary, "_extras", {})
        candidate.merge_summary._extras["projects"]       = projects       # type: ignore[attr-defined]
        candidate.merge_summary._extras["certifications"] = certifications  # type: ignore[attr-defined]

    def _merge_links_bundle(self, group: MatchGroup) -> LinksBundle:
        """Collect all link entries and produce the structured LinksBundle."""
        unique: Dict[str, LinkEntry] = {}
        for r in group.records:
            trust = self._field_confidence(r.source)
            for link in r.fields.get("links", []):
                if not isinstance(link, dict):
                    continue
                url = link.get("url", "").strip()
                if not url:
                    continue
                link_type = (link.get("type") or "other").lower()
                if url not in unique:
                    unique[url] = LinkEntry(
                        url=url,
                        type=link_type,
                        confidence=trust,
                        provenance=[ProvenanceEntry(
                            field="links",
                            source=r.source,
                            source_id=r.source_id,
                            method=self._get_extraction_method(r.source),
                            timestamp=r.ingested_at,
                            confidence=trust,
                            reason=f"Link found in {SOURCE_LABELS.get(r.source, r.source)}",
                            ingested_at=r.ingested_at,
                        )],
                    )
                else:
                    unique[url].provenance.append(ProvenanceEntry(
                        field="links",
                        source=r.source,
                        method=self._get_extraction_method(r.source),
                        timestamp=r.ingested_at,
                        confidence=trust,
                        reason=f"Link confirmed by {SOURCE_LABELS.get(r.source, r.source)}",
                        ingested_at=r.ingested_at,
                    ))
                    unique[url].confidence = round(min(1.0, unique[url].confidence + 0.02), 4)

        return LinksBundle.from_link_entries(list(unique.values()))
