import re

def normalize_e164(phone: str) -> str:
    """Normalizes a phone string to E.164 format roughly."""
    if not phone:
        return phone
    # Strip non-digits
    digits = re.sub(r'\D', '', phone)
    if not digits:
        return phone
    # Basic assumption: if it starts with 1, it's US +1, if not, assume US for this example
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) > 10:
        return f"+{digits}"
    return phone

def normalize_canonical_skills(skills) -> list:
    """Normalizes skills by lowercasing and deduping."""
    if not skills:
        return []
    
    normalized = []
    seen = set()
    
    if isinstance(skills, str):
        skills = [skills]
        
    for s in skills:
        # if skill is a dict (like our canonical skill schema), extract name
        if isinstance(s, dict) and "name" in s:
            name = s["name"]
        else:
            name = str(s)
            
        lower_name = name.lower().strip()
        if lower_name and lower_name not in seen:
            seen.add(lower_name)
            normalized.append(lower_name)
            
    return normalized

def apply_normalization(value, norm_type):
    if not value or not norm_type:
        return value
        
    norm_type = norm_type.lower()
    
    if norm_type == "e164":
        return normalize_e164(str(value))
    elif norm_type == "canonical":
        return normalize_canonical_skills(value)
        
    return value
