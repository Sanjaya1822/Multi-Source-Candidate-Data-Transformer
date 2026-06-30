"""
Validation Layer.
Validates projected output dictionaries against the JSON Schema.
"""
from typing import Any, Dict, List
from dataclasses import dataclass

import jsonschema
from jsonschema.exceptions import ValidationError

from data_transformer.schema.json_schema import CANDIDATE_OUTPUT_SCHEMA

@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]

class OutputValidator:
    """Validates the final output JSON."""
    
    def __init__(self, schema: Dict[str, Any] = CANDIDATE_OUTPUT_SCHEMA):
        self.schema = schema
        self.validator = jsonschema.Draft7Validator(self.schema)

    def validate(self, record: Dict[str, Any]) -> ValidationResult:
        errors = []
        for err in self.validator.iter_errors(record):
            path = ".".join(str(p) for p in err.path) if err.path else "root"
            errors.append(f"{path}: {err.message}")
            
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
