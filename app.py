import streamlit as st
import json
import yaml
import time
from pathlib import Path
import tempfile
import sys
import os
import uuid
import zipfile
import io

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from data_transformer.schema.canonical import Source
from data_transformer.pipeline.runner import PipelineRunner
from data_transformer.pipeline.clusterer import CandidateCluster

# --- Configuration & Theme ---
st.set_page_config(page_title="DataTransformer Batch", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .header-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1rem 2rem;
        background-color: transparent;
        border-bottom: 1px solid rgba(93, 64, 55, 0.1);
        margin-bottom: 2rem;
    }
    
    .header-title {
        color: #5d4037;
        font-weight: 700;
        font-size: 1.75rem;
        margin: 0;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-container">
    <div class="header-title">DataTransformer Batch Processing</div>
</div>
""", unsafe_allow_html=True)

if "pipeline_phase" not in st.session_state:
    st.session_state.pipeline_phase = "upload"
if "final_result" not in st.session_state:
    st.session_state.final_result = None

def detect_source_type(filename: str) -> str:
    fname = filename.lower()
    if fname.endswith(".json"):
        return "ats" if "ats" in fname else "resume"
    if fname.endswith(".csv"):
        return "csv"
    if fname.endswith(".txt"):
        return "resume" if "resume" in fname or "cv" in fname else "notes"
    return "resume"

@st.cache_resource
def get_runner():
    config = yaml.safe_load((Path("config") / "pipeline_config.yaml").read_text())
    schema = yaml.safe_load((Path("config") / "output_schema.yaml").read_text())
    return PipelineRunner(config, schema)

st.markdown('<div class="header-container"><h1>Candidate Data Transformer</h1></div>', unsafe_allow_html=True)

if st.session_state.pipeline_phase == "upload":
    col_left, col_right = st.columns([1, 2], gap="large")
    
    with col_left:
        st.subheader("Pipeline Settings")
        
        # Output Schema Config
        st.markdown("**Output Fields**")
        all_fields = [
            "candidate_id", "full_name", "emails", "emails[0].value", 
            "phones", "phones[0].value", "location", "location.city", 
            "location.country", "links", "skills", "experience", 
            "education", "projects", "certifications", "headline", "years_experience"
        ]
        default_selections = ["candidate_id", "full_name", "emails", "phones", "skills", "experience"]
        selected_fields = st.multiselect("Select fields to extract:", all_fields, default=default_selections)
        
        st.markdown("**Field Configuration (Rename & Normalize)**")
        schema_fields = []
        normalizations = {}
        for f in selected_fields:
            with st.expander(f"Configure: {f}"):
                default_path = f.replace(".value", "").replace("[0]", "")
                path = st.text_input("Rename to (path):", value=default_path, key=f"path_{f}")
                
                norm_opts = ["None", "E164", "canonical"]
                norm = st.selectbox("Normalization:", norm_opts, key=f"norm_{f}")
                
                field_def = {"path": path, "from": f}
                schema_fields.append(field_def)
                if norm != "None":
                    normalizations[path] = norm
            
        st.markdown("---")
        col_c, col_p = st.columns(2)
        with col_c:
            inc_conf = st.toggle("Include Confidence", value=True)
        with col_p:
            inc_prov = st.toggle("Include Provenance", value=False)
            
        on_missing = st.selectbox("On Missing Policy", ["omit", "null", "error"])
        
        # Hardcoded default for pipeline Phase 1 since UI is removed
        pipeline_config = {
            "deduplication": {"threshold": 0.85},
            "conflict_resolution": {"strategy": "highest_confidence"}
        }
        
        output_schema = {
            "fields": schema_fields,
            "include_confidence": inc_conf,
            "include_provenance": inc_prov,
            "on_missing": on_missing,
            "normalizations": normalizations
        }
        
        with st.expander("View Generated JSON Configs"):
            config_json_str = st.text_area("Configuration JSON", value=json.dumps(pipeline_config, indent=4), height=150)
            schema_json_str = st.text_area("Output Schema JSON", value=json.dumps(output_schema, indent=4), height=250)
            


        
    with col_right:
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            st.subheader("Structured Sources")
            structured_files = st.file_uploader("Upload ATS JSON or CSV", accept_multiple_files=True, type=["json", "csv"])
    
        with col_up2:
            st.subheader("Unstructured Sources")
            unstructured_files = st.file_uploader("Upload Resumes or Notes", accept_multiple_files=True, type=["pdf", "docx", "doc", "txt"])
    

        if st.button("Run Batch Pipeline"):
            all_files = (structured_files or []) + (unstructured_files or [])
            if not all_files:
                st.error("Please provide at least one valid source.")
            else:
                try:
                    pipeline_config = json.loads(config_json_str)
                    output_schema = json.loads(schema_json_str)
                except Exception as e:
                    st.error(f"Invalid JSON configuration: {e}")
                    st.stop()
                    
                sources = []
                temp_dir = tempfile.mkdtemp()
                for f in all_files:
                    path = os.path.join(temp_dir, f.name)
                    with open(path, "wb") as out:
                        out.write(f.getvalue())
                    sources.append(Source(type=detect_source_type(f.name), path=path))
                    
                progress_bar = st.progress(0, text="Initializing Batch Pipeline...")
                
                def update_progress(stage, current, total):
                    if total > 0:
                        pct = min(100, int((current / total) * 100))
                        progress_bar.progress(pct, text=f"{stage}: {current} / {total}")
                
                # Instantiate runner directly with the provided JSON configs
                runner = PipelineRunner(pipeline_config, output_schema)
                
                # Phase 1: Extraction & Clustering
                clusters, source_results, norm_log, run_id, start_time = runner.run_phase_1(sources, on_progress=update_progress)
                
                # Phase 2: Merging & Projection
                for c in clusters:
                    c.requires_review = False
                    
                result = runner.run_phase_2(
                    clusters=clusters,
                    source_results=source_results,
                    normalization_log=norm_log,
                    run_id=run_id,
                    start_time=start_time,
                    projection_config=output_schema,
                    on_progress=update_progress
                )
            
            progress_bar.empty()
            st.session_state.final_result = result
            st.session_state.pipeline_phase = "results"
            st.rerun()

elif st.session_state.pipeline_phase == "results":
    res = st.session_state.final_result
    
    st.markdown('<h2 style="color: var(--primary-brown)">Batch Processing Dashboard</h2>', unsafe_allow_html=True)
    
    if st.button("← Process Another Batch"):
        st.session_state.pipeline_phase = "upload"
        st.session_state.final_result = None
        st.rerun()
        
    summary = res.summary
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Files Processed", summary.get("files_processed", 0))
    col2.metric("Candidates Detected", summary.get("candidates_detected", 0))
    col3.metric("Duplicates Merged", summary.get("duplicates_merged", 0))
    col4.metric("Failed Files", summary.get("failed_files", 0))
    
    st.subheader("Export Options")
    
    combined_json = {
        "summary": summary,
        "profiles": res.profiles
    }
    json_str = json.dumps(combined_json, indent=2)
    
    import re
    
    # Create ZIP archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("summary.json", json.dumps(summary, indent=2))
        zip_file.writestr("quality_report.json", json.dumps(res.report, indent=2))
        for p in res.profiles:
            cid = p.get("candidate_id", uuid.uuid4().hex[:8])
            raw_name = p.get("full_name") or p.get("candidate_name") or "Unknown"
            clean_name = re.sub(r'[^a-zA-Z0-9]', '_', str(raw_name)).strip('_')
            filename = f"candidates/{clean_name}_{cid}.json"
            zip_file.writestr(filename, json.dumps(p, indent=2))
            
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            label="Download Combined JSON",
            data=json_str,
            file_name="batch_candidates.json",
            mime="application/json"
        )
    with col_dl2:
        st.download_button(
            label="Download ZIP Archive",
            data=zip_buffer.getvalue(),
            file_name="batch_candidates_archive.zip",
            mime="application/zip"
        )
    
    st.subheader("Generated Candidates")
    for p in res.profiles:
        name = p.get('full_name') or p.get('candidate_name') or 'Unknown Candidate'
        with st.expander(f"{name} - {p.get('candidate_id', '')}"):
            st.json(p)
    st.markdown('</div>', unsafe_allow_html=True)
