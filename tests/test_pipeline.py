"""E2E Pipeline Tests."""
from data_transformer.schema.canonical import Source
from data_transformer.pipeline.runner import PipelineRunner
import yaml
from pathlib import Path

def test_pipeline_runner_with_mock_data():
    base = Path(__file__).parent.parent
    config = yaml.safe_load((base / "config" / "pipeline_config.yaml").read_text())
    schema = yaml.safe_load((base / "config" / "output_schema.yaml").read_text())
    
    runner = PipelineRunner(config, schema)
    
    sources = [
        Source(type="ats", path=str(base / "data" / "samples" / "ats_sample.json")),
        Source(type="linkedin", path=str(base / "data" / "samples" / "linkedin_sample.json")),
        Source(type="resume", path=str(base / "data" / "samples" / "resume_sample.json")),
    ]
    
    res = runner.run(sources)
    
    # Jane Smith should be merged from all 3 sources
    assert len(res.profiles) == 1
    
    merged = res.profiles[0]
    assert merged["name"] == "Jane Smith"  # or Jane A. Smith depending on LLM/priority
    assert merged["primary_email"] == "jane.smith@example.com"
    
    assert "merge_summary" in merged
    assert len(merged["merge_summary"]["sources_merged"]) == 3
