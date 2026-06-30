"""
JSON Schema Draft-07 definition for the canonical output.
Used by the validation layer to enforce structure on the projected output.

Covers all fields defined in the Eightfold assignment:
  candidate_id, full_name, emails[], phones[], location {city, region, country},
  links {linkedin, github, portfolio, other[]}, headline, years_experience,
  skills[], experience[], education[], provenance[], overall_confidence
"""

CANDIDATE_OUTPUT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://datatransformer.io/schemas/candidate-output-v2.json",
    "title": "CandidateOutput",
    "description": "Merged candidate profile from the DataTransformer pipeline",
    "type": "object",
    "required": ["candidate_id"],
    "additionalProperties": True,
    "properties": {

        # ── Identity ──────────────────────────────────────────────────────────
        "candidate_id": {
            "type": "string",
            "description": "UUID v4 identifier"
        },

        # full_name: can be projected as a plain string OR a FieldValue object
        "full_name": {
            "oneOf": [
                {"type": ["string", "null"]},
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

        # ── Contact ───────────────────────────────────────────────────────────
        "emails": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["value"],
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

        "phones": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["value"],
                "properties": {
                    "value": {
                        "type": "string",
                        "pattern": "^\\+[1-9]\\d{1,14}$"
                    },
                    "is_primary": {"type": "boolean"},
                    "type": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        },

        # ── Location (assignment spec: city, region, country) ─────────────────
        "location": {
            "oneOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "city":      {"type": ["string", "null"]},
                        "region":    {"type": ["string", "null"]},
                        "country":   {
                            "type": ["string", "null"],
                            "description": "ISO-3166 alpha-2 country code"
                        },
                        "formatted": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                    }
                }
            ]
        },

        # ── Links (assignment spec: structured object) ────────────────────────
        "links": {
            "oneOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "linkedin":  {"type": ["string", "null"], "format": "uri"},
                        "github":    {"type": ["string", "null"], "format": "uri"},
                        "portfolio": {"type": ["string", "null"], "format": "uri"},
                        "other": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                    }
                }
            ]
        },

        # ── Professional ──────────────────────────────────────────────────────
        "headline": {
            "oneOf": [
                {"type": ["string", "null"]},
                {
                    "type": "object",
                    "properties": {
                        "value":       {"type": ["string", "null"]},
                        "confidence":  {"type": "number", "minimum": 0, "maximum": 1},
                        "merge_reason": {"type": ["string", "null"]}
                    }
                }
            ]
        },

        "years_experience": {
            "oneOf": [
                {"type": ["number", "null"]},
                {
                    "type": "object",
                    "properties": {
                        "value":       {"type": ["number", "null"]},
                        "confidence":  {"type": "number", "minimum": 0, "maximum": 1},
                        "merge_reason": {"type": ["string", "null"]}
                    }
                }
            ]
        },

        # ── Skills (structured objects per assignment spec) ────────────────────
        "skills": {
            "type": "array",
            "items": {
                "oneOf": [
                    {
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name":       {"type": "string"},
                            "normalized": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "sources": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        }
                    },
                    {"type": "string"}  # allow plain string projection too
                ]
            }
        },

        # ── Experience ────────────────────────────────────────────────────────
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company":    {"type": ["string", "null"]},
                    "title":      {"type": ["string", "null"]},
                    "start_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{4}-\\d{2}$"
                    },
                    "end_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{4}-\\d{2}$"
                    },
                    "is_current":   {"type": "boolean"},
                    "description":  {"type": ["string", "null"]},
                    "confidence":   {"type": "number", "minimum": 0, "maximum": 1},
                    "merge_reason": {"type": ["string", "null"]}
                }
            }
        },

        # ── Education ────────────────────────────────────────────────────────
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution":    {"type": ["string", "null"]},
                    "degree":         {"type": ["string", "null"]},
                    "field_of_study": {"type": ["string", "null"]},
                    "start_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{4}-\\d{2}$"
                    },
                    "end_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{4}-\\d{2}$"
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        },

        # ── Tracking ─────────────────────────────────────────────────────────
        "provenance": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source":      {"type": "string"},
                    "source_id":   {"type": ["string", "null"]},
                    "ingested_at": {"type": "string"}
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
                },
                "merge_decisions": {
                    "type": "array",
                    "items": {"type": "object"}
                }
            }
        }
    }
}
