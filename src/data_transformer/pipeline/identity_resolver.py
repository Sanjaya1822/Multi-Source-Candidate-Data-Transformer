"""
Identity Resolution module.
Scores pairwise candidate identity using deterministic and fuzzy heuristics.
"""
from typing import Dict, Any, List
from rapidfuzz import fuzz

from data_transformer.schema.canonical import RawRecord

def compute_identity_score(record_a: RawRecord, record_b: RawRecord) -> float:
    """
    Compute an identity score from 0.0 to 100.0 between two raw records.
    """
    fields_a = record_a.fields
    fields_b = record_b.fields

    # 1. Deterministic Hard Matches (100% confidence)
    # Exact email match
    emails_a = set(fields_a.get("emails", []))
    emails_b = set(fields_b.get("emails", []))
    if emails_a and emails_b and not emails_a.isdisjoint(emails_b):
        return 100.0
        
    # Exact phone match (E164 normalized)
    phones_a = set(fields_a.get("phones", []))
    phones_b = set(fields_b.get("phones", []))
    if phones_a and phones_b and not phones_a.isdisjoint(phones_b):
        return 100.0
        
    # Exact GitHub match
    links_a = [l.get("url", "") for l in fields_a.get("links", []) if l.get("type") == "github"]
    links_b = [l.get("url", "") for l in fields_b.get("links", []) if l.get("type") == "github"]
    if links_a and links_b and not set(links_a).isdisjoint(set(links_b)):
        return 100.0
        
    # 2. Fuzzy Matching (up to 100%)
    score = 0.0
    
    # Name (up to 85%)
    name_a = fields_a.get("full_name")
    name_b = fields_b.get("full_name")
    
    name_score = 0.0
    if name_a and name_b:
        name_a_str = str(name_a).lower()
        name_b_str = str(name_b).lower()
        ratio = fuzz.token_sort_ratio(name_a_str, name_b_str)
        name_score = (ratio / 100.0) * 85.0
        
    score += name_score
    
    # Location (up to 15%)
    loc_a = fields_a.get("location")
    loc_b = fields_b.get("location")
    
    loc_score = 0.0
    if loc_a and loc_b and isinstance(loc_a, dict) and isinstance(loc_b, dict):
        city_a = loc_a.get("city", "").lower()
        city_b = loc_b.get("city", "").lower()
        country_a = loc_a.get("country", "").lower()
        country_b = loc_b.get("country", "").lower()
        
        if city_a and city_b and city_a == city_b:
            loc_score = 15.0
        elif country_a and country_b and country_a == country_b:
            loc_score = 5.0
            
    score += loc_score
    
    return min(100.0, score)
