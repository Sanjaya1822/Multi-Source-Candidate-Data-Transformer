import json
from data_transformer.projection.projector import Projector
from data_transformer.schema.canonical import CandidateRecord, LocationEntry, FieldValue, EmailEntry

cand = CandidateRecord()
cand.full_name = FieldValue[str](value="Jane Smith")
cand.emails = [EmailEntry(value="jane@example.com", is_primary=True, confidence=1.0)]
cand.location = LocationEntry(formatted="New York, NY")

config = {
    "fields": [
        {"path": "candidate_id", "type": "string"},
        {"path": "full_name", "type": "string"},
        {"path": "primary_email", "from": "emails[0].value", "type": "string"},
        {"path": "location", "type": "object"}
    ],
    "on_missing": "omit"
}

projector = Projector(config)
out = projector.project(cand)
print(json.dumps(out, indent=2))
