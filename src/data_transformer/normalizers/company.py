"""
Company name normalization.
"""
import re

# Common corporate suffixes
SUFFIXES = [
    r"\binc\.?\b",
    r"\bllc\.?\b",
    r"\bcorp\.?\b",
    r"\bcorporation\b",
    r"\bltd\.?\b",
    r"\blimited\b",
    r"\bco\.?\b",
    r"\bcompany\b",
]
SUFFIX_PATTERN = re.compile("|".join(SUFFIXES), re.IGNORECASE)


def normalize_company(company: str) -> str:
    """
    Normalize company name by stripping legal suffixes and extra whitespace.
    """
    if not company:
        return ""
        
    # Remove suffixes
    cleaned = SUFFIX_PATTERN.sub("", company)
    
    # Clean punctuation left behind (like trailing commas)
    cleaned = cleaned.strip(",. \t")
    
    # Remove extra spaces
    cleaned = " ".join(cleaned.split())
    
    return cleaned
