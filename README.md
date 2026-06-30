# DataTransformer — Eightfold-Style Candidate Merging Pipeline

> **Version 2.0** | Production-grade candidate deduplication & merging with LLM-powered conflict resolution.

---

## 🏗 Architecture

```
INPUT SOURCES → ADAPTERS → NORMALIZERS → DEDUP/MATCH → CONFLICT RESOLUTION → PROJECTION → VALIDATION → OUTPUT
```

- **5 Source Adapters**: ATS, LinkedIn, Resume (PDF/DOCX), CSV, Notes
- **6 Field Normalizers**: Phone (E.164), Date (YYYY-MM), Skills taxonomy, Name, Company, Email
- **3-Tier Deduplication**: Exact (email/phone) → Fuzzy (name+company) → Vector similarity
- **5 Conflict Resolvers**: Priority Order, Majority Vote, Latest Wins, Highest Confidence, **🤖 LLM-Powered**
- **Config-Driven Projection**: Field selection, remapping, transformations
- **JSON Schema Validation** + Run-level Quality Report

---

## 🚀 Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run Demo

```bash
dt demo
```

### Merge Sources

```bash
dt merge --input data/samples/ --config config/pipeline_config.yaml --output merged_output.json
```

### Validate Output

```bash
dt validate --input merged_output.json
```

### Quality Report

```bash
dt report --input merged_output.json
```

### Start API Server

```bash
uvicorn data_transformer.api.app:app --reload
# POST http://localhost:8000/v1/merge
```

---

## ⚙️ Configuration

Edit `config/pipeline_config.yaml` to control:

| Setting | Description |
|---------|-------------|
| `conflict_resolver` | `priority_order` \| `majority_vote` \| `latest_wins` \| `highest_confidence` \| `llm` |
| `llm.backend` | `mock` (default) \| `phi3` (requires `pip install -e ".[llm]"`) |
| `dedup.fuzzy_threshold` | Name similarity threshold (default: 0.85) |
| `dedup.enable_vectors` | Vector similarity matching (requires `.[vectors]`) |

---

## 🤖 LLM Conflict Resolution

By default, the **mock LLM resolver** is used — it returns deterministic structured reasoning without any model download.

To use the real **Phi-3-Mini-4K** model:

```bash
pip install -e ".[llm]"
# In config/pipeline_config.yaml:
# conflict_resolver: llm
# llm:
#   backend: phi3
```

---

## 🧪 Tests

```bash
pytest tests/ -v --tb=short
```

---

## 📁 Project Structure

```
DataTransformer/
├── config/                  # Pipeline and output schema configs
├── data/samples/            # Sample input data (5 candidates, 4 sources)
├── src/data_transformer/
│   ├── schema/              # Pydantic canonical schema
│   ├── adapters/            # Source adapters (ATS, LinkedIn, Resume, CSV, Notes)
│   ├── normalizers/         # Field normalizers
│   ├── deduplication/       # Fuzzy + exact matching
│   ├── conflict_resolution/ # 5 pluggable strategies + LLM
│   ├── merger/              # Merge orchestration
│   ├── projection/          # Config-driven output transformation
│   ├── validation/          # JSON Schema validation
│   ├── reporting/           # Quality report generation
│   ├── pipeline/            # End-to-end runner
│   ├── api/                 # FastAPI server
│   └── cli/                 # Typer CLI (dt command)
└── tests/
```
