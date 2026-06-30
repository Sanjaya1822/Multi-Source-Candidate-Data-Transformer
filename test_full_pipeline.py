import json
from data_transformer.schema.canonical import Source, RawRecord
from data_transformer.pipeline.runner import PipelineRunner
import tempfile
import os

config = {
    "deduplication": {"threshold": 0.85},
    "conflict_resolution": {"strategy": "highest_confidence"}
}

schema = {
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

content = """
John Doe
Location: San Francisco, CA
Email: john@example.com
Phone: 555-1234
"""

fd, path = tempfile.mkstemp(suffix=".txt")
os.write(fd, content.encode('utf-8'))
os.close(fd)

runner = PipelineRunner(config, schema)
sources = [Source(type="notes", path=path)]

clusters, source_results, norm_log, run_id, start_time = runner.run_phase_1(sources)

for c in clusters:
    c.requires_review = False

res = runner.run_phase_2(clusters, source_results, norm_log, run_id, start_time, projection_config=schema)

print(json.dumps(res.profiles, indent=2))
