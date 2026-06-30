# Eightfold Engineering Intern - Assignment
## Step 1 - Technical Design

### Pipeline Architecture
The pipeline follows a modular ETL and deduplication pattern:
1. **Detect**: System detects file types based on file extension and/or naming conventions (e.g., `.csv` -> CSV Adapter, `ats.json` -> ATS Adapter, `github` -> GitHub Adapter).
2. **Extract**: Source Adapters extract fields from raw documents, mapping them into an intermediate `RawRecord`.
3. **Normalize (Input Level)**: During extraction, obvious fields are normalized (e.g., standardizing experience end-dates to "Present" if empty). 
4. **Merge (Deduplication & Conflict Resolution)**: `RawRecords` are matched. If they belong to the same candidate, a `MergeEngine` creates a canonical `CandidateRecord`. Conflict resolvers determine which source wins field conflicts (e.g., via `highest_confidence` or `priority_order` based on source trust).
5. **Project-to-Output**: A config-driven `Projector` transforms the canonical internal record into the final user-requested JSON schema, applying dynamic field selection, renaming (`from` key), and output normalizers (e.g., `E164`, `canonical`).
6. **Validate**: The final dictionary is emitted as the JSON output.

### Canonical Schema & Normalization Formats
Internally, the `CandidateRecord` stores normalized, strictly-typed Pydantic fields:
- `phones`: E.164 strings.
- `skills`: Normalized arrays of lowercase deduplicated strings.
- `experience`: List of objects with `YYYY-MM` dates.
- `location`: Standardized text (City, Region, Country).
- `provenance` & `confidence`: Tracked at the field level for trace-ability.

### Merge & Conflict Resolution Policy
- **Keys for Match**: Primarily matches via Exact Match (Email, Phone) and Fuzzy Match (Name + Company / Title).
- **Resolver**: The system defaults to `highest_confidence` or `priority_order`. 
- **Confidence Assignment**: Adapters define base trust scores (e.g., GitHub = 0.98, ATS = 0.95, LinkedIn = 0.90). A field's confidence is derived from the source's trust score. If multiple sources agree, confidence is boosted.

### Runtime Custom Output Config (Projection)
The `Projector` uses the requested runtime JSON configuration. 
- It iterates through the `"fields"` array.
- Uses JSONPath-like resolution to pull data from the canonical object using the `"from"` key.
- Applies standard functions if `"normalize"` is requested.
- Applies the `"on_missing"` policy (`null`, `omit`, or `error`) on missing data.

### Edge Cases Handled
1. **Incomplete/Missing Name from GitHub**: Handled by falling back to the GitHub username (`login`).
2. **Missing Essential Data causing Errors**: Handled strictly via the `"on_missing"` policy in the projection layer. If a field is `"required": true` and `"on_missing": "error"`, it halts and reports; otherwise gracefully uses `null` or omits.
3. **Array Flattening Requests**: If user asks for `"from": "emails[0]"`, the projector dynamically extracts the first element instead of crashing if multiple emails exist.

*Note: For the sake of the assignment constraints, we rely on rule-based NLP extraction rather than external LLMs for robust scale without arbitrary costs.*
