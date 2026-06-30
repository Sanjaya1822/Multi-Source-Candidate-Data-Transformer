"""
FastAPI application for the DataTransformer pipeline.
"""
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import json
import tempfile
import os
from pathlib import Path
import requests

from data_transformer.schema.canonical import Source
from data_transformer.pipeline.runner import PipelineRunner
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI(
    title="DataTransformer API",
    description="Eightfold-style Candidate Merging Pipeline",
    version="2.0"
)

class HealthCheck(BaseModel):
    status: str

@app.get("/v1/health", response_model=HealthCheck)
def health_check():
    return {"status": "ok"}

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/index.html")

frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend"
app.mount("/ui", StaticFiles(directory=str(frontend_dir)), name="frontend")

@app.post("/v1/merge")
async def merge_candidates(
    config_json: str = Form(...),
    output_schema_json: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    github_url: str = Form(None),
    linkedin_url: str = Form(None)
):
    """
    Accepts pipeline config, output schema, and multiple source files.
    Returns merged canonical profiles + quality report.
    """
    try:
        config = json.loads(config_json)
        schema = json.loads(output_schema_json)
        
        # Auto-translate simple schema to Projector format if missing
        if "fields" not in schema:
            keys = list(schema.keys())
            if "candidate_id" not in keys:
                keys.append("candidate_id")
                
            fields_config = []
            for k in keys:
                fields_config.append({"path": k})
                
            schema = {
                "fields": fields_config,
                "include_confidence": False,
                "include_provenance": False,
                "on_missing": "null"
            }
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in config or schema")
        
    runner = PipelineRunner(config, schema)
    sources = []
    
    # Save uploaded files to temp dir so adapters can read them
    with tempfile.TemporaryDirectory() as tmpdir:
        for file in files:
            path = Path(tmpdir) / file.filename
            with open(path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
                
            # Naive type detection
            ext = path.suffix.lower()
            src_type = "notes"
            if "github" in file.filename.lower(): src_type = "github"
            elif "ats" in file.filename.lower(): src_type = "ats"
            elif "linkedin" in file.filename.lower(): src_type = "linkedin"
            elif ext in [".pdf", ".docx", ".doc"]: src_type = "resume"
            elif "resume" in file.filename.lower(): src_type = "resume"
            elif ext == ".csv": src_type = "csv"
            
            sources.append(Source(type=src_type, path=str(path)))
            
        # Handle URLs
        if github_url:
            # Extract username
            username = github_url.strip('/').split('/')[-1]
            try:
                resp = requests.get(f"https://api.github.com/users/{username}")
                if resp.status_code == 200:
                    gh_path = Path(tmpdir) / f"{username}_github.json"
                    with open(gh_path, "w", encoding="utf-8") as f:
                        f.write(resp.text)
                    sources.append(Source(type="github", path=str(gh_path)))
            except Exception as e:
                print(f"Failed to fetch GitHub: {e}")
                
        if linkedin_url:
            # For assignment purposes, mock LinkedIn data since scraping is blocked
            username = linkedin_url.strip('/').split('/')[-1]
            li_path = Path(tmpdir) / f"{username}_linkedin.json"
            with open(li_path, "w", encoding="utf-8") as f:
                json.dump({"linkedin_id": username, "name": username}, f)
            sources.append(Source(type="linkedin", path=str(li_path)))
            
        result = runner.run(sources)
        
    return {
        "report": result.report,
        "profiles": result.profiles,
        "invalid_profiles": result.invalid_profiles
    }
