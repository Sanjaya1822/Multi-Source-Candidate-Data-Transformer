"""
Quality Report Generator.

Produces a comprehensive processing report including:
  - Processed / skipped / failed sources with per-source extraction stats
  - Normalization summary (all changes made during the normalization pass)
  - Deduplication results
  - Merge decisions (field-level with explainable reasoning)
  - Validation results (warnings and field-level errors)
  - Missing fields summary
  - Confidence summary (distribution, per-candidate breakdown)
  - Runtime statistics
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING

from data_transformer.schema.canonical import CandidateRecord

if TYPE_CHECKING:
    from data_transformer.pipeline.runner import SourceResult


class QualityReportGenerator:
    """Generates quality metrics and a full processing report for a pipeline run."""

    def generate(
        self,
        run_id: str,
        source_results: "List[SourceResult]",
        candidates: List[CandidateRecord],
        validation_warnings: List[Dict[str, Any]],
        normalization_log: List[Dict[str, Any]],
        dropped_candidates: List[Dict[str, Any]],
        duration_seconds: float,
        post_process_log: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        # ── Source breakdown ─────────────────────────────────────────────────
        processed_sources = []
        skipped_sources = []
        failed_adapters = []
        stub_notes = []

        for sr in source_results:
            entry = {
                "source_type": sr.source_type,
                "source_path": sr.source_path,
                "records_extracted": sr.records_extracted,
                "extraction_stats": sr.extraction_stats,
            }
            if sr.stub_note:
                stub_notes.append({"source_type": sr.source_type, "note": sr.stub_note})
            if sr.skipped:
                skipped_sources.append({**entry, "reason": sr.skip_reason})
            elif sr.failed:
                failed_adapters.append({**entry, "error": sr.fail_reason})
            else:
                processed_sources.append(entry)

        # ── Per-candidate stats ──────────────────────────────────────────────
        TRACKED_FIELDS = ["emails", "phones", "skills", "location", "experience",
                          "education", "headline", "links"]
        fields_missing_totals: Dict[str, int] = {f: 0 for f in TRACKED_FIELDS}
        conflict_methods: Dict[str, int] = {}
        conflicts_resolved = 0
        total_conf = 0.0
        conf_buckets = {"low_0_60": 0, "medium_60_80": 0, "high_80_100": 0}
        all_merge_decisions = []

        for c in candidates:
            # Missing field counts
            if not c.emails:
                fields_missing_totals["emails"] += 1
            if not c.phones:
                fields_missing_totals["phones"] += 1
            if not c.skills:
                fields_missing_totals["skills"] += 1
            loc = c.location
            if not loc.city and not loc.region and not loc.formatted:
                fields_missing_totals["location"] += 1
            if not c.experience:
                fields_missing_totals["experience"] += 1
            if not c.education:
                fields_missing_totals["education"] += 1
            if not c.headline.value:
                fields_missing_totals["headline"] += 1
            if not c.links.linkedin and not c.links.github and not c.links.portfolio:
                fields_missing_totals["links"] += 1

            # Conflict resolution stats
            for method in c.merge_summary.conflict_resolution_methods.values():
                conflict_methods[method] = conflict_methods.get(method, 0) + 1
                conflicts_resolved += 1

            total_conf += c.overall_confidence

            if c.overall_confidence < 0.6:
                conf_buckets["low_0_60"] += 1
            elif c.overall_confidence < 0.8:
                conf_buckets["medium_60_80"] += 1
            else:
                conf_buckets["high_80_100"] += 1

            for decision in c.merge_summary.merge_decisions:
                all_merge_decisions.append({"candidate_id": c.candidate_id, **decision})

        avg_conf = round(total_conf / max(1, len(candidates)), 4)

        # ── Normalization summary ────────────────────────────────────────────
        norm_by_type: Dict[str, int] = {}
        for entry in normalization_log:
            change_type = entry.get("change", "unknown")
            norm_by_type[change_type] = norm_by_type.get(change_type, 0) + 1

        normalization_summary = {
            "total_changes": len(normalization_log),
            "by_type": norm_by_type,
            "details": normalization_log,  # full audit trail
        }

        # ── Extraction stats ─────────────────────────────────────────────────
        total_records = sum(sr.records_extracted for sr in source_results)
        per_source_counts: Dict[str, int] = {}
        for sr in source_results:
            per_source_counts[sr.source_type] = (
                per_source_counts.get(sr.source_type, 0) + sr.records_extracted
            )

        return {
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",

            # ── Sources ───────────────────────────────────────────────────────
            "processed_sources": processed_sources,
            "skipped_sources": skipped_sources,
            "failed_adapters": failed_adapters,
            "stub_notes": stub_notes,

            # ── Records / Candidates ──────────────────────────────────────────
            "total_raw_records": total_records,
            "candidates_after_dedup": len(candidates),
            "candidates_dropped_low_confidence": dropped_candidates,
            "per_source_record_counts": per_source_counts,

            # ── Normalization ─────────────────────────────────────────────────
            "normalization_summary": normalization_summary,

            # ── Post-processing ───────────────────────────────────────────────
            "post_processing": {
                "total_cleanups": sum(len(e.get("actions", [])) for e in (post_process_log or [])),
                "details": post_process_log or [],
            },

            # ── Merge ─────────────────────────────────────────────────────────
            "merge_decisions": all_merge_decisions,
            "conflicts_resolved": conflicts_resolved,
            "conflict_resolution_methods_used": conflict_methods,

            # ── Validation ────────────────────────────────────────────────────
            "validation_warnings": validation_warnings,
            "validation_status": "clean" if not validation_warnings else f"{len(validation_warnings)} warning(s)",

            # ── Field quality ─────────────────────────────────────────────────
            "missing_fields": fields_missing_totals,

            # ── Confidence ────────────────────────────────────────────────────
            "confidence_summary": {
                "average_overall_confidence": avg_conf,
                "distribution": conf_buckets,
                "by_candidate": [
                    {
                        "candidate_id": c.candidate_id,
                        "name": c.full_name.value or "Unknown",
                        "overall_confidence": round(c.overall_confidence, 4),
                        "sources": c.merge_summary.sources_merged,
                        "fields_missing": c.merge_summary.fields_missing,
                        "fields_conflicted": c.merge_summary.fields_conflicted,
                    }
                    for c in candidates
                ],
            },

            # ── Runtime ───────────────────────────────────────────────────────
            "runtime": {
                "total_seconds": round(duration_seconds, 3),
                "avg_ms_per_candidate": round(
                    (duration_seconds / max(1, len(candidates))) * 1000, 1
                ),
            },
        }
