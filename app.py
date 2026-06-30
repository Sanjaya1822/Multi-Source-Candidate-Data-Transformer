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

    :root {
        --primary-brown: #5d4037;
        --secondary-brown: #8d6e63;
        --bg-color: #fbf7f4;
        --text-main: #3e2723;
        --card-bg: #ffffff;
        --border-light: #efebe9;
        --success: #4caf50;
    }
    
    .stApp {
        background-color: var(--bg-color);
        color: var(--text-main);
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    
    .header-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.25rem 2.5rem;
        background-color: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid rgba(93, 64, 55, 0.1);
        box-shadow: 0 4px 20px rgba(93, 64, 55, 0.03);
        margin-bottom: 2.5rem;
    }
    
    .header-title {
        color: var(--primary-brown);
        font-weight: 700;
        font-size: 1.75rem;
        margin: 0;
    }
    
    .saas-card {
        background: var(--card-bg);
        border-radius: 16px;
        padding: 2rem;
        box-shadow: 0 4px 12px rgba(93, 64, 55, 0.03);
        border: 1px solid rgba(239, 235, 233, 0.8);
        margin-bottom: 1.5rem;
    }
    
    .card-title {
        color: var(--primary-brown);
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 1.5rem;
        border-bottom: 2px solid var(--border-light);
        padding-bottom: 0.75rem;
    }

    div.stButton > button {
        background-color: var(--primary-brown);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        width: 100%;
    }
    
    div.stButton > button:hover {
        background-color: var(--secondary-brown);
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-container">
    <div class="header-title">DataTransformer Batch Processing</div>
    <div style="color: #795548; font-weight: 500;">Enterprise Scale (up to 1000 files)</div>
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

if st.session_state.pipeline_phase == "upload":
    st.sidebar.markdown("### Output Configuration")
    
    selected_fields = st.sidebar.multiselect(
        "Select Fields", 
        options=["full_name", "emails", "phones", "location", "links", "headline", "years_experience", "skills", "experience", "education", "projects", "certifications"], 
        default=["full_name", "emails", "phones", "location", "skills", "experience"]
    )
    
    st.session_state.projection_config = {
        "fields": selected_fields,
        "include_confidence": True,
        "include_provenance": True,
        "on_missing": "null"
    }
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown('<div class="saas-card"><div class="card-title">Structured Sources</div>', unsafe_allow_html=True)
        structured_files = st.file_uploader("Upload ATS JSON or CSV", accept_multiple_files=True, type=["json", "csv"])
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="saas-card"><div class="card-title">Unstructured Sources</div>', unsafe_allow_html=True)
        unstructured_files = st.file_uploader("Upload Resumes or Notes", accept_multiple_files=True, type=["pdf", "docx", "doc", "txt"])
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Run Batch Pipeline"):
        all_files = (structured_files or []) + (unstructured_files or [])
        if not all_files:
            st.error("Please provide at least one valid source.")
        else:
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
            
            runner = get_runner()
            # Phase 1: Extraction & Clustering
            clusters, source_results, norm_log, run_id, start_time = runner.run_phase_1(sources, on_progress=update_progress)
            
            # Phase 2: Merging & Projection
            # For batch processing, we force manual review clusters to auto-merge or separate. We'll auto-merge here to prevent blocking 1000 files.
            for c in clusters:
                c.requires_review = False
                
            result = runner.run_phase_2(
                clusters=clusters,
                source_results=source_results,
                normalization_log=norm_log,
                run_id=run_id,
                start_time=start_time,
                projection_config=st.session_state.projection_config,
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
    
    st.markdown('<div class="saas-card"><div class="card-title">Export Options</div>', unsafe_allow_html=True)
    
    combined_json = {
        "summary": summary,
        "profiles": res.profiles
    }
    json_str = json.dumps(combined_json, indent=2)
    
    # Create ZIP archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("summary.json", json.dumps(summary, indent=2))
        zip_file.writestr("quality_report.json", json.dumps(res.report, indent=2))
        for p in res.profiles:
            cid = p.get("candidate_id", uuid.uuid4().hex[:8])
            zip_file.writestr(f"candidates/candidate_{cid}.json", json.dumps(p, indent=2))
            
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
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="saas-card"><div class="card-title">Generated Candidates</div>', unsafe_allow_html=True)
    for p in res.profiles:
        with st.expander(f"{p.get('full_name', 'Unknown Candidate')} - {p.get('candidate_id', '')}"):
            st.json(p)
    st.markdown('</div>', unsafe_allow_html=True)
