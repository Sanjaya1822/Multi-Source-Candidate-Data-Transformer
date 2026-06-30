"""
Skills normalization.
"""
from typing import Optional
from rapidfuzz import fuzz, process

# A very basic taxonomy for demonstration
SKILL_TAXONOMY = {
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "python": "Python",
    "py": "Python",
    "go": "Go",
    "golang": "Go",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "Google Cloud",
    "google cloud platform": "Google Cloud",
    "c++": "C++",
    "cpp": "C++",
}

# The canonical names to match against
CANONICAL_SKILLS = list(set(SKILL_TAXONOMY.values()))

def normalize_skill(skill_name: str, fuzzy_threshold: float = 85.0) -> str:
    """
    Normalize skill name to a canonical form.
    Returns the canonical name if found in taxonomy or via fuzzy match.
    Otherwise returns the title-cased original string.
    """
    if not skill_name:
        return ""
        
    clean_name = skill_name.strip().lower()
    
    # 1. Exact match in taxonomy aliases
    if clean_name in SKILL_TAXONOMY:
        return SKILL_TAXONOMY[clean_name]
        
    # 2. Exact match in canonical list (case insensitive)
    for canonical in CANONICAL_SKILLS:
        if clean_name == canonical.lower():
            return canonical
            
    # 3. Fuzzy match against canonical list
    result = process.extractOne(clean_name, CANONICAL_SKILLS, scorer=fuzz.ratio)
    if result:
        match, score, _ = result
        if score >= fuzzy_threshold:
            return match
            
    # 4. Fallback: title case the original
    # Special casing for acronyms could go here
    return skill_name.strip().title()
