"""Tests for deduplication matcher."""
from data_transformer.deduplication.matcher import Matcher
from data_transformer.schema.canonical import RawRecord

def test_exact_email_match():
    r1 = RawRecord(source="ats", fields={"full_name": "John Doe", "emails": ["john@example.com"]})
    r2 = RawRecord(source="linkedin", fields={"full_name": "John Doe", "emails": ["john@example.com"]})
    r3 = RawRecord(source="csv", fields={"full_name": "Jane Smith", "emails": ["jane@example.com"]})
    
    matcher = Matcher()
    groups = matcher.match([r1, r2, r3])
    
    assert len(groups) == 2
    assert len(groups[0].records) == 2  # John Doe merged
    assert len(groups[1].records) == 1  # Jane Smith separate

def test_fuzzy_name_match():
    r1 = RawRecord(source="ats", fields={"full_name": "Jonathan Doe", "emails": ["john1@example.com"]})
    r2 = RawRecord(source="linkedin", fields={"full_name": "John Doe", "emails": ["john2@example.com"]})
    
    matcher = Matcher(fuzzy_threshold=80.0)
    groups = matcher.match([r1, r2])
    
    assert len(groups) == 1  # Should merge due to high fuzzy similarity
    
def test_name_company_match():
    # Names are somewhat different but companies match
    r1 = RawRecord(source="ats", fields={"full_name": "J. Doe", "experience": [{"company": "Google"}]})
    r2 = RawRecord(source="linkedin", fields={"full_name": "John Doe", "experience": [{"company": "Google LLC"}]})
    
    matcher = Matcher(name_company_threshold=70.0)
    groups = matcher.match([r1, r2])
    
    assert len(groups) == 1
