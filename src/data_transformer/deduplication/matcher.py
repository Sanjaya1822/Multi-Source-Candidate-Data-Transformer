"""
Deduplication and Matcher.

Groups incoming RawRecords into MatchGroups using a tiered strategy:

Tier 1 — Exact identifiers (highest confidence, checked first):
  a. Normalised email match
  b. E.164 phone match
  c. LinkedIn profile ID  (extracted from any link[] with type=linkedin)
  d. GitHub username      (extracted from any link[] with type=github)

Tier 2 — Fuzzy name similarity (rapidfuzz ratio ≥ threshold)

Tier 3 — Fuzzy name + shared employer (lower threshold)

After the greedy pass a transitive-closure merge is applied so that
A↔B and B↔C correctly ends up as one group {A,B,C}.

This ensures that:
  - Resume + GitHub URL → matched via shared GitHub link
  - Resume + LinkedIn URL stub → matched via shared LinkedIn link
  - Resume + ATS + LinkedIn → matched via email OR fuzzy name
"""
from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from rapidfuzz import fuzz

from data_transformer.schema.canonical import RawRecord
from data_transformer.normalizers import (
    normalize_email, normalize_phone, normalize_name, normalize_company,
)


# ─── MatchGroup ──────────────────────────────────────────────────────────────

class MatchGroup:
    """A group of records that belong to the same candidate."""

    def __init__(self) -> None:
        self.records: List[RawRecord] = []

    def add(self, record: RawRecord) -> None:
        self.records.append(record)

    # ── Identifier sets ───────────────────────────────────────────────────────

    def get_emails(self) -> Set[str]:
        out: Set[str] = set()
        for r in self.records:
            for e in r.fields.get("emails", []):
                n = normalize_email(str(e)) if e else ""
                if n:
                    out.add(n)
        return out

    def get_phones(self) -> Set[str]:
        out: Set[str] = set()
        for r in self.records:
            for p in r.fields.get("phones", []):
                n = normalize_phone(str(p)) if p else None
                if n:
                    out.add(n)
        return out

    def get_linkedin_ids(self) -> Set[str]:
        """Return LinkedIn username slugs from any record in this group."""
        return _linkedin_ids_from_records(self.records)

    def get_github_usernames(self) -> Set[str]:
        """Return GitHub usernames from any record in this group."""
        return _github_usernames_from_records(self.records)

    def get_names(self) -> Set[str]:
        out: Set[str] = set()
        for r in self.records:
            n = normalize_name(r.fields.get("full_name", "") or "")
            if n:
                out.add(n.lower())
        return out

    def get_companies(self) -> Set[str]:
        out: Set[str] = set()
        for r in self.records:
            for exp in r.fields.get("experience", []):
                if not isinstance(exp, dict):
                    continue
                c = normalize_company(exp.get("company") or "")
                if c:
                    out.add(c.lower())
        return out


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _linkedin_ids_from_records(records: List[RawRecord]) -> Set[str]:
    ids: Set[str] = set()
    for r in records:
        # Source ID for linkedin records
        if r.source == "linkedin" and r.source_id:
            ids.add(r.source_id.lower().strip("/"))
        # Source ID for linkedin_url stub
        if r.source == "linkedin_url" and r.source_id:
            ids.add(r.source_id.lower().strip("/"))
        # links[] array
        for lk in r.fields.get("links", []):
            if not isinstance(lk, dict):
                continue
            url = lk.get("url", "")
            if "linkedin.com/in/" in url:
                slug = url.split("/in/")[-1].strip("/").lower()
                if slug:
                    ids.add(slug)
    return ids


def _github_usernames_from_records(records: List[RawRecord]) -> Set[str]:
    names: Set[str] = set()
    for r in records:
        # Source ID for github records
        if r.source == "github" and r.source_id:
            names.add(r.source_id.lower())
        # links[] array — match only profile-level URLs (not repo paths)
        for lk in r.fields.get("links", []):
            if not isinstance(lk, dict):
                continue
            url = lk.get("url", "")
            m = re.search(r"github\.com/([\w\-]+)(?:/[^/]+)?/?$", url, re.I)
            if m:
                names.add(m.group(1).lower())
    return names


# ─── Matcher ─────────────────────────────────────────────────────────────────

class Matcher:
    """
    Groups RawRecords into unique candidates using tiered matching
    followed by transitive-closure merging.
    """

    def __init__(
        self,
        fuzzy_threshold: float = 85.0,
        name_company_threshold: float = 80.0,
    ) -> None:
        self.fuzzy_threshold       = fuzzy_threshold
        self.name_company_threshold = name_company_threshold

    # ── Public API ────────────────────────────────────────────────────────────

    def match(self, records: List[RawRecord]) -> List[MatchGroup]:
        if not records:
            return []

        # Greedy single-pass assignment
        groups: List[MatchGroup] = []
        for record in records:
            target = self._find_group(record, groups)
            if target is not None:
                target.add(record)
            else:
                g = MatchGroup()
                g.add(record)
                groups.append(g)

        # Transitive-closure merge: A↔B and B↔C → {A,B,C}
        groups = self._merge_transitive(groups)

        return groups

    # ── Group finder ─────────────────────────────────────────────────────────

    def _find_group(
        self, record: RawRecord, groups: List[MatchGroup]
    ) -> "MatchGroup | None":
        """Return the first group this record matches, or None."""
        for group in groups:
            if self._exact_match(record, group):
                return group
        for group in groups:
            if self._fuzzy_match(record, group):
                return group
        return None

    # ── Exact match ───────────────────────────────────────────────────────────

    def _exact_match(self, record: RawRecord, group: MatchGroup) -> bool:
        # a. Shared normalised email
        rec_emails = {
            normalize_email(str(e))
            for e in record.fields.get("emails", []) if e
        } - {""}
        if rec_emails and rec_emails & group.get_emails():
            return True

        # b. Shared E.164 phone
        rec_phones = {
            normalize_phone(str(p))
            for p in record.fields.get("phones", []) if p
        } - {None}  # type: ignore[arg-type]
        if rec_phones and rec_phones & group.get_phones():
            return True

        # c. Shared LinkedIn profile slug
        rec_li = _linkedin_ids_from_records([record])
        if rec_li and rec_li & group.get_linkedin_ids():
            return True

        # d. Shared GitHub username
        rec_gh = _github_usernames_from_records([record])
        if rec_gh and rec_gh & group.get_github_usernames():
            return True

        return False

    # ── Fuzzy match ───────────────────────────────────────────────────────────

    def _fuzzy_match(self, record: RawRecord, group: MatchGroup) -> bool:
        rec_name = normalize_name(record.fields.get("full_name") or "").lower()
        if not rec_name or len(rec_name) < 4:
            return False

        group_names = group.get_names()
        if not group_names:
            return False

        # For stub sources (linkedin_url, github) that carry no contact data,
        # apply a slightly more lenient name threshold so they can be absorbed
        # into an existing group rather than creating orphan groups.
        is_stub = record.source in ("linkedin_url",)
        effective_threshold = self.fuzzy_threshold - 5 if is_stub else self.fuzzy_threshold

        # Tier 2: name alone
        for gn in group_names:
            if fuzz.ratio(rec_name, gn) >= effective_threshold:
                return True

        # Tier 3: name + shared employer (relaxed name threshold)
        rec_companies = {
            normalize_company(exp.get("company") or "").lower()
            for exp in record.fields.get("experience", [])
            if isinstance(exp, dict)
        } - {""}

        if rec_companies and rec_companies & group.get_companies():
            for gn in group_names:
                if fuzz.ratio(rec_name, gn) >= self.name_company_threshold:
                    return True

        return False

    # ── Transitive closure ────────────────────────────────────────────────────

    def _merge_transitive(self, groups: List[MatchGroup]) -> List[MatchGroup]:
        """
        Union-Find merge: if two groups share any exact identifier,
        absorb the smaller into the larger.

        This handles the case where A↔B and B↔C were placed in different
        groups during the greedy pass (can happen when B was added before C).
        """
        n = len(groups)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # Check all pairs for shared exact identifiers
        for i in range(n):
            for j in range(i + 1, n):
                if self._groups_overlap(groups[i], groups[j]):
                    union(i, j)

        # Reconstruct merged groups
        merged: Dict[int, MatchGroup] = {}
        for i, g in enumerate(groups):
            root = find(i)
            if root not in merged:
                merged[root] = MatchGroup()
            for r in g.records:
                merged[root].add(r)

        return list(merged.values())

    def _groups_overlap(self, a: MatchGroup, b: MatchGroup) -> bool:
        """Return True if groups a and b share any exact identifier."""
        if a.get_emails() & b.get_emails():
            return True
        phones_a = a.get_phones()
        phones_b = b.get_phones()
        if phones_a and phones_b and phones_a & phones_b:
            return True
        if a.get_linkedin_ids() & b.get_linkedin_ids():
            return True
        if a.get_github_usernames() & b.get_github_usernames():
            return True
        return False
