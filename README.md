# Multi-Source Candidate Data Transformer

This project implements a robust candidate data transformation pipeline that ingests candidate information from ATS JSON, Recruiter CSV, Resume (PDF/DOCX/TXT), and Recruiter Notes (TXT). It automatically identifies and clusters candidate records, merges conflicting information using configurable resolution strategies, and generates standardized, schema-validated JSON output with normalization, deduplication, provenance tracking, confidence scoring, and quality reporting.

<img width="1919" height="972" alt="Screenshot 2026-06-30 215558" src="https://github.com/user-attachments/assets/b4416e92-003f-4809-9bfc-3b82c73ec5fc" />
<img width="1919" height="918" alt="Screenshot 2026-06-30 215816" src="https://github.com/user-attachments/assets/7ea7dbf1-3c6f-4ee1-97b3-02472a28df59" />
<img width="1919" height="974" alt="Screenshot 2026-06-30 220036" src="https://github.com/user-attachments/assets/c1d93bae-d7a6-426f-9c51-10b047102139" />

# Features

__Multi-Source Data Ingestion__: Supports ATS JSON, Recruiter CSV, Resume (PDF/DOCX/TXT), and Recruiter Notes (TXT).
__Automatic Candidate Clustering__: Identifies and groups records belonging to the same candidate using identity resolution.
__Canonical Data Normalization__: Standardizes emails, phone numbers (E.164), dates (YYYY-MM), locations, and skill names into a unified schema.
__Intelligent Merge Engine__: Deduplicates records and merges candidate data using configurable conflict resolution strategies (Highest Confidence, Majority Vote, Latest Wins, Priority Order).
__Configurable Projection Layer__: Dynamically transforms canonical candidate profiles into user-defined, schema-compliant JSON output at runtime.
__Provenance & Confidence Tracking__: Records the source, extraction method, and confidence score for every merged field to ensure transparency and explainability.
__Validation & Quality Reporting__: Performs schema validation, detects invalid or conflicting data, and generates comprehensive quality reports.
__Batch Processing__: Efficiently processes large collections of candidate files, automatically generating separate canonical profiles for each unique candidate.
__Interactive Streamlit Interface__: Provides an intuitive web-based interface for uploading files, configuring output, and viewing merged candidate profiles.

# System Architecture

<img width="1051" height="1497" alt="Systemarchitecture" src="https://github.com/user-attachments/assets/122ad904-6b17-4dc1-9490-c396995eb7cb" />

# Live Demo

Try the deployed application:

__Live Application__: https://multi-source-candidate-data-transformer.streamlit.app/

__Installation (Run Locally)__

Ensure you have Python 3.11+ installed.

__Clone the repository__:

git clone https://github.com/Sanjaya1822/Multi-Source-Candidate-Data-Transformer.git
cd Multi-Source-Candidate-Data-Transformer

__Install the required dependencies__:

pip install -r requirements.txt

__Launch the application__:

streamlit run app.py

The application will be available at http://localhost:8501.

# Usage

The application supports ATS JSON, Recruiter CSV, Resume (PDF/DOCX/TXT), and Recruiter Notes (TXT).

Upload one or more files, optionally configure the output projection, and click Run Pipeline. The system automatically:

Extracts candidate information
Identifies and clusters unique candidates
Normalizes and validates data
Merges related records
Generates canonical JSON profiles
Produces quality reports and downloadable outputs

# Runtime Configuration

The pipeline supports dynamic runtime configuration through an interactive Projection Builder. Users can customize the output schema without modifying the backend by:

Selecting the fields to include in the output.
Renaming output fields.
Toggling Confidence and Provenance.
Configuring the Missing Value Policy (omit, null, or error).
Applying field-specific normalizations (e.g., E.164 for phone numbers and canonical skill names).

The application automatically generates the corresponding Configuration JSON and Output Schema JSON, which users can review and modify before executing the pipeline.

**Example**:

```json
{
  "fields": ["full_name", "emails", "skills"],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "omit"
}
```
__Missing Value Policies__
omit – Exclude missing fields.
null – Include missing fields with null.
error – Stop execution and report a validation error.

# Testing

Run the automated test suite using pytest:

```bash
pytest tests/ -v
```

The tests validate the core pipeline, including data extraction, normalization, candidate clustering, conflict resolution, projection, and batch processing.

