"""
Projector — transforms internal CandidateRecord to output dictionary.

Reads the output schema config and applies:
  - Field selection (include/exclude)
  - Path remapping (internal → output field names)
  - Array transformations (sort, take_top_n)
  - Missing value policy (null/omit/error)
  - Confidence/provenance/merge_reason inclusion control
"""
from typing import Any, Dict, List

from data_transformer.schema.canonical import CandidateRecord
from data_transformer.projection.normalizers import apply_normalization


class Projector:
    """
    Projects internal CandidateRecords to output dictionaries based on config.
    Supports both the legacy flat 'fields' array format and the structured
    'field_selection' + 'remapping' format from output_schema.yaml.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        # Support both legacy and new config formats
        self.fields_config = config.get("fields", [])
        self.missing_policy = config.get("on_missing", config.get("missing_value_policy", "null"))
        self.include_conf = config.get("include_confidence", True)
        self.include_prov = config.get("include_provenance", True)
        self.include_merge_reason = config.get("include_merge_reason", True)

        # New format: field_selection.include / exclude
        self.field_include = config.get("field_selection", {}).get("include", [])
        self.field_exclude = set(config.get("field_selection", {}).get("exclude", []))

        # New format: remapping (internal_path -> output_field)
        self.remapping = config.get("remapping", {})

        # New format: transformations (array sorting, top_n, etc.)
        self.transformations = config.get("transformations", {})

    def project(self, candidate: CandidateRecord) -> Dict[str, Any]:
        """Convert CandidateRecord to the final output shape."""
        raw_dict = candidate.model_dump()
        out = {}

        # --- Phase 1: Process explicit fields config (legacy format) ---
        for field_def in self.fields_config:
            dest_path = field_def.get("path")
            if not dest_path:
                continue

            src_path = field_def.get("from", dest_path)
            is_required = field_def.get("required", False)
            norm_type = field_def.get("normalize")

            val = self._get_path(raw_dict, src_path)

            if val is None:
                if is_required and self.missing_policy == "error":
                    raise ValueError(f"Required field missing: {src_path}")
                elif self.missing_policy == "omit":
                    continue
                else:
                    out[dest_path] = None
                    continue

            if norm_type:
                val = apply_normalization(val, norm_type)

            out[dest_path] = val

        # --- Phase 2: Process field_selection.include + remapping (new format) ---
        if self.field_include:
            for field_name in self.field_include:
                if field_name in self.field_exclude:
                    continue
                if field_name in out:
                    continue  # already set by explicit fields config

                # Check if there's a remapping for this field
                if field_name in self.remapping:
                    src_path = self.remapping[field_name]
                    val = self._get_path(raw_dict, src_path)
                    if val is not None:
                        out[field_name] = val
                    elif self.missing_policy == "omit":
                        continue
                    else:
                        out[field_name] = None
                else:
                    # Direct field inclusion from raw_dict
                    val = raw_dict.get(field_name)
                    if val is not None:
                        out[field_name] = val
                    elif self.missing_policy == "omit":
                        continue
                    else:
                        out[field_name] = None

        # --- Phase 3: Apply transformations ---
        for field_name, transform_cfg in self.transformations.items():
            if field_name not in out or not isinstance(out[field_name], list):
                continue

            arr = out[field_name]
            transform_type = transform_cfg.get("transform", "")

            if transform_type == "sort_by_recency":
                # Sort by start_date descending
                arr.sort(key=lambda x: (x.get("start_date") or ""), reverse=True)
            elif transform_type == "take_top_n":
                sort_by = transform_cfg.get("sort_by", "")
                n = transform_cfg.get("n", len(arr))
                if sort_by:
                    arr.sort(key=lambda x: x.get(sort_by, 0) if isinstance(x.get(sort_by, 0), (int, float)) else 0, reverse=True)
                out[field_name] = arr[:n]

        # --- Phase 4: Clean metadata ---
        out = self._clean_metadata(out)

        return out

    def _get_path(self, obj: Any, path: str) -> Any:
        """Naive JSONPath-like resolution (e.g. 'full_name.value', 'emails[0]')."""
        parts = path.replace("]", "").replace("[", ".").split(".")
        current = obj
        for p in parts:
            if not p:
                continue
            if current is None:
                return None

            if isinstance(current, dict):
                current = current.get(p)
            elif isinstance(current, list):
                try:
                    idx = int(p)
                    if idx < len(current):
                        current = current[idx]
                    else:
                        return None
                except ValueError:
                    # e.g. skills[].name
                    # If it's a list, and we're asking for a key, map over the list
                    return [item.get(p) for item in current if isinstance(item, dict) and p in item]
            else:
                return None
        return current

    def _clean_metadata(self, obj: Any) -> Any:
        """Recursively removes confidence/provenance/merge_reason if config says so."""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k == "confidence" and not self.include_conf:
                    continue
                if k == "provenance" and not self.include_prov:
                    continue
                if k == "merge_reason" and not self.include_merge_reason:
                    continue
                cleaned[k] = self._clean_metadata(v)
            return cleaned
        elif isinstance(obj, list):
            return [self._clean_metadata(i) for i in obj]
        return obj
