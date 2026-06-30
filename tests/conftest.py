import pytest
from data_transformer.conflict_resolution.base import SourceValue

@pytest.fixture
def sample_source_values():
    return [
        SourceValue(value="Senior Engineer", source="resume", source_id="1", ingested_at="2025-01-01T00:00:00Z", trust_score=0.8),
        SourceValue(value="SDE III", source="ats", source_id="2", ingested_at="2026-01-01T00:00:00Z", trust_score=0.95),
        SourceValue(value="Senior Software Engineer", source="linkedin", source_id="3", ingested_at="2026-06-01T00:00:00Z", trust_score=0.9),
    ]
