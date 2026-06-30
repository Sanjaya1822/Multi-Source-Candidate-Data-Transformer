import pytest
from pydantic import ValidationError
from data_transformer.schema.canonical import ExperienceEntry, CandidateRecord
from data_transformer.merger.merge_engine import MergeEngine, MatchGroup
from data_transformer.conflict_resolution import PriorityOrderResolver
from data_transformer.projection.projector import Projector, ProjectorError
from data_transformer.pipeline.runner import PipelineRunner

def test_experience_entry_validation():
    # Valid: not current, end date present
    e = ExperienceEntry(start="2020-01", end="2021-01", is_current=False)
    assert e.end == "2021-01"

    # Valid: is current, no end date
    e2 = ExperienceEntry(start="2020-01", is_current=True)
    assert e2.end is None

    # Invalid: is current, end date present
    with pytest.raises(ValidationError):
        ExperienceEntry(start="2020-01", end="2021-01", is_current=True)

def test_experience_overlap_and_promotion_merge():
    # Setup mock merge engine
    engine = MergeEngine(
        default_resolver=PriorityOrderResolver({}),
        field_overrides={},
        trust_scores={"resume": 1.0}
    )
    
    # Mock records
    from data_transformer.schema.canonical import RawRecord
    r1 = RawRecord(source="resume", fields={"experience": [
        {"company": "TechCorp Inc.", "title": "Software Engineer", "start_date": "2020-01", "end_date": "2022-01"}
    ]})
    r2 = RawRecord(source="resume", fields={"experience": [
        {"company": "TechCorp", "title": "Senior Software Engineer", "start_date": "2021-06", "end_date": "2023-01"}
    ]})
    group = MatchGroup()
    group.add(r1)
    group.add(r2)
    
    # Merge
    merged = engine._merge_experience(group)
    
    # Should merge into 1 entry due to overlapping dates and same normalized company
    assert len(merged) == 1
    assert merged[0].company.startswith("TechCorp")
    assert merged[0].title == "Senior Software Engineer" # the promotion
    assert merged[0].start == "2020-01" # earliest start
    assert merged[0].end == "2023-01" # latest end

def test_confidence_rounding():
    proj = Projector({"confidence_precision": 2})
    res = proj._round_confidence({"overall_confidence": 0.99749999}, 2)
    assert res["overall_confidence"] == 1.0  # 0.997 rounded to 2 decimal places is 1.00

def test_pipeline_config_validation():
    # Invalid field override
    with pytest.raises(ValueError, match="ConfigError: field 'invalid_field'"):
        PipelineRunner(
            {"field_resolver_overrides": {"invalid_field": "majority_vote"}},
            {}
        )
    
    # Invalid resolver
    with pytest.raises(ValueError, match="ConfigError: invalid resolver 'magic_resolver'"):
        PipelineRunner(
            {"field_resolver_overrides": {"full_name": "magic_resolver"}},
            {}
        )

def test_projector_config_validation():
    # Duplicate path
    with pytest.raises(ProjectorError, match="ConfigError: duplicate output mapping for path 'name'"):
        Projector({"renames": [{"from": "full_name", "path": "name"}, {"from": "headline", "path": "name"}]})

    # Invalid field request
    with pytest.raises(ProjectorError, match="ConfigError: field 'magic_field'"):
        Projector({"fields": ["magic_field"]})
