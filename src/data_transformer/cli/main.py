"""
CLI Entrypoint using Typer.
"""
import json
import os
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console

from data_transformer.schema.canonical import Source
from data_transformer.pipeline.runner import PipelineRunner
from data_transformer.validation.validator import OutputValidator

app = typer.Typer(help="DataTransformer: Eightfold-style Candidate Merging Pipeline")
console = Console()


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.command()
def merge(
    input_dir: str = typer.Option(..., "--input", "-i", help="Directory containing source files"),
    config_file: str = typer.Option(..., "--config", "-c", help="Path to pipeline_config.yaml"),
    schema_file: str = typer.Option(None, "--schema", "-s", help="Path to output_schema.yaml"),
    output_file: str = typer.Option("output.json", "--output", "-o", help="Path to save merged JSON"),
):
    """Merge candidates from multiple sources."""
    console.print(f"[bold green]Starting DataTransformer[/bold green]")
    
    config = load_yaml(config_file)
    if not schema_file:
        schema_file = str(Path(config_file).parent / "output_schema.yaml")
    output_schema = load_yaml(schema_file)
    
    runner = PipelineRunner(config, output_schema)
    
    sources = []
    input_path = Path(input_dir)
    for file in input_path.rglob("*"):
        if file.is_file():
            ext = file.suffix.lower()
            src_type = "notes"
            if "ats" in file.name.lower(): src_type = "ats"
            elif "linkedin" in file.name.lower(): src_type = "linkedin"
            elif ext in [".pdf", ".docx", ".doc"]: src_type = "resume"
            elif "resume" in file.name.lower(): src_type = "resume"
            elif ext == ".csv": src_type = "csv"
            
            sources.append(Source(type=src_type, path=str(file)))
            
    console.print(f"Discovered [bold]{len(sources)}[/bold] sources in {input_dir}")
    
    result = runner.run(sources)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result.profiles, f, indent=2)
        
    console.print(f"[bold blue]Pipeline Completed![/bold blue]")
    console.print(f"Merged Profiles: {len(result.profiles)}")
    console.print(f"Output saved to: {output_file}")


@app.command()
def validate(
    input_file: str = typer.Option(..., "--input", "-i", help="Path to merged JSON file to validate")
):
    """Validate a merged JSON file against the output schema."""
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    validator = OutputValidator()
    
    all_valid = True
    for idx, profile in enumerate(data):
        res = validator.validate(profile)
        if not res.is_valid:
            all_valid = False
            console.print(f"[bold red]Profile {idx} Invalid:[/bold red]")
            for err in res.errors:
                console.print(f"  - {err}")
                
    if all_valid:
        console.print("[bold green]All profiles are valid according to the JSON Schema![/bold green]")
    else:
        raise typer.Exit(code=1)


@app.command()
def report(
    input_file: str = typer.Option(..., "--input", "-i", help="Path to merged JSON file")
):
    """Generate a quick summary from the merged output (needs merge_summary in output)."""
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    console.print(f"[bold]Quality Report for {input_file}[/bold]")
    console.print(f"Total Profiles: {len(data)}")
    
    total_conf = 0.0
    for p in data:
        total_conf += p.get("overall_confidence", 0.0)
        
    avg = total_conf / max(1, len(data))
    console.print(f"Average Confidence: [bold]{avg:.3f}[/bold]")
    
    # Show one profile summary if available
    if data and "merge_summary" in data[0]:
        console.print("\n[bold]Sample Merge Summary (Profile 1):[/bold]")
        console.print(json.dumps(data[0]["merge_summary"], indent=2))


@app.command()
def demo():
    """Run the built-in demo with sample data."""
    base = Path(__file__).parent.parent.parent.parent
    data_dir = base / "data" / "samples"
    conf_dir = base / "config"
    
    if not data_dir.exists():
        console.print(f"[bold red]Error: Sample data not found at {data_dir}[/bold red]")
        raise typer.Exit(code=1)
        
    merge(
        input_dir=str(data_dir),
        config_file=str(conf_dir / "pipeline_config.yaml"),
        schema_file=str(conf_dir / "output_schema.yaml"),
        output_file="demo_output.json"
    )
    console.print("\n[bold]Running Validation...[/bold]")
    validate(input_file="demo_output.json")


if __name__ == "__main__":
    app()
