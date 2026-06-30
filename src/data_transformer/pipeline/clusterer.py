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
            
        # ── Pass 1 & 2: Deterministic O(N) Blocking ──
        # Map canonical identity keys to cluster IDs
        cluster_map: Dict[str, str] = {}
        record_clusters: Dict[str, CandidateCluster] = {}
        
        def merge_clusters(id1: str, id2: str) -> str:
            if id1 == id2: return id1
            c1 = record_clusters[id1]
            c2 = record_clusters[id2]
            c1.records.extend(c2.records)
            if c2.requires_review:
                c1.requires_review = True
                c1.review_reason += " | " + c2.review_reason
            # Redirect pointers
            for k, v in list(cluster_map.items()):
                if v == id2:
                    cluster_map[k] = id1
            del record_clusters[id2]
            return id1
            
        for rec in records:
            fields = rec.fields
            emails = fields.get("emails", [])
            phones = fields.get("phones", [])
            links = fields.get("links", [])
            github_urls = [l.get("url", "") for l in links if isinstance(l, dict) and l.get("type") == "github"]
            full_name = fields.get("full_name")
            
            keys_to_check = []
            for e in emails: keys_to_check.append(f"email:{e}")
            for p in phones: keys_to_check.append(f"phone:{p}")
            for g in github_urls: keys_to_check.append(f"github:{g}")
            if full_name:
                normalized_name = str(full_name).lower().strip()
                keys_to_check.append(f"name:{normalized_name}")
                
            matched_cluster_ids = set()
            for k in keys_to_check:
                if k in cluster_map:
                    matched_cluster_ids.add(cluster_map[k])
                    
            target_cid = None
            if not matched_cluster_ids:
                target_cid = uuid.uuid4().hex[:8]
                record_clusters[target_cid] = CandidateCluster(cluster_id=target_cid, records=[rec])
            else:
                matched_list = list(matched_cluster_ids)
                target_cid = matched_list[0]
                record_clusters[target_cid].records.append(rec)
                for other_cid in matched_list[1:]:
                    if other_cid in record_clusters:
                        target_cid = merge_clusters(target_cid, other_cid)
                        
            for k in keys_to_check:
                cluster_map[k] = target_cid
                
        # ── Pass 3: Fuzzy & Semantic (Fallback) ──
        # Compare remaining distinct clusters using O(C^2) which is much smaller than O(N^2)
        clusters_list = list(record_clusters.values())
        merged_in_pass3 = set()
        final_clusters = []
        
        for i in range(len(clusters_list)):
            if clusters_list[i].cluster_id in merged_in_pass3:
                continue
                
            current_c = clusters_list[i]
            
            for j in range(i + 1, len(clusters_list)):
                if clusters_list[j].cluster_id in merged_in_pass3:
                    continue
                    
                other_c = clusters_list[j]
                
                # Compare the "best" record from each cluster for speed
                rec1 = max(current_c.records, key=lambda x: len(x.fields))
                rec2 = max(other_c.records, key=lambda x: len(x.fields))
                
                score = compute_identity_score(rec1, rec2)
                
                if score >= self.auto_merge_threshold:
                    current_c.records.extend(other_c.records)
                    merged_in_pass3.add(other_c.cluster_id)
                elif score >= self.manual_review_threshold:
                    # Auto-merge lower scores as requested by the user, skipping the manual review block.
                    current_c.records.extend(other_c.records)
                    merged_in_pass3.add(other_c.cluster_id)
                    
            final_clusters.append(current_c)
            
        return final_clusters
