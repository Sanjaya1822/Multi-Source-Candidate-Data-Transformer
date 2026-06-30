"""
Pipeline Runner.
Orchestrates the entire DETECT -> EXTRACT -> NORMALIZE -> DEDUP -> MERGE -> PROJECT -> VALIDATE process.
"""
import time
import uuid
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

import structlog

from data_transformer.schema.canonical import Source, RawRecord, CandidateRecord
from data_transformer.adapters import ATSAdapter, LinkedInAdapter, ResumeAdapter, CSVAdapter, NotesAdapter, GitHubAdapter
from data_transformer.deduplication.matcher import Matcher
from data_transformer.conflict_resolution import (
    PriorityOrderResolver, MajorityVoteResolver, LatestWinsResolver, 
    HighestConfidenceResolver, MockLLMResolver, PhiLLMResolver
)
from data_transformer.merger.merge_engine import MergeEngine
from data_transformer.projection.projector import Projector
from data_transformer.validation.validator import OutputValidator
from data_transformer.reporting.quality_report import QualityReportGenerator


@dataclass
class PipelineResult:
    profiles: List[Dict[str, Any]]
    report: Dict[str, Any]
    invalid_profiles: List[Dict[str, Any]]


class PipelineRunner:
    def __init__(self, pipeline_config: Dict[str, Any], output_schema: Dict[str, Any]):
        self.log = structlog.get_logger()
        self.config = pipeline_config
        self.output_schema = output_schema
        
        self._setup_adapters()
        self._setup_resolvers()
        
        # Matcher
        self.matcher = Matcher(
            fuzzy_threshold=self.config.get("dedup", {}).get("fuzzy_threshold", 85.0),
            name_company_threshold=self.config.get("dedup", {}).get("name_company_threshold", 80.0)
        )
        
        # Merge Engine
        trust_scores = {k: v.get("trust_score", 0.5) for k, v in self.config.get("sources", {}).items()}
        self.merge_engine = MergeEngine(
            default_resolver=self.default_resolver,
            field_overrides=self.field_overrides,
            trust_scores=trust_scores
        )
        
        # Projection & Validation
        self.projector = Projector(self.output_schema)
        self.validator = OutputValidator()
        self.reporter = QualityReportGenerator()

    def _setup_adapters(self):
        self.adapters = [
            GitHubAdapter(),
            ATSAdapter(),
            LinkedInAdapter(),
            ResumeAdapter(),
            CSVAdapter(),
            NotesAdapter()
        ]

    def _setup_resolvers(self):
        # Build priority map
        priority_map = {k: v.get("priority", 99) for k, v in self.config.get("sources", {}).items()}
        
        # Base resolvers
        priority_res = PriorityOrderResolver(priority_map)
        majority_res = MajorityVoteResolver(priority_res)
        latest_res = LatestWinsResolver()
        highest_res = HighestConfidenceResolver()
        
        # LLM Resolver
        llm_conf = self.config.get("llm", {})
        fallback_name = self.config.get("llm_fallback_resolver", "priority_order")
        fallback_map = {
            "priority_order": priority_res,
            "majority_vote": majority_res,
            "latest_wins": latest_res,
            "highest_confidence": highest_res
        }
        fallback_res = fallback_map.get(fallback_name, priority_res)
        
        if llm_conf.get("backend") == "phi3":
            llm_res = PhiLLMResolver(fallback_res, model_name=llm_conf.get("model_name", "microsoft/Phi-3-mini-4k-instruct"))
        else:
            llm_res = MockLLMResolver(fallback_res)
            
        resolver_map = {
            "priority_order": priority_res,
            "majority_vote": majority_res,
            "latest_wins": latest_res,
            "highest_confidence": highest_res,
            "llm": llm_res
        }
        
        default_name = self.config.get("conflict_resolver", "priority_order")
        self.default_resolver = resolver_map.get(default_name, priority_res)
        
        self.field_overrides = {}
        for field, res_name in self.config.get("field_resolver_overrides", {}).items():
            if res_name in resolver_map:
                self.field_overrides[field] = resolver_map[res_name]

    def run(self, sources: List[Source]) -> PipelineResult:
        start_time = time.time()
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        
        self.log.info("pipeline_started", run_id=run_id, sources=len(sources))
        
        raw_records = []
        failed_sources = 0
        
        # 1 & 2. DETECT & EXTRACT
        for source in sources:
            handled = False
            for adapter in self.adapters:
                if adapter.can_handle(source):
                    record = adapter.safe_extract(source)
                    if record:
                        raw_records.append(record)
                    else:
                        failed_sources += 1
                    handled = True
                    break
            if not handled:
                self.log.warning("no_adapter_found", source_type=source.type, path=source.path)
                failed_sources += 1
                
        # 3. NORMALIZE (Done implicitly within adapters and deduplication mapping)
        # Note: True pipeline would do an explicit normalization pass here before matching.
        # We rely on normalizer functions being called during matching and downstream.
        
        # 4. DEDUP
        self.log.info("deduplication_started", records=len(raw_records))
        match_groups = self.matcher.match(raw_records)
        
        # 5. MERGE & CONFLICT RESOLUTION
        candidates: List[CandidateRecord] = []
        for group in match_groups:
            merged = self.merge_engine.merge(group)
            
            # Apply Min Confidence Filter
            min_conf = self.config.get("output", {}).get("min_overall_confidence", 0.0)
            if merged.overall_confidence >= min_conf:
                candidates.append(merged)
            else:
                self.log.info("candidate_dropped_low_confidence", cid=merged.candidate_id, conf=merged.overall_confidence)
                
        # 6. PROJECT & VALIDATE
        final_profiles = []
        invalid_profiles = []
        
        for cand in candidates:
            projected = self.projector.project(cand)
            val_result = self.validator.validate(projected)
            
            if val_result.is_valid:
                final_profiles.append(projected)
            else:
                self.log.warning("validation_failed", cid=cand.candidate_id, errors=val_result.errors)
                invalid_profiles.append({"profile": projected, "errors": val_result.errors})
                
        # 7. EMIT REPORT
        duration = time.time() - start_time
        report = self.reporter.generate(
            run_id=run_id,
            sources_processed=len(sources),
            sources_failed=failed_sources,
            candidates=candidates,
            duration_seconds=duration
        )
        
        self.log.info("pipeline_completed", run_id=run_id, merged=len(final_profiles), duration=duration)
        
        return PipelineResult(
            profiles=final_profiles,
            report=report,
            invalid_profiles=invalid_profiles
        )
