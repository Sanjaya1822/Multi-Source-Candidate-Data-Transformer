"""Adapters package."""
from .base import SourceAdapter
from .ats_adapter import ATSAdapter
from .linkedin_adapter import LinkedInAdapter
from .resume_adapter import ResumeAdapter
from .csv_adapter import CSVAdapter
from .notes_adapter import NotesAdapter
from .github_adapter import GitHubAdapter

__all__ = [
    "SourceAdapter",
    "ATSAdapter",
    "LinkedInAdapter",
    "ResumeAdapter",
    "CSVAdapter",
    "NotesAdapter",
    "GitHubAdapter"
]
