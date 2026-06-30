import pytest
import tempfile
import json
import yaml
from pathlib import Path

from data_transformer.schema.canonical import Source
from data_transformer.pipeline.runner import PipelineRunner

def test_batch_pipeline_scale():
    # Load config
    config = yaml.safe_load((Path("config") / "pipeline_config.yaml").read_text())
    schema = yaml.safe_load((Path("config") / "output_schema.yaml").read_text())
    
    # We will simulate 100 files containing 30 unique candidates
    # For speed, we just write simple ATS json records
    
    runner = PipelineRunner(config, schema)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        sources = []
        for i in range(100):
            # Create 30 unique buckets based on i % 30
            uid = i % 30
            path = Path(tmpdir) / f"candidate_{i}.json"
            data = {
                "candidate_id": f"id_{uid}",
                "name": f"Candidate {uid}",
                "email": f"candidate{uid}@example.com",
                "phone": f"+15550000{uid:02d}",
                "skills": ["Python", "AWS", f"Skill_{uid}"]
            }
            with open(path, "w") as f:
                json.dump(data, f)
            sources.append(Source(type="ats", path=str(path)))
            
        # Run batch pipeline
        result = runner.run(sources)
        
        # Verify deduplication grouped the 100 files into 30 canonical profiles
        assert result.summary["files_processed"] == 100
        assert result.summary["candidates_detected"] == 30
        assert len(result.profiles) == 30
        assert result.summary["duplicates_merged"] == 70
        assert result.summary["failed_files"] == 0
        
        # Check an output profile
        profile = result.profiles[0]
        assert "candidate_name" in profile or "full_name" in profile
        assert profile.get("emails") or profile.get("phones")
