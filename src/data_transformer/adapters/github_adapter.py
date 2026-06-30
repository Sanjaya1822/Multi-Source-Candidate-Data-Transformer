"""
GitHub Adapter.

Reads GitHub API-style JSON profile data.
Trust score: 0.98 — GitHub data is reliable for identity verification.

Production swap-in: Replace load_from_file() with PyGithub or direct API calls
to GET /users/{username}.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_transformer.adapters.base import SourceAdapter
from data_transformer.schema.canonical import RawRecord, Source


class GitHubAdapter(SourceAdapter):
    """
    Adapter for GitHub profile JSON data.

    Expected structure (GitHub API user endpoint style):
    {
        "login": "janesmith",
        "name": "Jane Smith",
        "email": "jane@example.com",
        "location": "San Francisco, CA",
        "html_url": "https://github.com/janesmith",
        "bio": "Software engineer passionate about ML",
        "company": "TechCorp",
        "public_repos": 42,
        "followers": 100,
        "created_at": "2020-01-15T00:00:00Z",
        "languages": ["Python", "JavaScript", "TypeScript"]
    }
    """

    TRUST_SCORE = 0.98

    def can_handle(self, source: Source) -> bool:
        if source.type == "github":
            return True
        if source.path and "github" in source.path.lower():
            return True
        return False

    def get_trust_score(self) -> float:
        return self.TRUST_SCORE

    def extract(self, source: Source) -> RawRecord:
        data = self._load(source)

        # Name — fallback to login if missing (edge case: incomplete GitHub profile)
        name = data.get("name", "")
        if not name:
            name = data.get("login", "")

        # Emails
        emails = []
        if data.get("email"):
            emails.append(data["email"])

        # Location
        location = data.get("location", "")

        # Links
        links = []
        github_url = data.get("html_url", "")
        if github_url:
            links.append({"url": github_url, "type": "github"})

        # Experience — synthesize from company field if present
        experience = []
        if data.get("company"):
            experience.append({
                "company": data["company"],
                "title": "Software Engineer",
                "start_date": (data.get("created_at", "")[:7] if data.get("created_at") else ""),
                "end_date": None,
                "is_current": True,
                "description": data.get("bio", ""),
            })

        # Skills from languages
        skills = data.get("languages", [])
        skills = [s for s in skills if s]

        return RawRecord(
            source="github",
            source_id=data.get("login", ""),
            ingested_at=data.get("updated_at", data.get("created_at", "")),
            fields={
                "full_name": name,
                "emails": emails,
                "phones": [],
                "location": location,
                "links": links,
                "skills": skills,
                "experience": experience,
                "education": [],
            },
        )

    def _load(self, source: Source) -> dict[str, Any]:
        if source.content is not None:
            if isinstance(source.content, dict):
                return source.content
            return json.loads(source.content)
        if source.path:
            return json.loads(Path(source.path).read_text(encoding="utf-8"))
        raise ValueError("GitHubAdapter: no content or path provided")
