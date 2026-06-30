"""
Pipeline Runner.

Orchestrates the full 8-stage pipeline:
  1. Source Detection + Extraction  (adapters, with per-source error isolation)
  2. Normalization                   (emails, phones, skills, dates, locations, names)
  3. Deduplication                   (fuzzy name + exact email/phone matching)
  4. Merge + Conflict Resolution     (per-field, with explainable provenance)
  5. Confidence Scoring              (source reliability × extraction quality × agreement)
  6. Projection                      (runtime schema-driven output shaping)
  7. Schema Validation               (JSON Schema, warnings only — never crashes pipeline)
  8. Quality Report                  (per-source stats, normalization log, confidence summary)

Every stage is isolated. A failure in any single source or candidate
never stops the rest of the pipeline from completing.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import structlog

from data_transformer.schema.canonical import Source, RawRecord, CandidateRecord
from data_transformer.adapters import (
    ATSAdapter, ResumeAdapter, CSVAdapter, NotesAdapter
)
from data_transformer.adapters.base import SourceAdapter
from data_transformer.deduplication.matcher import Matcher
from data_transformer.conflict_resolution import (
    PriorityOrderResolver, MajorityVoteResolver, LatestWinsResolver,
    HighestConfidenceResolver, MockLLMResolver, PhiLLMResolver,
)
from data_transformer.merger.merge_engine import MergeEngine
from data_transformer.projection.projector import Projector, ProjectorError
from data_transformer.validation.validator import OutputValidator
from data_transformer.reporting.quality_report import QualityReportGenerator
from data_transformer.pipeline.postprocessor import post_process
from data_transformer.normalizers import (
    normalize_email, normalize_phone, normalize_name,
    normalize_skill, normalize_date, normalize_location_string,
)

log = structlog.get_logger()


# ─── Pipeline data containers ─────────────────────────────────────────────────

@dataclass
class SourceResult:
    """Tracks per-source extraction outcome for the report."""
    source_type: str
    source_path: Optional[str]
    records_extracted: int
    skipped: bool = False
    skip_reason: Optional[str] = None
    failed: bool = False
    fail_reason: Optional[str] = None
    extraction_stats: Dict[str, Any] = field(default_factory=dict)
    stub_note: Optional[str] = None
    _records: List[RawRecord] = field(default_factory=list, repr=False)


@dataclass
class PipelineResult:
    profiles: List[Dict[str, Any]]
    report: Dict[str, Any]
    invalid_profiles: List[Dict[str, Any]]
    summary: Dict[str, Any] = field(default_factory=dict)


# ─── Pipeline Runner ──────────────────────────────────────────────────────────

class PipelineRunner:
    """
    Config-driven pipeline runner.

    All behavior is controlled by pipeline_config and output_schema dicts.
    No code changes are needed to alter deduplication thresholds, resolver
    strategies, trust scores, normalization options, or output shape.
    """

    def __init__(self, pipeline_config: Dict[str, Any], output_schema: Dict[str, Any]):
        self.log = log
        self.config = pipeline_config
        self.output_schema = output_schema

        self._setup_adapters()
        self._setup_resolvers()
        self._setup_deduplication()
        self._setup_merge_engine()

        self.projector = Projector(output_schema)
        self.validator = OutputValidator()
        self.reporter = QualityReportGenerator()

    # ─── Setup ───────────────────────────────────────────────────────────────

    def _setup_adapters(self) -> None:
        trust_scores = {
            k: v.get("trust_score", 0.5) 
            for k, v in self.config.get("sources", {}).items()
        }
        self.adapters: List[SourceAdapter] = [
            ATSAdapter(),
            CSVAdapter(),
            ResumeAdapter(),
            NotesAdapter(),
        ]

    def _setup_resolvers(self) -> None:
        # Build priority map from sources config
        priority_map = {
            k: v.get("priority", 99)
            for k, v in self.config.get("sources", {}).items()
        }

        priority_res  = PriorityOrderResolver(priority_map)
        majority_res  = MajorityVoteResolver(priority_res)
        latest_res    = LatestWinsResolver()
        highest_res   = HighestConfidenceResolver()

        llm_conf     = self.config.get("llm", {})
        fallback_name = self.config.get("llm_fallback_resolver", "priority_order")
        fallback_map  = {
            "priority_order":     priority_res,
            "majority_vote":      majority_res,
            "latest_wins":        latest_res,
            "highest_confidence": highest_res,
        }
        fallback_res = fallback_map.get(fallback_name, priority_res)

        if llm_conf.get("backend") == "phi3":
            llm_res = PhiLLMResolver(
                fallback_res,
                model_name=llm_conf.get("model_name", "microsoft/Phi-3-mini-4k-instruct"),
            )
        else:
            llm_res = MockLLMResolver(fallback_res)

        resolver_map = {
            "priority_order":     priority_res,
            "majority_vote":      majority_res,
            "latest_wins":        latest_res,
            "highest_confidence": highest_res,
            "llm":                llm_res,
        }

        # Support both conflict_resolution.strategy and legacy conflict_resolver
        cr_cfg        = self.config.get("conflict_resolution", {})
        strategy_name = (
            cr_cfg.get("strategy")
            or self.config.get("conflict_resolver", "priority_order")
        )
        self.default_resolver = resolver_map.get(strategy_name, priority_res)

        self.field_overrides: Dict[str, Any] = {}
        # Get canonical schema fields for validation
        canonical_fields = CandidateRecord.model_fields.keys()
        
        for fname, res_name in self.config.get("field_resolver_overrides", {}).items():
            if fname not in canonical_fields:
                raise ValueError(f"ConfigError: field '{fname}' in field_resolver_overrides does not exist in canonical schema.")
            if res_name not in resolver_map:
                raise ValueError(f"ConfigError: invalid resolver '{res_name}' specified for field '{fname}'.")
            self.field_overrides[fname] = resolver_map[res_name]

    def _setup_deduplication(self) -> None:
        dedup_cfg = self.config.get("deduplication", self.config.get("dedup", {}))
        threshold = dedup_cfg.get("threshold", dedup_cfg.get("fuzzy_threshold", 0.85))
        # Convert 0–1 scale to 0–100 for rapidfuzz
        if isinstance(threshold, float) and threshold <= 1.0:
            threshold = threshold * 100
        name_company_threshold = dedup_cfg.get(
            "name_company_threshold", threshold * 0.94
        )
        self.matcher = Matcher(
            fuzzy_threshold=float(threshold),
            name_company_threshold=float(name_company_threshold),
        )

    def _setup_merge_engine(self) -> None:
        trust_scores: Dict[str, float] = {
            k: v.get("trust_score", 0.5)
            for k, v in self.config.get("sources", {}).items()
        }
        # Defaults if config doesn't specify
        trust_scores.setdefault("ats",          0.95)
        trust_scores.setdefault("csv",          0.90)
        trust_scores.setdefault("linkedin",     0.88)
        trust_scores.setdefault("github",       0.80)
        trust_scores.setdefault("resume",       0.75)
        trust_scores.setdefault("notes",        0.60)
        trust_scores.setdefault("linkedin_url", 0.30)

        self.merge_engine = MergeEngine(
            default_resolver=self.default_resolver,
            field_overrides=self.field_overrides,
            trust_scores=trust_scores,
        )

    # ─── Main Run ─────────────────────────────────────────────────────────────

    def run(self, sources: List[Source], on_progress=None) -> PipelineResult:
        """Synchronous runner for tests and legacy execution."""
        clusters, source_results, norm_log, run_id, start_time = self.run_phase_1(sources, on_progress=on_progress)
        return self.run_phase_2(clusters, source_results, norm_log, run_id, start_time, on_progress=on_progress)

    def run_phase_1(self, sources: List[Source], on_progress=None) -> tuple[List[Any], List[SourceResult], List[Dict], str, float]:
        start_time = time.time()
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        self.log.info("pipeline_started", run_id=run_id, sources=len(sources))

        # ── Stage 1: Extraction ───────────────────────────────────────────────
        raw_records: List[RawRecord] = []
        source_results: List[SourceResult] = []

        import concurrent.futures
        
        if on_progress:
            on_progress("Extraction", 0, len(sources))
            
        max_workers = min(8, len(sources)) if sources else 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_source = {executor.submit(self._detect_and_extract, s): s for s in sources}
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_source):
                try:
                    sr = future.result()
                    source_results.append(sr)
                    raw_records.extend(sr._records)
                except Exception as exc:
                    s = future_to_source[future]
                    self.log.error("extraction_future_failed", source=s.path, error=str(exc))
                    
                completed += 1
                if on_progress:
                    on_progress("Extraction", completed, len(sources))

        # ── Stage 2: Normalization ────────────────────────────────────────────
        normalization_log: List[Dict[str, Any]] = []
        raw_records = self._normalize_pass(raw_records, normalization_log)

        # ── Stage 3: Identity Resolution & Candidate Clustering ───────────────
        self.log.info("clustering_started", records=len(raw_records))
        from data_transformer.pipeline.clusterer import CandidateClusterer
        
        clusterer = CandidateClusterer(
            auto_merge_threshold=self.config.get("clustering", {}).get("auto_merge_threshold", 90.0),
            manual_review_threshold=self.config.get("clustering", {}).get("manual_review_threshold", 70.0)
        )
        clusters = clusterer.cluster(raw_records)
        self.log.info("clustering_complete", clusters=len(clusters))
        
        return clusters, source_results, normalization_log, run_id, start_time

    def run_phase_2(self, clusters: List[Any], source_results: List[SourceResult], normalization_log: List[Dict], run_id: str, start_time: float, projection_config: Optional[Dict[str, Any]] = None, on_progress=None) -> PipelineResult:
        if projection_config is not None:
            self.projector = Projector(projection_config)
        # ── Stage 4 & 5: Merge + Confidence Scoring ───────────────────────────
        from data_transformer.deduplication.matcher import MatchGroup
        
        candidates: List[CandidateRecord] = []
        dropped_low_conf: List[Dict] = []
        post_process_log: List[Dict] = []
        min_conf = self.config.get("output", {}).get("min_overall_confidence", 0.0)

        if on_progress:
            on_progress("Merging", 0, len(clusters))

        completed_clusters = 0
        for cluster in clusters:
            # Map CandidateCluster back to MatchGroup for merge engine compatibility
            group = MatchGroup()
            for rec in cluster.records:
                group.add(rec)
            try:
                merged = self.merge_engine.merge(group)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self.log.warning("merge_failed", error=str(exc))
                continue

            # ── Stage 4.5: Post-processing (cleanup before projection) ─────
            try:
                merged, pp_actions = post_process(merged)
                if pp_actions:
                    post_process_log.append({
                        "candidate_id": merged.candidate_id,
                        "actions": pp_actions,
                    })
            except Exception as exc:
                self.log.warning("post_process_failed", error=str(exc))

            if merged.overall_confidence >= min_conf:
                candidates.append(merged)
            else:
                dropped_low_conf.append({
                    "candidate_id": merged.candidate_id,
                    "overall_confidence": merged.overall_confidence,
                    "reason": f"Below min_overall_confidence threshold ({min_conf})",
                })
                self.log.info(
                    "candidate_dropped_low_confidence",
                    cid=merged.candidate_id,
                    conf=merged.overall_confidence,
                )

            completed_clusters += 1
            if on_progress:
                on_progress("Merging", completed_clusters, len(clusters))

        # ── Stage 6 & 7: Projection + Validation ─────────────────────────────
        final_profiles: List[Dict] = []
        invalid_profiles: List[Dict] = []
        validation_warnings: List[Dict] = []

        for cand in candidates:
            try:
                projected = self.projector.project(cand)
            except ProjectorError as e:
                self.log.warning("projection_failed", cid=cand.candidate_id, error=str(e))
                invalid_profiles.append({
                    "candidate_id": cand.candidate_id,
                    "errors": [str(e)],
                    "reason": "projection_error",
                })
                continue
            except Exception as e:
                self.log.warning("projection_unexpected_error", cid=cand.candidate_id, error=str(e))
                invalid_profiles.append({
                    "candidate_id": cand.candidate_id,
                    "errors": [str(e)],
                    "reason": "unexpected_error",
                })
                continue

            val_result = self.validator.validate(projected)
            if not val_result.is_valid:
                for err in val_result.errors:
                    validation_warnings.append({
                        "candidate_id": cand.candidate_id,
                        "warning": err,
                    })

            final_profiles.append(projected)

        # ── Stage 8: Report ───────────────────────────────────────────────────
        duration = time.time() - start_time
        report = self.reporter.generate(
            run_id=run_id,
            source_results=source_results,
            candidates=candidates,
            validation_warnings=validation_warnings,
            normalization_log=normalization_log,
            dropped_candidates=dropped_low_conf,
            duration_seconds=duration,
            post_process_log=post_process_log,
        )

        # Batch Processing Summary
        files_processed = len(source_results)
        candidates_detected = len(clusters)
        profiles_generated = len(final_profiles)
        duplicates_merged = files_processed - candidates_detected if files_processed > candidates_detected else 0
        failed_files = sum(1 for sr in source_results if sr.failed)
        
        summary = {
            "files_processed": files_processed,
            "candidates_detected": candidates_detected,
            "profiles_generated": profiles_generated,
            "duplicates_merged": duplicates_merged,
            "failed_files": failed_files,
            "processing_time": f"{round(duration, 2)}s",
            "warnings": validation_warnings
        }

        self.log.info(
            "pipeline_completed",
            run_id=run_id,
            merged=len(final_profiles),
            invalid=len(invalid_profiles),
            duration_s=round(duration, 3),
        )

        return PipelineResult(
            profiles=final_profiles,
            report=report,
            invalid_profiles=invalid_profiles,
            summary=summary,
        )


    # ─── Extraction helper ────────────────────────────────────────────────────

    def _detect_and_extract(self, source: Source) -> SourceResult:
        """Find the right adapter, extract records, return SourceResult. Never raises."""
        sr = SourceResult(
            source_type=source.type,
            source_path=source.path,
            records_extracted=0,
        )

        for adapter in self.adapters:
            if not adapter.can_handle(source):
                continue

            try:
                result = adapter.extract(source)
                # CSV returns List[RawRecord]; all others return a single RawRecord or None
                if isinstance(result, list):
                    records = [r for r in result if r is not None]
                elif result is not None:
                    records = [result]
                else:
                    records = []

                sr._records = records
                sr.records_extracted = len(records)

                # Collect extraction_stats and stub notes from each record
                for rec in records:
                    if not rec.fields.get("full_name"):
                        from pathlib import Path
                        import re
                        fname = Path(source.path).stem
                        # Remove common words like resume, cv, notes
                        clean_name = re.sub(r'(?i)(resume|cv|notes|profile|data)', '', fname).replace('_', ' ').replace('-', ' ').strip()
                        if clean_name:
                            rec.fields["full_name"] = clean_name
                            
                    if rec.extraction_stats:
                        sr.extraction_stats.update(rec.extraction_stats)
                        stub_note = rec.extraction_stats.get("stub_note")
                        if stub_note:
                            sr.stub_note = stub_note

            except Exception as exc:
                self.log.warning(
                    "adapter_extraction_failed",
                    adapter=adapter.__class__.__name__,
                    source_type=source.type,
                    path=source.path,
                    error=str(exc),
                )
                sr.failed = True
                sr.fail_reason = str(exc)

            return sr

        # No adapter matched
        sr.skipped = True
        sr.skip_reason = f"No adapter found for source type '{source.type}'"
        self.log.warning("no_adapter_found", source_type=source.type, path=source.path)
        return sr

    # ─── Normalization pass ───────────────────────────────────────────────────

    def _normalize_pass(
        self, records: List[RawRecord], norm_log: List[Dict[str, Any]]
    ) -> List[RawRecord]:
        """
        Explicit isolated normalization stage.

        Transforms raw extracted values in-place and logs every change:
          - Emails: lowercase + validate
          - Phones: E.164 via phonenumbers
          - Skills: canonical alias lookup + fuzzy matching
          - Dates: YYYY-MM normalization for experience/education
          - Names: title-case normalization
          - Location: structured parse into city/region/country

        All changes are appended to norm_log for the quality report.
        """
        missing_value_policy = (
            self.config.get("output", {}).get("missing_value_policy", "null")
        )

        for record in records:
            f = record.fields
            src = record.source

            # ── Emails ───────────────────────────────────────────────────────
            if "emails" in f and f["emails"]:
                normed = []
                for e in f["emails"]:
                    n = normalize_email(str(e)) if e else ""
                    if n and n != str(e):
                        norm_log.append({"source": src, "field": "email", "raw": e, "normalized": n, "change": "normalized"})
                    if n:
                        normed.append(n)
                    elif e:
                        norm_log.append({"source": src, "field": "email", "raw": e, "normalized": None, "change": "dropped_invalid"})
                f["emails"] = normed

            # ── Phones ───────────────────────────────────────────────────────
            if "phones" in f and f["phones"]:
                normed = []
                for p in f["phones"]:
                    raw_str = str(p) if not isinstance(p, dict) else p.get("value", "")
                    n = normalize_phone(raw_str) if raw_str else None
                    if n and n != raw_str:
                        norm_log.append({"source": src, "field": "phone", "raw": raw_str, "normalized": n, "change": "e164"})
                    if n:
                        normed.append(n)
                    elif raw_str:
                        norm_log.append({"source": src, "field": "phone", "raw": raw_str, "normalized": None, "change": "dropped_unparseable"})
                f["phones"] = normed

            # ── Skills ───────────────────────────────────────────────────────
            if "skills" in f and f["skills"]:
                normed_skills = []
                seen_skills: Dict[str, str] = {}
                for s in f["skills"]:
                    raw_s = str(s).strip()
                    if not raw_s:
                        continue
                    canonical = normalize_skill(raw_s)
                    if canonical:
                        key = canonical.lower()
                        if key not in seen_skills:
                            seen_skills[key] = canonical
                            if canonical != raw_s:
                                norm_log.append({"source": src, "field": "skill", "raw": raw_s, "normalized": canonical, "change": "alias_resolved"})
                            normed_skills.append(canonical)
                        else:
                            norm_log.append({"source": src, "field": "skill", "raw": raw_s, "normalized": canonical, "change": "duplicate_removed"})
                    else:
                        norm_log.append({"source": src, "field": "skill", "raw": raw_s, "normalized": None, "change": "dropped_empty"})
                f["skills"] = normed_skills

            # ── Full name ────────────────────────────────────────────────────
            if "full_name" in f and f["full_name"]:
                raw_name = str(f["full_name"]).strip()
                normed_name = normalize_name(raw_name)
                if normed_name and normed_name != raw_name:
                    norm_log.append({"source": src, "field": "full_name", "raw": raw_name, "normalized": normed_name, "change": "title_cased"})
                if normed_name:
                    f["full_name"] = normed_name

            # ── Location: parse into structured dict ─────────────────────────
            if "location" in f and f["location"]:
                raw_loc = f["location"]
                if isinstance(raw_loc, str) and raw_loc.strip():
                    parsed = normalize_location_string(raw_loc.strip())
                    if parsed.get("country") and parsed.get("country") != raw_loc.strip():
                        norm_log.append({"source": src, "field": "location", "raw": raw_loc, "normalized": parsed, "change": "structured_parsed"})
                    f["location"] = parsed  # store as dict for merge engine
                elif isinstance(raw_loc, dict):
                    # Already structured — ensure country is normalized
                    country = raw_loc.get("country")
                    if country:
                        from data_transformer.normalizers import normalize_country
                        iso = normalize_country(str(country))
                        if iso and iso != country:
                            norm_log.append({"source": src, "field": "location.country", "raw": country, "normalized": iso, "change": "iso3166"})
                            raw_loc["country"] = iso

            # ── Experience dates ─────────────────────────────────────────────
            if "experience" in f and f["experience"]:
                for exp in f["experience"]:
                    if not isinstance(exp, dict):
                        continue
                    for date_field in ("start_date", "end_date"):
                        raw_d = exp.get(date_field)
                        if raw_d and isinstance(raw_d, str):
                            normed_d = normalize_date(raw_d)
                            if normed_d and normed_d != raw_d:
                                norm_log.append({"source": src, "field": f"experience.{date_field}", "raw": raw_d, "normalized": normed_d, "change": "yyyy-mm"})
                                exp[date_field] = normed_d
                            elif not normed_d:
                                exp[date_field] = None

            # ── Education dates ──────────────────────────────────────────────
            if "education" in f and f["education"]:
                for edu in f["education"]:
                    if not isinstance(edu, dict):
                        continue
                    for date_field in ("start_date", "end_date"):
                        raw_d = edu.get(date_field)
                        if raw_d and isinstance(raw_d, str):
                            normed_d = normalize_date(raw_d)
                            if normed_d and normed_d != raw_d:
                                norm_log.append({"source": src, "field": f"education.{date_field}", "raw": raw_d, "normalized": normed_d, "change": "yyyy-mm"})
                                edu[date_field] = normed_d
                            elif not normed_d:
                                edu[date_field] = None

        return records