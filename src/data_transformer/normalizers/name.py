"""
Name normalization.
"""

def normalize_name(name: str) -> str:
    """
    Normalize name to Title Case and clean up whitespace.
    """
    if not name:
        return ""
        
    # Clean extra whitespace
    cleaned = " ".join(name.split())
    
    # Title case (can be improved to handle O'Connor, etc.)
    return cleaned.title()
