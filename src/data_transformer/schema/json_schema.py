"""
JSON Schema for output validation.
Used by the validation layer to enforce structure on the projected output.
"""

CANDIDATE_OUTPUT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://datatransformer.io/schemas/candidate-output-v1.json",
    "title": "CandidateOutput",
    "description": "Merged candidate profile output from the DataTransformer pipeline",
    "type": "object",
    "required": ["candidate_id"],
    "properties": {
        "candidate_id": {
            "type": "string",
            "description": "UUID v4 identifier"
        },
        "full_name": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "merge_reason": {"type": ["string", "null"]}
                    }
                }
            ]
        },
        "name": {
            "type": ["string", "null"]
        },
        "emails": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "pattern": "^[^@]+@[^@]+\\.[^@]+$"
                    },
                    "is_primary": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        },
        "primary_email": {
            "type": ["string", "null"],
            "pattern": "^[^@]+@[^@]+\\.[^@]+$"
        },
        "phones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "pattern": "^\\+[1-9]\\d{1,14}$"
                    },
                    "is_primary": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        },
        "primary_phone": {
            "type": ["string", "null"],
            "pattern": "^\\+[1-9]\\d{1,14}$"
        },
        "location": {
            "type": ["object", "null"],
            "properties": {
                "city": {"type": ["string", "null"]},
                "state": {"type": ["string", "null"]},
                "country": {"type": ["string", "null"]},
                "formatted": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            }
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "normalized": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": ["string", "null"]},
                    "title": {"type": ["string", "null"]},
                    "start_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{4}-\\d{2}$"
                    },
                    "end_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{4}-\\d{2}$"
                    },
                    "is_current": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": ["string", "null"]},
                    "degree": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        },
        "overall_confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
        },
        "merge_summary": {
            "type": "object",
            "properties": {
                "sources_merged": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "fields_conflicted": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "fields_missing": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
    },
    "additionalProperties": True
}
