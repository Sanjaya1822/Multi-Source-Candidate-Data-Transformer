"""Tests for normalizers."""
from data_transformer.normalizers import (
    normalize_phone, normalize_date, normalize_skill, 
    normalize_name, normalize_company, normalize_email
)

def test_normalize_phone():
    assert normalize_phone("(415) 555-1234") == "+14155551234"
    assert normalize_phone("+1 415-555-1234") == "+14155551234"
    assert normalize_phone("invalid") is None

def test_normalize_date():
    assert normalize_date("Jan 2020") == "2020-01"
    assert normalize_date("2020") == "2020-01"
    assert normalize_date("01/2020") == "2020-01"
    assert normalize_date("invalid") is None

def test_normalize_skill():
    assert normalize_skill("js") == "JavaScript"
    assert normalize_skill("PYTHON") == "Python"
    assert normalize_skill("reactjs") == "React"
    assert normalize_skill("unknown_skill") == "Unknown_Skill"

def test_normalize_name():
    assert normalize_name(" john doe ") == "John Doe"
    assert normalize_name("JANE SMITH") == "Jane Smith"

def test_normalize_company():
    assert normalize_company("TechCorp Inc.") == "TechCorp"
    assert normalize_company("Google LLC") == "Google"
    assert normalize_company("Startup Co") == "Startup"

def test_normalize_email():
    assert normalize_email(" John.Doe@Example.com ") == "john.doe@example.com"
    assert normalize_email("invalid") == ""
