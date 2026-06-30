"""Tests for projection and transformations."""
from data_transformer.schema.canonical import CandidateRecord, FieldValue, EmailEntry
from data_transformer.projection.projector import Projector

def test_projector_basic_remapping():
    cand = CandidateRecord(candidate_id="123")
    cand.full_name = FieldValue(value="John Doe", confidence=1.0)
    cand.emails = [EmailEntry(value="john@example.com", is_primary=True, confidence=0.9)]
    
    config = {
        "field_selection": {"include": ["candidate_id", "full_name", "emails"]},
        "remapping": {
            "full_name.value": "name",
            "emails[0].value": "primary_email"
        },
        "include_confidence": False,
        "include_provenance": False
    }
    
    projector = Projector(config)
    res = projector.project(cand)
    
    assert res["candidate_id"] == "123"
    assert res["name"] == "John Doe"
    assert res["primary_email"] == "john@example.com"
    assert "confidence" not in str(res)
