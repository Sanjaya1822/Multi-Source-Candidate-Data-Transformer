"""
Runtime Projection Layer.

Transforms the canonical CandidateRecord into the final output dictionary
using dynamic configuration mapping rules (field selection, renaming, normalization).
"""
from typing import Any, Dict, List

from data_transformer.schema.canonical import CandidateRecord
from data_transformer.normalizers import (
    normalize_phone,
)
from data_transformer.normalizers.skills import normalize_skill


class ProjectorError(Exception):
    pass


class Projector:
    """
    Projects a CandidateRecord dynamically based on runtime configuration.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.fields = self.config.get("fields", [])
        
        # Valid fields logic
        canonical_fields = set(CandidateRecord.model_fields.keys())
        canonical_fields.update({"projects", "certifications"}) # From _extras
        
        if self.fields:
            for f in self.fields:
                fname = f.get("from", f.get("path", "")).split(".")[0] if isinstance(f, dict) else f
                if fname and fname not in canonical_fields and not fname.startswith("provenance") and not fname.startswith("candidate_id") and not fname.startswith("overall_confidence"):
                    raise ProjectorError(f"ConfigError: field '{fname}' requested in projection does not exist in canonical schema.")
                    
        self.renames = {}
        target_paths = set()
        for r in self.config.get("renames", []):
            if isinstance(r, dict) and "from" in r and "path" in r:
                rfrom = r["from"].split(".")[0]
                if rfrom not in canonical_fields:
                    raise ProjectorError(f"ConfigError: rename source '{r['from']}' does not exist.")
                if r["path"] in target_paths:
                    raise ProjectorError(f"ConfigError: duplicate output mapping for path '{r['path']}'.")
                self.renames[rfrom] = r["path"]
                target_paths.add(r["path"])
            
        self.normalizations = self.config.get("normalizations", {})
        self.include_confidence = self.config.get("include_confidence", False)
        self.include_provenance = self.config.get("include_provenance", False)
        self.on_missing = self.config.get("on_missing", "omit")  # null, omit, error

    def _get_raw_value(self, candidate: CandidateRecord, field: str) -> Any:
        # Helper to extract scalar or array from CandidateRecord
        if field == "candidate_id":
            return candidate.candidate_id
        if field == "full_name":
            return candidate.full_name.value
        if field == "headline":
            return candidate.headline.value
        if field == "years_experience":
            return candidate.years_experience.value
        if field == "emails":
            return [
                {
                    "value": e.value,
                    "is_primary": e.is_primary,
                    **({"confidence": e.confidence} if self.include_confidence else {})
                }
                for e in candidate.emails if e.value
            ]
        if field == "phones":
            res = []
            for p in candidate.phones:
                if not p.value: continue
                val = p.value
                # Apply normalization if configured
                if self.normalizations.get("phones") == "E164":
                    val = normalize_phone(val) or val
                d = {
                    "value": val,
                    "is_primary": p.is_primary,
                    **({"confidence": p.confidence} if self.include_confidence else {})
                }
                if p.type: d["type"] = p.type
                res.append(d)
            return res
        if field == "location":
            loc = candidate.location
            if not loc:
                return None
            if not loc.city and not loc.region and not loc.country:
                return loc.formatted if loc.formatted else None
            out = {}
            if loc.city: out["city"] = loc.city
            if loc.region: out["region"] = loc.region
            if loc.country: out["country"] = loc.country
            if loc.formatted: out["formatted"] = loc.formatted
            return out
        if field == "links":
            links = candidate.links
            if not links.linkedin and not links.github and not links.portfolio and not links.other:
                return None
            out = {}
            if links.linkedin: out["linkedin"] = links.linkedin
            if links.github: out["github"] = links.github
            if links.portfolio: out["portfolio"] = links.portfolio
            out["other"] = links.other if links.other else []
            return out
        if field == "skills":
            res = []
            for s in candidate.skills:
                if not s.name: continue
                val = s.name
                if self.normalizations.get("skills") == "canonical":
                    val = normalize_skill(val) or val
                res.append({
                    "name": val,
                    "sources": s.sources,
                    **({"confidence": s.confidence} if self.include_confidence else {})
                })
            return res
        if field == "experience":
            res = []
            for e in candidate.experience:
                if not e.company and not e.title: continue
                d = {}
                if e.company: d["company"] = e.company
                if e.title: d["title"] = e.title
                if e.start: d["start"] = e.start
                if e.end: d["end"] = e.end
                d["is_current"] = e.is_current
                if e.summary: d["summary"] = e.summary
                res.append(d)
            return res
        if field == "education":
            res = []
            for e in candidate.education:
                if not e.institution and not e.degree: continue
                d = {}
                if e.institution: d["institution"] = e.institution
                if e.degree: d["degree"] = e.degree
                if e.field: d["field_of_study"] = e.field
                if e.end_year: d["end_date"] = f"{e.end_year}-01"
                res.append(d)
            return res
        if field == "projects":
            if hasattr(candidate.merge_summary, "_extras"):
                return candidate.merge_summary._extras.get("projects", [])
            return []
        if field == "certifications":
            if hasattr(candidate.merge_summary, "_extras"):
                return candidate.merge_summary._extras.get("certifications", [])
            return []
        return None

    def project(self, candidate: CandidateRecord) -> Dict[str, Any]:
        """Convert a CandidateRecord to the dynamic configuration shape."""
        out: Dict[str, Any] = {
            "candidate_id": candidate.candidate_id,
        }

        # Determine which fields to include
        target_fields = []
        if self.fields:
            for f in self.fields:
                if isinstance(f, dict):
                    target_fields.append(f.get("from", f.get("path")))
                else:
                    target_fields.append(f)
        else:
            target_fields = [
                "full_name", "emails", "phones", "location", "links", 
                "headline", "years_experience", "skills", "experience", "education"
            ]

        for field in target_fields:
            if not field or field.startswith("candidate_id") or field.startswith("provenance") or field.startswith("overall_confidence"):
                continue
                
            # Basic path resolution for 'from'
            base_field = field.split(".")[0]
            
            raw_val = self._get_raw_value(candidate, base_field)
            out_key = self.renames.get(base_field, base_field)
            
            if raw_val is None or (isinstance(raw_val, (list, dict, str)) and not raw_val):
                if self.on_missing == "error":
                    raise ProjectorError(f"Missing required field: {base_field}")
                elif self.on_missing == "null":
                    out[out_key] = None
                # if "omit", do nothing
            else:
                out[out_key] = raw_val

        if self.include_confidence:
            out["overall_confidence"] = candidate.overall_confidence

        if self.include_provenance:
            prov = self._flatten_provenance(candidate)
            if prov:
                out["provenance"] = prov

        # Validate that the final output doesn't drop the entire profile
        valid_keys = [k for k in out.keys() if k != "candidate_id" and out[k] is not None and out[k] != []]
        if not valid_keys:
             raise ProjectorError("Generated profile is completely empty")
             
        precision = self.config.get("confidence_precision", 4)
        out = self._round_confidence(out, precision)

        return out
        
    def _round_confidence(self, obj: Any, precision: int) -> Any:
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                if k in ("confidence", "overall_confidence") and isinstance(v, (float, int)):
                    new_dict[k] = round(float(v), precision)
                else:
                    new_dict[k] = self._round_confidence(v, precision)
            return new_dict
        elif isinstance(obj, list):
            return [self._round_confidence(i, precision) for i in obj]
        else:
            return obj

    def _flatten_provenance(self, candidate: CandidateRecord) -> List[Dict[str, str]]:
        """Extract all internal per-field provenance lists into the global list format."""
        prov_out = []
        
        def _add(prov_list, field_name):
            for p in prov_list:
                prov_out.append({
                    "field": field_name,
                    "source": p.source,
                    "method": p.method or "unknown"
                })

        _add(candidate.full_name.provenance, "full_name")
        _add(candidate.headline.provenance, "headline")
        _add(candidate.years_experience.provenance, "years_experience")
        _add(candidate.location.provenance, "location")
        _add(candidate.links.provenance, "links")
        
        for i, e in enumerate(candidate.emails):
            _add(e.provenance, f"emails[{i}]")
        for i, p in enumerate(candidate.phones):
            _add(p.provenance, f"phones[{i}]")
        for i, s in enumerate(candidate.skills):
            _add(s.provenance, f"skills[{i}]")
        for i, e in enumerate(candidate.experience):
            _add(e.provenance, f"experience[{i}]")
        for i, e in enumerate(candidate.education):
            _add(e.provenance, f"education[{i}]")
            
        seen = set()
        unique_prov = []
        for p in prov_out:
            key = (p["field"], p["source"], p["method"])
            if key not in seen:
                seen.add(key)
                unique_prov.append(p)
                
        return unique_prov
