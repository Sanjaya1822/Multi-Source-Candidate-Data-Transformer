# Task Progress - All Issues Fixed ✅

## Completed Fixes:

### 🔴 CRITICAL
- [x] **GitHubAdapter** - Fixed wrong `RawRecord` constructor. Was using `source_type`, `full_name`, `emails`, `phones`, `skills`, `experience`, `education`, `raw_data`, `metadata` as kwargs — none of which exist on `RawRecord`. Now properly uses `source`, `source_id`, `ingested_at`, and `fields` dict matching the canonical schema.

### 🔴 CRITICAL
- [x] **Projector** - Fixed to properly read `output_schema.yaml` config format. The YAML uses `field_selection.include`, `remapping`, `transformations`, `missing_value_policy` but the projector was only reading `fields`, `on_missing`, `include_confidence`, `include_provenance`. Now supports both formats.

### 🟡 MEDIUM
- [x] **MergeEngine._merge_skills()** - Added `_round_confidence()` to round skill confidences to 4 decimal places, eliminating floating-point artifacts like `0.9974999999999999` and `0.9450000000000001`.

### 🟡 MEDIUM
- [x] **MergeEngine._merge_experience()** - Improved to merge overlapping entries at the same company:
  - Normalizes company names (strips "Inc.", "Corp.", etc.) for fuzzy grouping
  - Merges provenances from all sources
  - Uses earliest start_date, latest end_date
  - Fixes `is_current`/`end_date` semantic inconsistency (null end_date + not current → mark as current)
  - Boosts confidence for cross-source agreement

### 🟡 MEDIUM
- [x] **MergeEngine._merge_phones()** - Added confidence boost for duplicate phones (same pattern as emails already had). When a phone appears in multiple sources, confidence gets a 1.1x boost.

### 🟢 MINOR
- [x] **MergeEngine._calculate_overall_confidence()** - Added rounding to 4 decimal places to avoid floating-point artifacts in overall confidence.

### 🟢 MINOR
- [x] **output_schema.yaml** - Fixed remapping format. Was using `"full_name.value": "name"` (internal→output) but the projector reads `"name": "full_name.value"` (output→internal). Now correctly maps output field names to internal JSONPath expressions.

### 🟢 MINOR
- [x] **All Conflict Resolvers** - Added `round(confidence, 4)` to all resolvers (HighestConfidence, MajorityVote, LatestWins, PriorityOrder, MockLLM, PhiLLM) to ensure consistent 4-decimal precision throughout the pipeline.

### 🟢 MINOR
- [x] **HighestConfidenceResolver** - Removed unused `Counter` import. Extracted `_to_hashable()` to module level for reuse.
