"""Tests for projection and transformations."""
from data_transformer.schema.canonical import CandidateRecord, FieldValue, EmailEntry
from data_transformer.projection.projector import Projector

def test_projector_basic_eightfold():
    cand = CandidateRecord(candidate_id="123")
    cand.full_name = FieldValue(value="John Doe", confidence=1.0)
    cand.emails = [EmailEntry(value="john@example.com", is_primary=True, confidence=0.9)]

    config = {"include_confidence": True}
    projector = Projector(config)
    res = projector.project(cand)

    assert res["candidate_id"] == "123"
    assert res["full_name"] == "John Doe"
    assert res["emails"][0]["value"] == "john@example.com"
    assert res["emails"][0]["is_primary"] is True
    assert res["emails"][0]["confidence"] == 0.9

def test_projector_missing_fields_omit():
    cand = CandidateRecord(candidate_id="456")
    cand.full_name = FieldValue(value="Jane Doe")
    config = {
        "fields": ["full_name", "emails", "location"],
        "on_missing": "omit"
    }
    projector = Projector(config)
    res = projector.project(cand)
    assert "full_name" in res
    assert "emails" not in res
    assert "location" not in res

def test_projector_missing_fields_null():
    cand = CandidateRecord(candidate_id="456")
    cand.full_name = FieldValue(value="Jane Doe")
    config = {
        "fields": ["full_name", "emails", "location"],
        "on_missing": "null"
    }
    projector = Projector(config)
    res = projector.project(cand)
    assert res["emails"] is None
    assert res["location"] is None

def test_projector_nested_objects():
    from data_transformer.schema.canonical import LocationEntry
    cand = CandidateRecord(candidate_id="789")
    cand.location = LocationEntry(city="Chennai", country="IN")
    config = {
        "fields": ["location"],
        "on_missing": "omit"
    }
    res = Projector(config).project(cand)
    assert "location" in res
    assert res["location"]["city"] == "Chennai"
    assert res["location"]["country"] == "IN"
    assert "region" not in res["location"]

def test_projector_renames():
    cand = CandidateRecord(candidate_id="abc")
    cand.full_name = FieldValue(value="Bob Smith")
    config = {
        "fields": ["full_name"],
        "renames": [{"from": "full_name", "path": "candidate_name"}]
    }
    res = Projector(config).project(cand)
    assert "candidate_name" in res
    assert res["candidate_name"] == "Bob Smith"
    assert "full_name" not in res

def test_projector_partial_selection():
    cand = CandidateRecord(candidate_id="abc")
    cand.full_name = FieldValue(value="Bob Smith")
    cand.headline = FieldValue(value="Engineer")
    config = {
        "fields": ["full_name"]
    }
    res = Projector(config).project(cand)
    assert "full_name" in res
    assert "headline" not in res

def test_projector_toggles():
    cand = CandidateRecord(candidate_id="abc")
    cand.full_name = FieldValue(value="Bob Smith", confidence=0.8)
    cand.emails = [EmailEntry(value="bob@example.com", confidence=0.7)]
    config = {
        "fields": ["emails"],
        "include_confidence": False,
        "include_provenance": False
    }
    res = Projector(config).project(cand)
    assert "confidence" not in res["emails"][0]
