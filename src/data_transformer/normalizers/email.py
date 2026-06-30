"""
Email normalization.
"""
import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

def normalize_email(email: str) -> str:
    """
    Normalize email to lowercase and validate format.
    Returns empty string if invalid.
    """
    if not email:
        return ""
        
    cleaned = email.strip().lower()
    
    if EMAIL_RE.match(cleaned):
        return cleaned
        
    return ""
