# Multi-Source Candidate Data Transformer

A robust, enterprise-grade data pipeline for merging candidate profiles across multiple disparate sources. This project is the submission for the **Eightfold Engineering Intern Assignment**.

## Key Features

- **Multi-Source Support:** Ingests data from 6 independent sources:
  1. ATS Exports (Structured JSON)
  2. Recruiter CSVs (Structured)
  3. LinkedIn Profiles (Structured JSON)
  4. Resumes (Unstructured PDF/DOCX/TXT)
  5. GitHub URLs (API Fetching)
  6. Recruiter Notes (Unstructured TXT)
- **Deterministic Deduplication:** Merges identical candidates across sources using RapidFuzz name-matching and contact overlap heuristics.
- **Conflict Resolution Engine:** Configurable field-level resolvers (`majority_vote`, `latest_wins`, `priority_order`, `highest_confidence`, and `llm`).
- **Rich Provenance Tracking:** Every merged field tracks its origin source, extraction method, pre-normalized raw value, confidence score, and selection reasoning.
- **Quality Reporting:** Generates a comprehensive pipeline execution report including validation warnings, confidence distributions, and extraction statistics.
- **Dynamic Schema Projection:** Internal data uses a strict canonical schema, which is dynamically projected into any requested output format via JSON Path configuration.

## Architecture Overview

The pipeline strictly adheres to the requested architecture:

```text
Input Sources → Source Detection → Extractors (Adapters)
  ↓
Raw Records → Normalization (Emails, Phones, Skills)
  ↓
Deduplication Matcher
  ↓
Merge Engine (Conflict Resolution)
  ↓
Canonical Candidate Records (with Provenance)
  ↓
Projection Layer & Validation
  ↓
Final JSON Output + Quality Report
```

## Running the Project

### Prerequisites
- Python 3.9+
- Poetry (or standard pip)

### Installation
```bash
pip install -r requirements.txt
```

### Start the Server
```bash
python -m uvicorn data_transformer.api.app:app --reload
```
Navigate to `http://localhost:8000/ui/index.html` to access the Pipeline UI.

## Usage Guide (UI)

The UI is divided into 3 columns:

1. **Configuration**: Edit the JSON configuration for deduplication, conflict resolution, and the output schema.
2. **Data Sources**: Upload files or paste URLs for the 6 supported sources. Any combination of sources is supported.
3. **Results**: View the merged JSON profiles and the comprehensive Quality Report. Use the Copy or Download buttons to export the data.

### Sample Files
The project includes sample fixtures in `tests/fixtures/` and sample unstructured files in `samples/` that you can upload to test the pipeline.

## Trust Scores & Extraction Methods

| Source | Input Type | Extraction Method | Trust Score |
|---|---|---|---|
| ATS | `.json` | Structured Parser | 0.95 |
| Recruiter CSV | `.csv` | Structured Parser | 0.90 |
| LinkedIn Data | `.json` | Structured Parser | 0.88 |
| GitHub | URL | API Fetch (Repos & Bio) | 0.80 |
| Resume | PDF/DOCX/TXT | Regex Extraction | 0.75 |
| Recruiter Notes| `.txt` | Regex Extraction | 0.60 |
| LinkedIn URL | URL | Stub (Link Only) | 0.30 |

*Note: LinkedIn profile scraping is stubbed out to respect LinkedIn's Terms of Service. The adapter validates the URL and stores it as a confirmed link without attempting unauthorized scraping.*
