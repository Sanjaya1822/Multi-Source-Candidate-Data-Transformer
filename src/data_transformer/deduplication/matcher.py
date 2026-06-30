"""
Deduplication and Matcher logic.
Groups incoming RawRecords into matched candidate sets.
"""
from __future__ import annotations

import collections
from typing import List, Set

from rapidfuzz import fuzz

from data_transformer.schema.canonical import RawRecord
from data_transformer.normalizers import normalize_email, normalize_phone, normalize_name, normalize_company


class MatchGroup:
    """A group of records that belong to the same candidate."""
    def __init__(self):
        self.records: List[RawRecord] = []
        
    def add(self, record: RawRecord):
        self.records.append(record)
        
    def get_emails(self) -> Set[str]:
        emails = set()
        for r in self.records:
            emails.update([normalize_email(e) for e in r.fields.get("emails", []) if e])
        return {e for e in emails if e}
        
    def get_phones(self) -> Set[str]:
        phones = set()
        for r in self.records:
            phones.update([normalize_phone(p) for p in r.fields.get("phones", []) if p])
        return {p for p in phones if p}
        
    def get_names(self) -> Set[str]:
        names = set()
        for r in self.records:
            name = normalize_name(r.fields.get("full_name", ""))
            if name:
                names.add(name.lower())
        return names
        
    def get_companies(self) -> Set[str]:
        companies = set()
        for r in self.records:
            for exp in r.fields.get("experience", []):
                comp = normalize_company(exp.get("company", ""))
                if comp:
                    companies.add(comp.lower())
        return companies


class Matcher:
    """
    Groups candidates using tiered matching strategy.
    """
    def __init__(self, fuzzy_threshold: float = 85.0, name_company_threshold: float = 80.0):
        self.fuzzy_threshold = fuzzy_threshold
        self.name_company_threshold = name_company_threshold

    def match(self, records: List[RawRecord]) -> List[MatchGroup]:
        """Group records into unique candidates."""
        if not records:
            return []
            
        groups: List[MatchGroup] = []
        
        for record in records:
            matched_group = None
            
            # 1. Exact matching
            for group in groups:
                if self._exact_match(record, group):
                    matched_group = group
                    break
                    
            # 2. Fuzzy matching
            if not matched_group:
                for group in groups:
                    if self._fuzzy_match(record, group):
                        matched_group = group
                        break
                        
            if matched_group:
                matched_group.add(record)
            else:
                new_group = MatchGroup()
                new_group.add(record)
                groups.append(new_group)
                
        return groups

    def _exact_match(self, record: RawRecord, group: MatchGroup) -> bool:
        """Check for exact email, phone, or LinkedIn ID match."""
        # Email match
        rec_emails = {normalize_email(e) for e in record.fields.get("emails", []) if e}
        rec_emails = {e for e in rec_emails if e}
        if rec_emails and rec_emails.intersection(group.get_emails()):
            return True
            
        # Phone match
        rec_phones = {normalize_phone(p) for p in record.fields.get("phones", []) if p}
        rec_phones = {p for p in rec_phones if p}
        if rec_phones and rec_phones.intersection(group.get_phones()):
            return True
            
        # LinkedIn ID match
        rec_linkedin = None
        if record.source == "linkedin":
            rec_linkedin = record.source_id
        else:
            for link in record.fields.get("links", []):
                if link.get("type") == "linkedin" and "linkedin.com/in/" in link.get("url", ""):
                    rec_linkedin = link.get("url").split("/in/")[-1].strip("/")
                    break
                    
        if rec_linkedin:
            for g_rec in group.records:
                if g_rec.source == "linkedin" and g_rec.source_id == rec_linkedin:
                    return True
                for link in g_rec.fields.get("links", []):
                    if link.get("type") == "linkedin" and "linkedin.com/in/" in link.get("url", ""):
                        if rec_linkedin == link.get("url").split("/in/")[-1].strip("/"):
                            return True
                            
        return False

    def _fuzzy_match(self, record: RawRecord, group: MatchGroup) -> bool:
        """Check for fuzzy name or name+company match."""
        rec_name = normalize_name(record.fields.get("full_name", "")).lower()
        if not rec_name:
            return False
            
        # Try name fuzzy match
        for group_name in group.get_names():
            if fuzz.ratio(rec_name, group_name) >= self.fuzzy_threshold:
                return True
                
        # Try name + company match (lower threshold for name if company matches)
        rec_companies = {normalize_company(exp.get("company", "")).lower() 
                         for exp in record.fields.get("experience", [])}
        rec_companies = {c for c in rec_companies if c}
        
        group_companies = group.get_companies()
        
        if rec_companies and group_companies and rec_companies.intersection(group_companies):
            # Company matches exactly, check name with lower threshold
            for group_name in group.get_names():
                if fuzz.ratio(rec_name, group_name) >= self.name_company_threshold:
                    return True
                    
        return False
