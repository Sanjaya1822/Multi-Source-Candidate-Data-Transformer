"""
Candidate Clustering module.
Groups RawRecords into distinct CandidateClusters based on identity scores.
"""
from typing import List, Dict, Any, Set
from dataclasses import dataclass, field
import uuid

from data_transformer.schema.canonical import RawRecord
from data_transformer.pipeline.identity_resolver import compute_identity_score

@dataclass
class CandidateCluster:
    cluster_id: str
    records: List[RawRecord] = field(default_factory=list)
    requires_review: bool = False
    review_reason: str = ""
    scores: Dict[str, float] = field(default_factory=dict) # Pairwise scores within cluster

class CandidateClusterer:
    """
    Groups raw records into candidate clusters.
    """
    def __init__(self, auto_merge_threshold: float = 90.0, manual_review_threshold: float = 70.0):
        self.auto_merge_threshold = auto_merge_threshold
        self.manual_review_threshold = manual_review_threshold
        
    def cluster(self, records: List[RawRecord]) -> List[CandidateCluster]:
        """
        Takes a list of records and clusters them.
        Uses connected components for clustering.
        """
        if not records:
            return []
            
        n = len(records)
        if n == 1:
            return [CandidateCluster(cluster_id=uuid.uuid4().hex[:8], records=records)]
            
        clusters: List[CandidateCluster] = []
        
        # Calculate pairwise scores
        scores_matrix: Dict[int, Dict[int, float]] = {i: {} for i in range(n)}
        
        for i in range(n):
            for j in range(i + 1, n):
                score = compute_identity_score(records[i], records[j])
                scores_matrix[i][j] = score
                scores_matrix[j][i] = score
                
        # Simple clustering: start with each record as a cluster, then merge based on score
        # Since n is usually very small (2-5), a simple greedy approach works well.
        unassigned = set(range(n))
        
        while unassigned:
            start = unassigned.pop()
            current_cluster_indices = {start}
            
            cluster_requires_review = False
            review_reasons = []
            cluster_scores = {}
            
            # Expand cluster
            changed = True
            while changed:
                changed = False
                to_add = set()
                
                for idx in current_cluster_indices:
                    for other_idx in unassigned:
                        score = scores_matrix[idx][other_idx]
                        
                        s_idx = getattr(records[idx].source, 'type', str(records[idx].source))
                        s_other = getattr(records[other_idx].source, 'type', str(records[other_idx].source))
                        
                        if score >= self.auto_merge_threshold:
                            to_add.add(other_idx)
                            cluster_scores[f"{s_idx}_{s_other}"] = score
                        elif score >= self.manual_review_threshold:
                            # They should merge, but requires review
                            to_add.add(other_idx)
                            cluster_requires_review = True
                            review_reasons.append(
                                f"Identity Score is {score:.1f}% between {s_idx} and {s_other}. "
                                "Review matching/conflicting fields to proceed."
                            )
                            cluster_scores[f"{s_idx}_{s_other}"] = score
                
                if to_add:
                    current_cluster_indices.update(to_add)
                    unassigned.difference_update(to_add)
                    changed = True
                    
            cluster_records = [records[i] for i in current_cluster_indices]
            clusters.append(CandidateCluster(
                cluster_id=uuid.uuid4().hex[:8],
                records=cluster_records,
                requires_review=cluster_requires_review,
                review_reason=" | ".join(review_reasons) if cluster_requires_review else "",
                scores=cluster_scores
            ))
            
        return clusters
