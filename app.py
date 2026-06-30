import streamlit as st
import json
import yaml
import time
from pathlib import Path
import tempfile
import sys
import os

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from data_transformer.schema.canonical import Source
from data_transformer.pipeline.runner import PipelineRunner
from data_transformer.pipeline.clusterer import CandidateCluster

# --- Configuration & Theme ---
st.set_page_config(page_title="DataTransformer", layout="wide")

# Cream and brown modern SaaS theme (no Bootstrap/Tailwind per requirements)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Base theme */
    :root {
        --primary-brown: #5d4037;
        --secondary-brown: #8d6e63;
        --accent-cream: #fff3e0;
        --bg-color: #fbf7f4;
        --text-main: #3e2723;
        --text-muted: #795548;
        --card-bg: #ffffff;
        --border-light: #efebe9;
        --success: #4caf50;
        --warning: #ff9800;
        --danger: #f44336;
    }
    
    .stApp {
        background-color: var(--bg-color);
        color: var(--text-main);
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    
    /* Hide Streamlit default branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Header styling */
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
        position: sticky;
        top: 0;
        z-index: 1000;
    }
    
    .header-title {
        color: var(--primary-brown);
        font-weight: 700;
        font-size: 1.75rem;
        margin: 0;
        letter-spacing: -0.02em;
    }
    
    /* Card styling */
    .saas-card {
        background: var(--card-bg);
        border-radius: 16px;
        padding: 2rem;
        box-shadow: 0 4px 12px rgba(93, 64, 55, 0.03), 0 1px 3px rgba(93, 64, 55, 0.05);
        border: 1px solid rgba(239, 235, 233, 0.8);
        margin-bottom: 1.5rem;
        transition: transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
    }
    
    .saas-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(93, 64, 55, 0.06), 0 4px 8px rgba(93, 64, 55, 0.04);
    }
    
    .card-title {
        color: var(--primary-brown);
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 1.5rem;
        border-bottom: 2px solid var(--border-light);
        padding-bottom: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Buttons */
    div.stButton > button {
        background-color: var(--primary-brown);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 500;
        font-size: 0.95rem;
        transition: all 0.2s ease-in-out;
        width: 100%;
        box-shadow: 0 2px 4px rgba(93, 64, 55, 0.1);
    }
    
    div.stButton > button:hover {
        background-color: var(--secondary-brown);
        box-shadow: 0 6px 16px rgba(93, 64, 55, 0.15);
        transform: translateY(-1px);
    }
    
    div.stButton > button:active {
        transform: translateY(1px);
        box-shadow: 0 1px 2px rgba(93, 64, 55, 0.1);
    }
    
    /* File uploader */
    .stFileUploader {
        border-radius: 12px;
    }
    
    /* Identity Review Alert */
    .review-alert {
        background-color: rgba(255, 152, 0, 0.1);
        border-left: 4px solid var(--warning);
        padding: 1.25rem;
        border-radius: 8px;
        margin-bottom: 1.5rem;
        color: var(--text-main);
        font-weight: 500;
    }
    
    /* Sidebar styling enhancements */
    [data-testid="stSidebar"] {
        background-color: #f7f3f0;
        border-right: 1px solid var(--border-light);
    }
</style>
""", unsafe_allow_html=True)

# Custom header
st.markdown("""
<div class="header-container">
    <div class="header-title">DataTransformer</div>
    <div style="color: var(--text-muted); font-size: 0.9rem; font-weight: 500;">v2.0 Enterprise</div>
</div>
""", unsafe_allow_html=True)


# --- Session State ---
if "pipeline_phase" not in st.session_state:
    st.session_state.pipeline_phase = "upload" # upload -> review -> results
if "clusters" not in st.session_state:
    st.session_state.clusters = []
if "pipeline_data" not in st.session_state:
    st.session_state.pipeline_data = {}
if "resolved_clusters" not in st.session_state:
    st.session_state.resolved_clusters = []
if "final_result" not in st.session_state:
    st.session_state.final_result = None

def reset_pipeline():
    st.session_state.pipeline_phase = "upload"
    st.session_state.clusters = []
    st.session_state.pipeline_data = {}
    st.session_state.resolved_clusters = []
    st.session_state.final_result = None

def detect_source_type(filename: str) -> str:
    fname = filename.lower()
    if fname.endswith(".json"):
        return "ats" if "ats" in fname else "resume"
    if fname.endswith(".csv"):
        return "csv"
    if fname.endswith(".txt"):
        return "resume" if "resume" in fname or "cv" in fname else "notes"
    return "resume" # fallback for pdf/docx

# --- Runner Instance ---
@st.cache_resource
def get_runner():
    config = yaml.safe_load((Path("config") / "pipeline_config.yaml").read_text())
    schema = yaml.safe_load((Path("config") / "output_schema.yaml").read_text())
    return PipelineRunner(config, schema)


# --- UI: Phase 1 (Upload) ---
if st.session_state.pipeline_phase == "upload":
    st.sidebar.markdown("### Projection Builder")
    
    # Initialize defaults in session state
    if "proj_fields" not in st.session_state:
        st.session_state.proj_fields = ["full_name", "emails", "phones", "location", "headline", "skills", "experience", "education"]
    if "proj_conf" not in st.session_state:
        st.session_state.proj_conf = True
    if "proj_prov" not in st.session_state:
        st.session_state.proj_prov = True
    if "proj_missing" not in st.session_state:
        st.session_state.proj_missing = "omit"
    if "proj_renames" not in st.session_state:
        st.session_state.proj_renames = [{"from": "full_name", "path": "candidate_name"}]
    if "proj_norm_phone" not in st.session_state:
        st.session_state.proj_norm_phone = "E164"
    if "proj_norm_skill" not in st.session_state:
        st.session_state.proj_norm_skill = "canonical"
        
    adv_mode = st.sidebar.toggle("Advanced Mode (Raw JSON)")
    
    if not adv_mode:
        all_options = ["full_name", "emails", "phones", "location", "links", "headline", "years_experience", "skills", "experience", "education", "projects", "certifications"]
        selected_fields = st.sidebar.multiselect("Select Fields", options=all_options, default=st.session_state.proj_fields)
        
        col_t1, col_t2 = st.sidebar.columns(2)
        inc_conf = col_t1.toggle("Include Confidence", value=st.session_state.proj_conf)
        inc_prov = col_t2.toggle("Include Provenance", value=st.session_state.proj_prov)
        
        on_missing = st.sidebar.selectbox("Missing Value Policy", ["omit", "null", "error"], index=["omit", "null", "error"].index(st.session_state.proj_missing))
        
        st.sidebar.markdown("**Field Renames**")
        renames = []
        rename_from = st.sidebar.selectbox("Original Field", ["(None)"] + all_options)
        rename_to = st.sidebar.text_input("New Name")
        if rename_from != "(None)" and rename_to:
            renames.append({"from": rename_from, "path": rename_to})
        elif st.session_state.proj_renames:
            renames = st.session_state.proj_renames
            
        st.sidebar.markdown("**Normalization**")
        n_phone = st.sidebar.selectbox("Phones Normalization", ["None", "E164"], index=1 if st.session_state.proj_norm_phone == "E164" else 0)
        n_skill = st.sidebar.selectbox("Skills Normalization", ["None", "canonical"], index=1 if st.session_state.proj_norm_skill == "canonical" else 0)
        
        # Build config obj
        norms = {}
        if n_phone != "None": norms["phones"] = n_phone
        if n_skill != "None": norms["skills"] = n_skill
        
        current_config = {
            "fields": selected_fields,
            "include_confidence": inc_conf,
            "include_provenance": inc_prov,
            "on_missing": on_missing,
            "renames": renames,
            "normalizations": norms
        }
        
        st.session_state.projection_config = current_config
        with st.sidebar.expander("Live JSON Preview"):
            st.json(current_config)
            
    else:
        # Advanced mode
        cfg_str = st.sidebar.text_area(
            "Raw JSON Config",
            value=json.dumps(st.session_state.get("projection_config", {}), indent=2),
            height=300
        )
        try:
            st.session_state.projection_config = json.loads(cfg_str)
        except Exception:
            st.sidebar.error("Invalid JSON configuration")

    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown('<div class="saas-card"><div class="card-title">Structured Sources</div>', unsafe_allow_html=True)
        structured_files = st.file_uploader("Upload ATS JSON or CSV", accept_multiple_files=True, type=["json", "csv"])
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col2:
        st.markdown('<div class="saas-card"><div class="card-title">Unstructured Sources</div>', unsafe_allow_html=True)
        unstructured_files = st.file_uploader("Upload Resumes or Notes", accept_multiple_files=True, type=["pdf", "docx", "doc", "txt"])
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Run Pipeline"):
        if not structured_files and not unstructured_files:
            st.error("Please provide at least one valid source to process.")
        else:
            with st.spinner("Extracting & Resolving Identities..."):
                sources = []
                temp_dir = tempfile.mkdtemp()
                
                # File Validation function
                def validate_file(f, f_type):
                    content = f.getvalue()
                    if not content or len(content) == 0:
                        return False, f"{f.name} is empty."
                        
                    if f_type == "json":
                        try:
                            data = json.loads(content.decode("utf-8"))
                            if not data:
                                return False, f"ATS JSON {f.name} is empty."
                        except:
                            return False, f"ATS JSON {f.name} is malformed or invalid."
                            
                    if f_type == "txt" or f_type == "csv":
                        if not content.decode("utf-8", errors="ignore").strip():
                            return False, f"{f.name} contains no readable text or records."
                            
                    return True, ""

                valid_files_count = 0
                validation_errors = []
                
                all_files = (structured_files or []) + (unstructured_files or [])
                
                for f in all_files:
                    f_type = detect_source_type(f.name)
                    is_valid, err_msg = validate_file(f, f.name.split('.')[-1].lower())
                    
                    if not is_valid:
                        validation_errors.append(err_msg)
                        continue
                        
                    # Save valid file
                    valid_files_count += 1
                    path = os.path.join(temp_dir, f.name)
                    with open(path, "wb") as out:
                        out.write(f.getvalue())
                    sources.append(Source(type=f_type, path=path))
                    
                if validation_errors:
                    for err in validation_errors:
                        st.error(err)
                        
                if valid_files_count == 0:
                    st.error("Execution stopped: All uploaded files are empty or invalid.")
                else:
                    runner = get_runner()
                    clusters, source_results, norm_log, run_id, start_time = runner.run_phase_1(sources)
                    
                    st.session_state.clusters = clusters
                    st.session_state.pipeline_data = {
                        "source_results": source_results,
                        "norm_log": norm_log,
                        "run_id": run_id,
                        "start_time": start_time
                    }
                    st.session_state.resolved_clusters = []
                    st.session_state.pipeline_phase = "review"
                    st.rerun()

# --- UI: Phase 2 (Identity Review) ---
elif st.session_state.pipeline_phase == "review":
    st.markdown('<h2 style="color: var(--primary-brown)">Identity Resolution Review</h2>', unsafe_allow_html=True)
    
    unresolved = [c for c in st.session_state.clusters if c.requires_review and c not in st.session_state.resolved_clusters]
    
    if not unresolved:
        with st.spinner("Merging candidates and applying schema..."):
            runner = get_runner()
            result = runner.run_phase_2(
                clusters=st.session_state.clusters,
                source_results=st.session_state.pipeline_data["source_results"],
                normalization_log=st.session_state.pipeline_data["norm_log"],
                run_id=st.session_state.pipeline_data["run_id"],
                start_time=st.session_state.pipeline_data["start_time"],
                projection_config=st.session_state.projection_config
            )
            st.session_state.final_result = result
            st.session_state.pipeline_phase = "results"
            st.rerun()
    else:
        # Show the first unresolved cluster
        target = unresolved[0]
        st.markdown(f'<div class="review-alert"><strong>Manual Review Required:</strong> {target.review_reason}</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="saas-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">Cluster ID: {target.cluster_id}</div>', unsafe_allow_html=True)
        
        cols = st.columns(len(target.records))
        for i, rec in enumerate(target.records):
            with cols[i]:
                st.write(f"**Source {i+1}: {rec.source.type}**")
                st.json({
                    "Name": rec.fields.get("full_name", ""),
                    "Emails": rec.fields.get("emails", []),
                    "Phones": rec.fields.get("phones", [])
                })
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Merge Anyway (Ignore Warning)", key=f"merge_{target.cluster_id}"):
                target.requires_review = False
                st.session_state.resolved_clusters.append(target)
                st.rerun()
        with col_btn2:
            if st.button("Separate into Distinct Candidates", key=f"sep_{target.cluster_id}"):
                # Split the cluster into individual clusters
                st.session_state.clusters.remove(target)
                for rec in target.records:
                    new_c = CandidateCluster(cluster_id=f"{target.cluster_id}_{uuid.uuid4().hex[:4]}", records=[rec])
                    st.session_state.clusters.append(new_c)
                    st.session_state.resolved_clusters.append(new_c)
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# --- UI: Phase 3 (Results) ---
elif st.session_state.pipeline_phase == "results":
    res = st.session_state.final_result
    
    st.markdown('<div style="display:flex; justify-content:space-between; align-items:center;">'
                '<h2 style="color: var(--primary-brown)">Pipeline Output</h2>'
                '</div>', unsafe_allow_html=True)
    
    if st.button("Start New Pipeline"):
        reset_pipeline()
        st.rerun()
        
    st.toast("Pipeline completed successfully!")
    
    col_out1, col_out2 = st.columns([1, 1])
    
    with col_out1:
        st.markdown('<div class="saas-card"><div class="card-title">Generated Canonical Profiles</div>', unsafe_allow_html=True)
        
        if res.profiles:
            json_str = json.dumps(res.profiles, indent=2)
            st.download_button(
                label="Export Profiles to JSON",
                data=json_str,
                file_name=f"candidates_{st.session_state.pipeline_data.get('run_id', 'export')}.json",
                mime="application/json"
            )
            
        for i, p in enumerate(res.profiles):
            with st.expander(f"Profile: {p.get('full_name', 'Unknown')} ({p.get('candidate_id')})"):
                st.json(p)
        if not res.profiles:
            st.info("No valid profiles generated.")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col_out2:
        st.markdown('<div class="saas-card"><div class="card-title">Quality Report</div>', unsafe_allow_html=True)
        st.json(res.report)
        
        if res.invalid_profiles:
            st.markdown('<div class="card-title" style="margin-top: 1rem; color: var(--danger)">Invalid Profiles</div>', unsafe_allow_html=True)
            for err in res.invalid_profiles:
                st.error(f"Candidate {err.get('candidate_id')}: {err.get('reason')}")
        st.markdown('</div>', unsafe_allow_html=True)
