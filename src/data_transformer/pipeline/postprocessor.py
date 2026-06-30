"""
Post-Processing Stage.

Runs after Merge, before Projection. Cleans the merged CandidateRecord:
  - Removes duplicate URLs (case-insensitive)
  - Deduplicates skills by canonical normalized key
  - Removes experience/education entries with no meaningful data
  - Strips empty/null objects from lists
  - Removes obviously invalid entities (malformed emails, short names, etc.)
  - Trims overly long descriptions
  - Deduplicates certifications (case-insensitive)
  - Ensures phones are E.164 (drops any that aren't after normalization)
  - Validates location fields (rejects education strings as location)
  - Records all cleanup actions for the report
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from data_transformer.schema.canonical import CandidateRecord


# Maximum lengths for free-text fields
MAX_DESCRIPTION_CHARS = 500
MAX_HEADLINE_CHARS    = 300

# Patterns that indicate a value is junk, not a real entity
_JUNK_NAME_RE = re.compile(
    r"^(?:career\s+objective|summary|profile|skills|experience|"
    r"education|contact|certif|project|resume|cv|curriculum\s+vitae)$",
    re.I,
)

_EDUCATION_IN_LOCATION_RE = re.compile(
    r"\b(?:university|college|institute|campus|school|academy|"
    r"polytechnic|b\.?tech|b\.?e|m\.?tech|cgpa|gpa|engineering|"
    r"technology|science|arts|commerce|management)\b",
    re.I,
)

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def post_process(candidate: CandidateRecord) -> Tuple[CandidateRecord, List[str]]:
    """
    Clean and validate a merged CandidateRecord.

    Returns (cleaned_candidate, list_of_cleanup_actions).
    Modifies the candidate in-place and also returns it.
    """
    actions: List[str] = []

    # ── 1. Full name validation ───────────────────────────────────────────────
    name_val = candidate.full_name.value or ""
    if _JUNK_NAME_RE.match(name_val.strip()):
        candidate.full_name.value = None
        actions.append(f"cleared junk full_name: {name_val!r}")
    elif name_val and len(name_val.split()) == 1 and len(name_val) < 3:
        candidate.full_name.value = None
        actions.append(f"cleared single-char full_name: {name_val!r}")

    # ── 2. Headline trim ──────────────────────────────────────────────────────
    if candidate.headline.value and len(candidate.headline.value) > MAX_HEADLINE_CHARS:
        candidate.headline.value = candidate.headline.value[:MAX_HEADLINE_CHARS].rstrip() + "…"
        actions.append("trimmed headline to 300 chars")

    # ── 3. Emails — deduplicate and validate ──────────────────────────────────
    seen_emails: set = set()
    clean_emails = []
    for entry in candidate.emails:
        key = entry.value.lower().strip()
        if not key or key in seen_emails:
            actions.append(f"removed duplicate/empty email: {entry.value!r}")
            continue
        # Must have @ and a dot after @
        if not re.match(r"^[^@]+@[^@]+\.[^@]{2,}$", key):
            actions.append(f"removed invalid email: {entry.value!r}")
            continue
        seen_emails.add(key)
        clean_emails.append(entry)
    candidate.emails = clean_emails

    # ── 4. Phones — keep only E.164, deduplicate ──────────────────────────────
    seen_phones: set = set()
    clean_phones = []
    for entry in candidate.phones:
        val = (entry.value or "").strip()
        if not val or val in seen_phones:
            continue
        if not _E164_RE.match(val):
            actions.append(f"removed non-E164 phone: {val!r}")
            continue
        seen_phones.add(val)
        clean_phones.append(entry)
    candidate.phones = clean_phones

    # ── 5. Location — reject education strings ────────────────────────────────
    loc = candidate.location
    for field in ("city", "region", "formatted"):
        val = getattr(loc, field, None)
        if val and _EDUCATION_IN_LOCATION_RE.search(str(val)):
            setattr(loc, field, None)
            actions.append(f"cleared education string from location.{field}: {val!r}")
    # Rebuild formatted if it was cleared
    if loc.formatted and (loc.city is None and loc.region is None and loc.country is None):
        loc.formatted = None

    # ── 6. Skills — semantic deduplication ───────────────────────────────────
    seen_skill_keys: set = set()
    clean_skills = []
    for entry in candidate.skills:
        key = entry.normalized or entry.name.lower()
        if key in seen_skill_keys:
            actions.append(f"removed duplicate skill: {entry.name!r}")
            continue
        seen_skill_keys.add(key)
        clean_skills.append(entry)
    candidate.skills = clean_skills

    # ── 7. Experience — remove empty/invalid entries ──────────────────────────
    clean_exp = []
    for entry in candidate.experience:
        # Must have at least company or title
        if not entry.company and not entry.title:
            actions.append("removed experience entry with no company or title")
            continue
        # Title/company must not be a section heading or description blob
        for field in ("company", "title"):
            val = getattr(entry, field, None)
            if val and (len(val) > 100 or _JUNK_NAME_RE.match(val.strip())):
                setattr(entry, field, None)
                actions.append(f"cleared junk experience.{field}: {val[:50]!r}")
        # Trim description
        if entry.summary and len(entry.summary) > MAX_DESCRIPTION_CHARS:
            entry.summary = entry.summary[:MAX_DESCRIPTION_CHARS].rstrip() + "…"
        # Only keep if still has company or title
        if entry.company or entry.title:
            clean_exp.append(entry)
        else:
            actions.append("removed experience entry after cleaning (no valid company/title left)")
    candidate.experience = clean_exp

    # ── 8. Education — remove empty/invalid entries ───────────────────────────
    clean_edu = []
    for entry in candidate.education:
        if not entry.institution and not entry.degree:
            actions.append("removed education entry with no institution or degree")
            continue
        # Institution must not be a CGPA/GPA line
        if entry.institution:
            if re.search(r"\b(cgpa|gpa|\d+\.?\d*/\d+|\d{2,3}%)\b", entry.institution, re.I):
                actions.append(f"cleared CGPA/GPA from institution: {entry.institution!r}")
                entry.institution = None
        if entry.institution or entry.degree:
            clean_edu.append(entry)
        else:
            actions.append("removed education entry after cleaning")
    candidate.education = clean_edu

    # ── 9. Links — deduplicate URLs (case-insensitive, trailing-slash normalised)
    links = candidate.links
    seen_urls: set = set()
    for attr in ("linkedin", "github", "portfolio"):
        val = getattr(links, attr, None)
        if val:
            key = val.lower().rstrip("/")
            if key in seen_urls:
                setattr(links, attr, None)
                actions.append(f"removed duplicate link.{attr}: {val!r}")
            else:
                seen_urls.add(key)
    clean_other = []
    for url in links.other:
        key = url.lower().rstrip("/")
        if key not in seen_urls:
            seen_urls.add(key)
            clean_other.append(url)
        else:
            actions.append(f"removed duplicate other link: {url!r}")
    links.other = clean_other

    # ── 10. Certifications — deduplicate ──────────────────────────────────────
    extras = getattr(candidate.merge_summary, "_extras", {})
    certs  = extras.get("certifications", [])
    seen_certs: set = set()
    clean_certs = []
    for c in certs:
        key = str(c).lower().strip()
        if key and key not in seen_certs:
            seen_certs.add(key)
            clean_certs.append(c)
        elif key:
            actions.append(f"removed duplicate certification: {c!r}")
    extras["certifications"] = clean_certs

    # ── 11. Projects — remove entries with no meaningful name ─────────────────
    projects = extras.get("projects", [])
    clean_projects = []
    seen_proj: set = set()
    for p in projects:
        name = (p.get("name") or "").strip() if isinstance(p, dict) else str(p).strip()
        if not name or len(name) < 3:
            actions.append("removed project with no name")
            continue
        key = name.lower()
        if key in seen_proj:
            actions.append(f"removed duplicate project: {name!r}")
            continue
        seen_proj.add(key)
        clean_projects.append(p)
    extras["projects"] = clean_projects

    return candidate, actions
