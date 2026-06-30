import json
from data_transformer.adapters.resume_adapter import ResumeAdapter
from data_transformer.merger.merge_engine import MergeEngine
from data_transformer.schema.canonical import Source
from data_transformer.deduplication.matcher import MatchGroup
from data_transformer.projection.projector import Projector

def test():
    adapter = ResumeAdapter()
    src = Source(type="resume", path="debug_resume.txt")
    record = adapter.extract(src)
    
    print("=== Raw Experience ===")
    print(record.fields.get('experience'))
    
    import yaml
    from pathlib import Path
    from data_transformer.pipeline.runner import PipelineRunner
    config = yaml.safe_load((Path("config") / "pipeline_config.yaml").read_text())
    runner = PipelineRunner(config, {})
    merger = runner.merge_engine
    group = MatchGroup()
    group.records.append(record)
    candidate = merger.merge(group)
    
    print("=== Merged Experience ===")
    print(candidate.experience)
    
    print("=== Merged Education ===")
    print(candidate.education)
    
    print("=== Merged Location ===")
    print(candidate.location)
    
    projector = Projector()
    out = projector.project(candidate)
    print("=== Projected Output ===")
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    test()
