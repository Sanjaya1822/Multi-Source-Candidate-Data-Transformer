"""
Quality Reporting.
Generates a run-level report summarizing pipeline performance and data quality.
"""
from datetime import datetime
from typing import List, Dict, Any

from data_transformer.schema.canonical import CandidateRecord

class QualityReportGenerator:
    """Generates quality metrics for a pipeline run."""
    
    def generate(self, 
                 run_id: str,
                 sources_processed: int,
                 sources_failed: int,
                 candidates: List[CandidateRecord],
                 duration_seconds: float) -> Dict[str, Any]:
                 
        fields_missing = {"emails": 0, "phones": 0, "skills": 0, "location": 0, "experience": 0}
        conflict_methods = {}
        conflicts_resolved = 0
        total_conf = 0.0
        low_conf = 0
        
        for c in candidates:
            # Missing
            if not c.emails: fields_missing["emails"] += 1
            if not c.phones: fields_missing["phones"] += 1
            if not c.skills: fields_missing["skills"] += 1
            if not c.location.formatted and not c.location.city: fields_missing["location"] += 1
            if not c.experience: fields_missing["experience"] += 1
            
            # Conflicts
            for method in c.merge_summary.conflict_resolution_methods.values():
                conflict_methods[method] = conflict_methods.get(method, 0) + 1
                conflicts_resolved += 1
                
            # Confidence
            total_conf += c.overall_confidence
            if c.overall_confidence < 0.6:
                low_conf += 1
                
        avg_conf = total_conf / max(1, len(candidates))
        
        return {
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sources_processed": sources_processed,
            "sources_failed": sources_failed,
            "candidates_merged": len(candidates),
            "fields_missing": fields_missing,
            "conflicts_resolved": conflicts_resolved,
            "conflict_methods": conflict_methods,
            "avg_overall_confidence": round(avg_conf, 3),
            "low_confidence_profiles": low_conf,
            "performance": {
                "total_duration_seconds": round(duration_seconds, 2),
                "avg_profile_ms": round((duration_seconds / max(1, len(candidates))) * 1000, 1)
            }
        }
