"""
Merge Engine.
Takes groups of matched RawRecords, applies conflict resolution per field,
and constructs the final canonical CandidateRecord.
"""
from typing import Any, Dict, List
import uuid

from data_transformer.schema.canonical import (
    CandidateRecord,
    MergeSummary,
    ProvenanceEntry,
    FieldValue,
    EmailEntry,
    PhoneEntry,
    LocationEntry,
    SkillEntry,
    ExperienceEntry,
    EducationEntry,
    LinkEntry,
    SourceProvenance,
    RawRecord
)
from data_transformer.deduplication.matcher import MatchGroup
from data_transformer.conflict_resolution.base import ConflictResolver, SourceValue


def _round_confidence(value: float, decimals: int = 4) -> float:
    """Round confidence to a fixed number of decimal places to avoid floating-point artifacts."""
    return round(value, decimals)


class MergeEngine:
    """
    Orchestrates the merge of a MatchGroup into a CandidateRecord.
    """
    def __init__(self, 
                 default_resolver: ConflictResolver, 
                 field_overrides: Dict[str, ConflictResolver],
                 trust_scores: Dict[str, float]):
        self.default_resolver = default_resolver
        self.field_overrides = field_overrides
        self.trust_scores = trust_scores

    def merge(self, group: MatchGroup) -> CandidateRecord:
        """Merge a group of raw records into a single CandidateRecord."""
        record_id = str(uuid.uuid4())
        
        # Collect source level provenance
        prov_list = []
        sources_merged = []
        
        for r in group.records:
            sources_merged.append(r.source)
            prov_list.append(SourceProvenance(
                source=r.source,
                source_id=r.source_id,
                ingested_at=r.ingested_at
            ))
            
        summary = MergeSummary(sources_merged=list(set(sources_merged)))
        
        # Helper to resolve a specific scalar field
        def resolve_scalar(field_name: str) -> FieldValue:
            values = self._extract_source_values(group.records, field_name)
            if not values:
                summary.fields_missing.append(field_name)
                return FieldValue()
                
            resolver = self.field_overrides.get(field_name, self.default_resolver)
            resolved = resolver.resolve(field_name, values)
            
            if len(values) > 1 and len({v.value for v in values if v.value}) > 1:
                summary.fields_conflicted.append(field_name)
                summary.conflict_resolution_methods[field_name] = resolver.__class__.__name__
                
            return FieldValue(
                value=resolved.value,
                confidence=_round_confidence(resolved.confidence),
                provenance=resolved.provenance,
                merge_reason=resolved.reasoning
            )

        # Build candidate
        candidate = CandidateRecord(
            candidate_id=record_id,
            provenance=prov_list,
            merge_summary=summary
        )
        
        # Resolve scalar fields
        candidate.full_name = resolve_scalar("full_name")
        
        # For lists (emails, phones, skills, experience, education, links), we do union merges
        candidate.emails = self._merge_emails(group)
        candidate.phones = self._merge_phones(group)
        candidate.skills = self._merge_skills(group)
        candidate.experience = self._merge_experience(group)
        candidate.education = self._merge_education(group)
        candidate.links = self._merge_links(group)
        
        # Location (dict/object merge could be complex, for now we treat as scalar string or dict)
        loc_val = resolve_scalar("location")
        if loc_val.value:
            if isinstance(loc_val.value, dict):
                candidate.location = LocationEntry(**loc_val.value, confidence=loc_val.confidence, provenance=loc_val.provenance, merge_reason=loc_val.merge_reason)
            else:
                candidate.location = LocationEntry(formatted=loc_val.value, confidence=loc_val.confidence, provenance=loc_val.provenance, merge_reason=loc_val.merge_reason)
        
        # Calculate overall confidence
        candidate.overall_confidence = self._calculate_overall_confidence(candidate)
        
        return candidate

    def _extract_source_values(self, records: List[RawRecord], field_name: str) -> List[SourceValue]:
        values = []
        for r in records:
            val = r.fields.get(field_name)
            if val not in (None, "", [], {}):
                values.append(SourceValue(
                    value=val,
                    source=r.source,
                    source_id=r.source_id,
                    ingested_at=r.ingested_at,
                    trust_score=self.trust_scores.get(r.source, 0.5)
                ))
        return values
        
    def _calculate_overall_confidence(self, candidate: CandidateRecord) -> float:
        """Weighted average of scalar confidences and list source trusts."""
        scores = []
        if candidate.full_name.confidence:
            scores.append(candidate.full_name.confidence)
        if candidate.location.confidence:
            scores.append(candidate.location.confidence)
            
        for e in candidate.emails: scores.append(e.confidence)
        for p in candidate.phones: scores.append(p.confidence)
        for s in candidate.skills: scores.append(s.confidence)
        
        if not scores:
            return 0.0
        return _round_confidence(sum(scores) / len(scores))

    # ─── Union Merge Helpers ──────────────────────────────────────────────────
    
    def _merge_emails(self, group: MatchGroup) -> List[EmailEntry]:
        # Simple union by email string
        from data_transformer.normalizers import normalize_email
        unique = {}
        for r in group.records:
            trust = self.trust_scores.get(r.source, 0.5)
            for email in r.fields.get("emails", []):
                email = normalize_email(email)
                if not email: continue
                if email not in unique:
                    unique[email] = EmailEntry(value=email, confidence=trust)
                unique[email].provenance.append(ProvenanceEntry(source=r.source, ingested_at=r.ingested_at))
                # Boost confidence if seen multiple times
                if len(unique[email].provenance) > 1:
                    unique[email].confidence = _round_confidence(min(1.0, unique[email].confidence * 1.1))
                    
        res = list(unique.values())
        if res:
            res.sort(key=lambda x: x.confidence, reverse=True)
            res[0].is_primary = True
        return res

    def _merge_phones(self, group: MatchGroup) -> List[PhoneEntry]:
        from data_transformer.normalizers import normalize_phone
        unique = {}
        for r in group.records:
            trust = self.trust_scores.get(r.source, 0.5)
            for phone in r.fields.get("phones", []):
                phone = normalize_phone(phone)
                if not phone: continue
                if phone not in unique:
                    unique[phone] = PhoneEntry(value=phone, confidence=trust)
                unique[phone].provenance.append(ProvenanceEntry(source=r.source, ingested_at=r.ingested_at))
                # Boost confidence if seen in multiple sources (same pattern as emails)
                if len(unique[phone].provenance) > 1:
                    unique[phone].confidence = _round_confidence(min(1.0, unique[phone].confidence * 1.1))
        res = list(unique.values())
        if res:
            res.sort(key=lambda x: x.confidence, reverse=True)
            res[0].is_primary = True
        return res
        
    def _merge_skills(self, group: MatchGroup) -> List[SkillEntry]:
        unique = {}
        for r in group.records:
            trust = self.trust_scores.get(r.source, 0.5)
            for skill in r.fields.get("skills", []):
                if not skill: continue
                norm = skill.lower()
                if norm not in unique:
                    unique[norm] = SkillEntry(name=skill, normalized=norm, confidence=trust)
                unique[norm].provenance.append(ProvenanceEntry(source=r.source, ingested_at=r.ingested_at))
                unique[norm].confidence = _round_confidence(min(1.0, unique[norm].confidence * 1.05))
        res = list(unique.values())
        res.sort(key=lambda x: x.confidence, reverse=True)
        return res

    def _merge_experience(self, group: MatchGroup) -> List[ExperienceEntry]:
        # Advanced merging: group by overlapping companies (fuzzy) and date ranges
        all_exp = []
        for r in group.records:
            trust = self.trust_scores.get(r.source, 0.5)
            for exp in r.fields.get("experience", []):
                entry = ExperienceEntry(
                    **exp, 
                    confidence=trust,
                    provenance=[ProvenanceEntry(source=r.source, ingested_at=r.ingested_at)]
                )
                all_exp.append(entry)
        
        # Improved dedup: group by normalized company name (lowercase, stripped)
        # and overlapping date ranges, then pick the best entry from each group
        from collections import defaultdict
        company_groups = defaultdict(list)
        for e in all_exp:
            company_key = (e.company or "").lower().replace("inc.", "").replace("inc", "").replace("corp.", "").replace("corp", "").strip()
            company_groups[company_key].append(e)
        
        merged_result = []
        for company_key, entries in company_groups.items():
            if len(entries) == 1:
                merged_result.append(entries[0])
            else:
                # Multiple entries for same company — merge them
                # Pick the best title (highest confidence), best dates, etc.
                best_entry = max(entries, key=lambda x: x.confidence)
                
                # Collect all provenances
                all_prov = []
                for e in entries:
                    all_prov.extend(e.provenance)
                
                # Use the best entry's data but merge provenances
                best_entry.provenance = all_prov
                
                # If any entry says is_current=True, use that
                if any(e.is_current for e in entries):
                    best_entry.is_current = True
                    # If current, end_date should be None
                    best_entry.end_date = None
                
                # Use the earliest start_date
                valid_starts = [e.start_date for e in entries if e.start_date]
                if valid_starts:
                    best_entry.start_date = min(valid_starts)
                
                # Use the latest end_date (or None if any is current)
                if not best_entry.is_current:
                    valid_ends = [e.end_date for e in entries if e.end_date]
                    if valid_ends:
                        best_entry.end_date = max(valid_ends)
                
                # Fix semantic inconsistency: if is_current is False but end_date is None,
                # set a reasonable end_date or mark as current
                if not best_entry.is_current and best_entry.end_date is None:
                    # If there's a non-null end_date from any entry, use it
                    for e in entries:
                        if e.end_date is not None:
                            best_entry.end_date = e.end_date
                            break
                    else:
                        # No end_date found — this is likely still current
                        best_entry.is_current = True
                
                # Boost confidence for agreement
                if len(entries) > 1:
                    best_entry.confidence = _round_confidence(min(1.0, best_entry.confidence * 1.05))
                
                merged_result.append(best_entry)
        
        res = list(merged_result)
        res.sort(key=lambda x: x.start_date or "", reverse=True)
        return res

    def _merge_education(self, group: MatchGroup) -> List[EducationEntry]:
        all_edu = []
        for r in group.records:
            trust = self.trust_scores.get(r.source, 0.5)
            for edu in r.fields.get("education", []):
                entry = EducationEntry(
                    **edu, 
                    confidence=trust,
                    provenance=[ProvenanceEntry(source=r.source, ingested_at=r.ingested_at)]
                )
                all_edu.append(entry)
        
        deduped = {}
        for e in all_edu:
            key = f"{e.institution}|{e.degree}"
            if key not in deduped or deduped[key].confidence < e.confidence:
                deduped[key] = e
                
        res = list(deduped.values())
        res.sort(key=lambda x: x.start_date or "", reverse=True)
        return res

    def _merge_links(self, group: MatchGroup) -> List[LinkEntry]:
        unique = {}
        for r in group.records:
            for link in r.fields.get("links", []):
                url = link.get("url")
                if not url: continue
                if url not in unique:
                    unique[url] = LinkEntry(url=url, type=link.get("type"))
                unique[url].provenance.append(ProvenanceEntry(source=r.source, ingested_at=r.ingested_at))
        return list(unique.values())
