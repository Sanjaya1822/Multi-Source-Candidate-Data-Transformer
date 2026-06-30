import json
from data_transformer.schema.canonical import CandidateRecord, LocationEntry, FieldValue
from data_transformer.projection.projector import Projector

config = {
  "fields": [
    "full_name",
    "emails",
    "phones",
    "location"
  ],
  "include_confidence": True,
  "include_provenance": True,
  "on_missing": "omit",
  "renames": [
    {
      "from": "full_name",
      "path": "candidate_name"
    }
  ],
  "normalizations": {
    "phones": "E164"
  }
}

cand = CandidateRecord()
cand.full_name = FieldValue[str](value="John Doe", confidence=1.0)
cand.location = LocationEntry(formatted="San Francisco, CA", confidence=0.9)

projector = Projector(config)
out = projector.project(cand)
print(json.dumps(out, indent=2))
