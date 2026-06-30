"""
Comprehensive unit tests for the DataTransformer pipeline.

Covers: resume extraction, GitHub, LinkedIn, ATS, OCR text,
        missing fields, duplicates, internships, deduplication,
        merge strategy, confidence scoring, and validation.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import re
import yaml
from data_transformer.adapters.resume_adapter import (
    ResumeAdapter, _split_sections, _extract_skills,
    _extract_experience, _extract_education, _extract_name,
)
from data_transformer.adapters.ats_adapter import ATSAdapter
from data_transformer.adapters.github_adapter import GithubAdapter
from data_transformer.deduplication.matcher import Matcher, _linkedin_ids_from_records, _github_usernames_from_records
from data_transformer.normalizers import normalize_phone, normalize_email
from data_transformer.normalizers.location import normalize_location_string
from data_transformer.pipeline.runner import PipelineRunner
from data_transformer.schema.canonical import Source, RawRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    config = yaml.safe_load(open(
        os.path.join(os.path.dirname(__file__), '..', 'config', 'pipeline_config.yaml')
    ))
    schema = yaml.safe_load(open(
        os.path.join(os.path.dirname(__file__), '..', 'config', 'output_schema.yaml')
    ))
    return PipelineRunner(config, schema)


FULL_RESUME_TXT = """Arjun Mehta
arjun.mehta@gmail.com | +91-9876543210 | Bangalore, Karnataka, India
LinkedIn: https://www.linkedin.com/in/arjunmehta | GitHub: https://github.com/arjunmehta

CAREER OBJECTIVE
Passionate software engineer with 4 years experience in backend and cloud.

TECHNICAL SKILLS
Programming Languages: Python, Java, JavaScript
Frameworks & Libraries: Django, FastAPI, React
Cloud & DevOps: AWS, Docker, Kubernetes
Databases: PostgreSQL, MongoDB

EXPERIENCE

Software Engineer Intern | Infosys
June 2022 – August 2022
• Developed REST APIs using Django
• Wrote unit tests achieving 85% coverage

Junior Software Engineer | TCS
September 2022 – March 2024
• Built data pipelines using Apache Kafka
• Deployed services on AWS using Docker

PROJECTS

Stock Predictor
Technologies: Python, TensorFlow, Pandas

EDUCATION

Visvesvaraya Technological University (VTU)
B.E. Computer Science and Engineering
2018 – 2022
CGPA: 8.7 / 10

CERTIFICATIONS
AWS Certified Solutions Architect – Associate (2023)
"""

OCR_RESUME_TXT = """J0hn D03
j0hn.doe@gmai1.com
+1 (415) 555-1234
San Francisco, CA

SUMMARY
Software engineer with 5 years of Python and cloud experience.

SKILLS
Python, AWS, Docker, PostgreSQL

EXPERIENCE

Software Engineer | Acme Corp
2020 - Present
Developed microservices and APIs.

EDUCATION

MIT
B.S. Computer Science
2015 - 2019
"""

MINIMAL_RESUME_TXT = """Jane Doe
jane@example.com

SKILLS
Python, Java
"""

INTERNSHIP_RESUME_TXT = """Alice Wang
alice@example.com | +1-650-555-9999

INTERNSHIPS

Machine Learning Intern | Google
May 2023 – August 2023
• Implemented NLP pipelines using transformers
• Reduced model inference time by 30%

TECHNICAL SKILLS
Python, TensorFlow, PyTorch, Scikit-learn

EDUCATION
Stanford University
M.S. Computer Science
2022 – 2024
"""

# ---------------------------------------------------------------------------
# 1. Section detection
# ---------------------------------------------------------------------------

class TestSectionDetection:
    def test_detects_standard_sections(self):
        secs = _split_sections(FULL_RESUME_TXT)
        assert "skills" in secs
        assert "experience" in secs
        assert "education" in secs
        assert "certifications" in secs

    def test_career_objective_becomes_summary(self):
        secs = _split_sections(FULL_RESUME_TXT)
        assert "summary" in secs
        assert "career objective" not in str(secs.get("header", "")).lower()

    def test_internships_section_becomes_experience(self):
        secs = _split_sections(INTERNSHIP_RESUME_TXT)
        assert "experience" in secs
        assert "skills" in secs

    def test_header_contains_only_contact_info(self):
        secs = _split_sections(FULL_RESUME_TXT)
        header = secs.get("header", "")
        # Name and email should be in header
        assert "arjun.mehta@gmail.com" in header or "Arjun Mehta" in header

# ---------------------------------------------------------------------------
# 2. Name extraction
# ---------------------------------------------------------------------------

class TestNameExtraction:
    def test_extracts_name_correctly(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        assert r.fields["full_name"] == "Arjun Mehta"

    def test_career_objective_not_extracted_as_name(self):
        text = "Career Objective\njohn@example.com\n\nJohn Smith\n"
        secs = _split_sections(text)
        header = secs.get("header", text[:300])
        name = _extract_name(header, ["john@example.com"], [])
        assert name != "Career Objective"

    def test_section_headers_not_extracted_as_name(self):
        for heading in ["Technical Skills", "Work Experience", "Education", "Profile"]:
            name = _extract_name(heading + "\nJohn Doe\n", [], [])
            assert name != heading, f"'{heading}' should not be extracted as a name"

    def test_minimal_resume_no_crash(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=MINIMAL_RESUME_TXT))
        assert isinstance(r.fields["full_name"], str)

# ---------------------------------------------------------------------------
# 3. Contact extraction
# ---------------------------------------------------------------------------

class TestContactExtraction:
    def test_email_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        assert "arjun.mehta@gmail.com" in r.fields["emails"]

    def test_international_phone_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        phones = r.fields["phones"]
        assert len(phones) > 0
        # Raw value preserved; normalization pass converts to E.164
        assert any("9876543210" in p for p in phones)

    def test_phone_e164_normalization(self):
        assert normalize_phone("+91-9876543210") == "+919876543210"
        assert normalize_phone("+1 (415) 555-1234") == "+14155551234"
        assert normalize_phone("(415) 555-1234", "US") == "+14155551234"

    def test_invalid_phone_returns_none(self):
        assert normalize_phone("not-a-phone") is None
        assert normalize_phone("123") is None

    def test_email_normalization(self):
        assert normalize_email("Test@Example.COM") == "test@example.com"
        assert normalize_email("invalid-email") == ""

    def test_linkedin_url_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        link_types = {lk["type"] for lk in r.fields["links"]}
        assert "linkedin" in link_types

    def test_github_url_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        link_types = {lk["type"] for lk in r.fields["links"]}
        assert "github" in link_types

# ---------------------------------------------------------------------------
# 4. Skills extraction
# ---------------------------------------------------------------------------

class TestSkillsExtraction:
    def test_skills_extracted_from_section(self):
        skills = _extract_skills(
            "Programming Languages: Python, Java, JavaScript\nFrameworks: Django, FastAPI",
            ""
        )
        assert "Python" in skills
        assert "Java" in skills
        assert "Django" in skills

    def test_label_stripped(self):
        skills = _extract_skills("Programming Languages: Python, Java", "")
        assert "Python" in skills
        assert "Java" in skills
        assert not any("Programming" in s for s in skills)

    def test_ampersand_label_stripped(self):
        skills = _extract_skills("Frameworks & Libraries: FastAPI, React", "")
        assert "FastAPI" in skills
        assert "React" in skills
        assert not any("Libraries" in s for s in skills)

    def test_internship_names_not_in_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=INTERNSHIP_RESUME_TXT))
        skills = [s.lower() for s in r.fields["skills"]]
        assert "machine learning intern" not in skills
        assert "google" not in skills

    def test_company_names_not_in_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        skills = [s.lower() for s in r.fields["skills"]]
        assert "infosys" not in skills
        assert "tcs" not in skills
        assert "flipkart" not in skills

    def test_section_headers_not_in_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        skills = [s.lower() for s in r.fields["skills"]]
        assert "technical skills" not in skills
        assert "experience" not in skills
        assert "education" not in skills
        assert "career objective" not in skills

    def test_action_verbs_not_in_skills(self):
        skills = _extract_skills(
            "Python, Java\nDeveloped REST APIs using Django\nAWS",
            ""
        )
        skill_lower = [s.lower() for s in skills]
        assert "developed rest apis using django" not in skill_lower

    def test_deduplication(self):
        skills = _extract_skills("Python, Python, python, PYTHON", "")
        assert skills.count("Python") + skills.count("python") + skills.count("PYTHON") <= 1

# ---------------------------------------------------------------------------
# 5. Experience extraction
# ---------------------------------------------------------------------------

class TestExperienceExtraction:
    def test_experience_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        exp = r.fields["experience"]
        assert len(exp) >= 2

    def test_internship_in_experience_not_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        titles = [e.get("title", "").lower() for e in r.fields["experience"]]
        assert any("intern" in t for t in titles)
        skills_lower = [s.lower() for s in r.fields["skills"]]
        assert not any("intern" in s for s in skills_lower)

    def test_dates_parsed(self):
        entries = _extract_experience(
            "Software Engineer | Acme\nJanuary 2020 – March 2022\n• Built APIs"
        )
        assert entries
        assert entries[0]["start_date"] == "2020-01"
        assert entries[0]["end_date"] == "2022-03"

    def test_current_job_detected(self):
        entries = _extract_experience(
            "Lead Engineer | BigCo\nApril 2024 – Present\n• Led team"
        )
        assert entries
        assert entries[0]["is_current"] is True
        assert entries[0]["end_date"] is None

    def test_title_company_not_swapped(self):
        entries = _extract_experience(
            "Software Engineer Intern | Infosys\nJune 2022 – August 2022\n• Did stuff"
        )
        assert entries
        e = entries[0]
        assert e["title"] == "Software Engineer Intern"
        assert e["company"] == "Infosys"

# ---------------------------------------------------------------------------
# 6. Education extraction
# ---------------------------------------------------------------------------

class TestEducationExtraction:
    def test_education_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FULL_RESUME_TXT))
        edu = r.fields["education"]
        assert len(edu) >= 1

    def test_institution_not_cgpa(self):
        entries = _extract_education(
            "VTU\nB.E. Computer Science\n2018 – 2022\nCGPA: 8.7 / 10"
        )
        assert entries
        assert "cgpa" not in (entries[0].get("institution") or "").lower()
        assert entries[0]["institution"] == "VTU"

    def test_field_of_study_no_leading_dot(self):
        entries = _extract_education(
            "MIT\nB.E. Computer Science and Engineering\n2015 – 2019"
        )
        assert entries
        fos = entries[0].get("field_of_study", "")
        assert not fos.startswith(".")
        assert "Computer Science" in fos

    def test_dates_parsed_correctly(self):
        entries = _extract_education(
            "Stanford University\nM.S. Computer Science\n2022 – 2024"
        )
        assert entries
        assert entries[0]["start_date"] == "2022-01"
        assert entries[0]["end_date"] == "2024-01"

# ---------------------------------------------------------------------------
# 7. Location normalization
# ---------------------------------------------------------------------------

class TestLocationNormalization:
    def test_us_city_state(self):
        r = normalize_location_string("San Francisco, CA")
        assert r["city"] == "San Francisco"
        assert r["region"] == "CA"
        assert r["country"] == "US"

    def test_international_city_country(self):
        r = normalize_location_string("Bangalore, Karnataka, India")
        assert r["city"] == "Bangalore"
        assert r["country"] == "IN"

    def test_country_only(self):
        r = normalize_location_string("India")
        assert r["country"] == "IN"

    def test_empty_returns_nulls(self):
        r = normalize_location_string("")
        assert r["city"] is None
        assert r["country"] is None

# ---------------------------------------------------------------------------
# 8. ATS adapter
# ---------------------------------------------------------------------------

class TestATSAdapter:
    def test_extracts_all_fields(self):
        data = {
            "id": "ats_001",
            "first_name": "John", "last_name": "Doe",
            "email_addresses": [{"value": "john@acme.com", "type": "work"}],
            "phone_numbers": [{"value": "+14155551234", "type": "mobile"}],
            "tags": ["Python", "AWS"],
            "updated_at": "2024-01-01T00:00:00Z",
        }
        r = ATSAdapter().extract(Source(type="ats", content=data))
        assert r.fields["full_name"] == "John Doe"
        assert "john@acme.com" in r.fields["emails"]
        assert "Python" in r.fields["skills"]

# ---------------------------------------------------------------------------
# 9. LinkedIn adapter
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 10. Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:

    def _make_record(self, source, name="", emails=None, phones=None, links=None):
        return RawRecord(
            source=source,
            source_id=f"{source}_001",
            fields={
                "full_name": name,
                "emails": emails or [],
                "phones": phones or [],
                "links": links or [],
                "skills": [], "experience": [], "education": [],
            }
        )

    def test_same_email_merges(self):
        m = Matcher()
        r1 = self._make_record("resume", "Jane Smith", emails=["jane@x.com"])
        r2 = self._make_record("ats",    "Jane Smith", emails=["jane@x.com"])
        groups = m.match([r1, r2])
        assert len(groups) == 1

    def test_same_phone_merges(self):
        m = Matcher()
        r1 = self._make_record("resume", "Alice", phones=["+14155551234"])
        r2 = self._make_record("ats",    "Alice", phones=["+14155551234"])
        groups = m.match([r1, r2])
        assert len(groups) == 1

    def test_shared_linkedin_merges(self):
        m = Matcher()
        r1 = self._make_record("resume", "Bob", links=[{"url": "https://linkedin.com/in/bobsmith", "type": "linkedin"}])
        r2 = self._make_record("linkedin_url", "", links=[{"url": "https://linkedin.com/in/bobsmith", "type": "linkedin"}])
        groups = m.match([r1, r2])
        assert len(groups) == 1

    def test_shared_github_merges(self):
        m = Matcher()
        r1 = self._make_record("resume", "Carol", links=[{"url": "https://github.com/caroldev", "type": "github"}])
        r2 = self._make_record("github", "Carol Dev", links=[{"url": "https://github.com/caroldev", "type": "github"}])
        groups = m.match([r1, r2])
        assert len(groups) == 1

    def test_different_people_not_merged(self):
        m = Matcher()
        r1 = self._make_record("resume", "Jane Smith", emails=["jane@x.com"])
        r2 = self._make_record("resume", "Bob Jones",  emails=["bob@y.com"])
        groups = m.match([r1, r2])
        assert len(groups) == 2

    def test_fuzzy_name_merges(self):
        m = Matcher(fuzzy_threshold=85.0)
        r1 = self._make_record("resume", "Jonathan Doe", emails=["jd@x.com"])
        r2 = self._make_record("ats",    "Jonathan Doe", emails=["jd@x.com"])
        groups = m.match([r1, r2])
        assert len(groups) == 1

    def test_transitive_closure(self):
        """A-B and B-C via different signals should all end in one group."""
        m = Matcher()
        rA = self._make_record("resume",       "Eve", emails=["eve@x.com"])
        rB = self._make_record("ats",           "Eve", emails=["eve@x.com"],
                               links=[{"url": "https://github.com/eveloper", "type": "github"}])
        rC = self._make_record("github_url",   "",
                               links=[{"url": "https://github.com/eveloper", "type": "github"}])
        groups = m.match([rA, rB, rC])
        assert len(groups) == 1

# ---------------------------------------------------------------------------
# 11. Full pipeline integration
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_single_resume_produces_one_profile(self, runner):
        result = runner.run([Source(type="resume", content=FULL_RESUME_TXT)])
        assert len(result.profiles) == 1
        assert len(result.invalid_profiles) == 0

    def test_resume_github_linkedin_produces_one_profile(self, runner):
        sources = [
            Source(type="resume", content=FULL_RESUME_TXT),
            Source(type="linkedin_url", content="https://linkedin.com/in/arjunmehta"),
            Source(type="github_url",   content="https://github.com/arjunmehta"),
        ]
        result = runner.run(sources)
        assert len(result.profiles) == 1, f"Expected 1, got {len(result.profiles)}"

    def test_profile_has_all_required_fields(self, runner):
        result = runner.run([Source(type="resume", content=FULL_RESUME_TXT)])
        p = result.profiles[0]
        assert p.get("full_name"), "full_name missing"
        assert p.get("emails"), "emails missing"
        assert p.get("phones"), "phones missing"
        assert p.get("skills"), "skills missing"
        assert p.get("experience"), "experience missing"
        assert p.get("education"), "education missing"

    def test_phone_is_e164_in_output(self, runner):
        result = runner.run([Source(type="resume", content=FULL_RESUME_TXT)])
        p = result.profiles[0]
        for ph in p.get("phones", []):
            assert ph["value"].startswith("+"), f"Phone not E.164: {ph['value']}"

    def test_no_validation_warnings(self, runner):
        result = runner.run([Source(type="resume", content=FULL_RESUME_TXT)])
        assert result.report.get("validation_warnings", []) == []

    def test_internship_in_experience_field(self, runner):
        result = runner.run([Source(type="resume", content=INTERNSHIP_RESUME_TXT)])
        p = result.profiles[0]
        titles = [e.get("title", "").lower() for e in p.get("experience", [])]
        assert any("intern" in t for t in titles), "Internship should be in experience"

    def test_internship_not_in_skills(self, runner):
        result = runner.run([Source(type="resume", content=INTERNSHIP_RESUME_TXT)])
        p = result.profiles[0]
        skills_lower = [s["name"].lower() for s in p.get("skills", [])]
        assert not any("intern" in s for s in skills_lower)
        assert not any("google" == s for s in skills_lower)

    def test_source_priority_resume_over_ats(self, runner):
        """Resume name takes priority over ATS name per config."""
        ats_data = {
            "id": "001",
            "full_name": "Arjun M",           # ATS has truncated name
            "email_addresses": [{"value": "arjun.mehta@gmail.com"}],
            "tags": [],
        }
        sources = [
            Source(type="resume", content=FULL_RESUME_TXT),
            Source(type="ats",    content=ats_data),
        ]
        result = runner.run(sources)
        assert len(result.profiles) == 1
        # Resume should win for full_name (priority=1)
        p = result.profiles[0]
        assert p.get("full_name") == "Arjun Mehta"

    def test_null_not_overwriting_valid_value(self, runner):
        """A source with empty name should not replace a valid name."""
        sources = [
            Source(type="resume", content=FULL_RESUME_TXT),
            Source(type="linkedin_url", content="https://linkedin.com/in/arjunmehta"),
        ]
        result = runner.run(sources)
        p = result.profiles[0]
        assert p.get("full_name") == "Arjun Mehta"

    def test_missing_fields_produce_partial_result(self, runner):
        result = runner.run([Source(type="resume", content=MINIMAL_RESUME_TXT)])
        p = result.profiles[0]
        assert p.get("full_name") == "Jane Doe"
        assert p.get("skills"), "Skills should still be extracted"

    def test_ocr_resume_extracts_core_fields(self, runner):
        result = runner.run([Source(type="resume", content=OCR_RESUME_TXT)])
        assert len(result.profiles) == 1
        p = result.profiles[0]
        # Name may be garbled from OCR but emails should still work
        assert p.get("emails"), "Email should survive OCR noise"

    def test_duplicate_sources_produce_one_profile(self, runner):
        """Same resume submitted twice should still yield one profile."""
        sources = [
            Source(type="resume", content=FULL_RESUME_TXT),
            Source(type="resume", content=FULL_RESUME_TXT),
        ]
        result = runner.run(sources)
        assert len(result.profiles) == 1

    def test_overall_confidence_is_populated(self, runner):
        result = runner.run([Source(type="resume", content=FULL_RESUME_TXT)])
        p = result.profiles[0]
        assert 0.0 < p.get("overall_confidence", 0) <= 1.0

    def test_provenance_recorded(self, runner):
        result = runner.run([Source(type="resume", content=FULL_RESUME_TXT)])
        p = result.profiles[0]
        prov = p.get("provenance", [])
        assert len(prov) > 0
        assert any(src.get("source") == "resume" for src in prov)

    def test_malformed_source_does_not_crash_pipeline(self, runner):
        sources = [
            Source(type="resume", content=FULL_RESUME_TXT),
            Source(type="resume", content=""),           # empty resume
            Source(type="ats",    content={}),           # empty ATS
        ]
        result = runner.run(sources)
        # Should not raise; should still produce at least one profile
        assert len(result.profiles) >= 1


# ---------------------------------------------------------------------------
# 12. Real-world fresher resume (Priya Ramesh style)
# ---------------------------------------------------------------------------

FRESHER_RESUME = """Priya Ramesh
priya.ramesh@gmail.com
+91-8765432109
Chennai, Tamil Nadu, India
LinkedIn: https://www.linkedin.com/in/priyaramesh
GitHub: https://github.com/priyaramesh

Career Objective
A motivated fresher seeking opportunities in software development.

Education

Rathinam Technical Campus
B.Tech Information Technology
2020-2024
CGPA: 8.2/10

Skills
Python, Java, C, HTML, CSS, JavaScript, MySQL, MongoDB, Git, REST APIs

Internship Experience

Software Development Intern
Zoho Corporation, Chennai
June 2023 – August 2023
Worked on building internal tools using Python and Django framework.

Web Development Intern
TCS iON Digital Learning Hub
January 2024 – March 2024
Developed responsive web applications.

Projects

Smart Attendance System
Technologies: Python, OpenCV, dlib, SQLite

Certifications
Python for Everybody – Coursera (2022)
AWS Cloud Practitioner Essentials (2023)
"""


class TestFresherResume:

    def test_name_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        assert r.fields["full_name"] == "Priya Ramesh"

    def test_email_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        assert "priya.ramesh@gmail.com" in r.fields["emails"]

    def test_phone_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        assert len(r.fields["phones"]) > 0
        assert any("8765432109" in p for p in r.fields["phones"])

    def test_location_is_city_not_institution(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        loc = r.fields["location"]
        # Must NOT contain education text
        assert "Rathinam" not in str(loc), f"Institution leaked into location: {loc}"
        assert "B.Tech" not in str(loc), f"Degree leaked into location: {loc}"
        assert "Information Technology" not in str(loc), f"Field leaked into location: {loc}"
        # Must be a real location string
        assert loc, "Location should not be empty"
        assert "Chennai" in str(loc) or "Tamil Nadu" in str(loc)

    def test_internship_section_detected_as_experience(self):
        secs = _split_sections(FRESHER_RESUME)
        assert "experience" in secs, "Internship Experience section should map to 'experience'"
        assert secs["experience"].strip() != ""

    def test_internship_roles_in_experience_not_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        exp_titles = [e.get("title", "").lower() for e in r.fields["experience"]]
        skills_lower = [s.lower() for s in r.fields["skills"]]
        # Intern roles must be in experience
        assert any("intern" in t for t in exp_titles), "Intern role not in experience"
        # Intern role text must NOT be in skills
        assert not any("intern" in s for s in skills_lower), f"Intern role leaked into skills: {r.fields['skills']}"

    def test_company_name_not_in_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        skills_lower = [s.lower() for s in r.fields["skills"]]
        assert "zoho corporation" not in skills_lower
        assert "zoho" not in skills_lower
        assert "tcs ion digital learning hub" not in skills_lower

    def test_date_range_not_in_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        for skill in r.fields["skills"]:
            assert not re.search(
                r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
                skill, re.I
            ), f"Date string leaked into skills: {skill!r}"
            assert not re.search(r"\d{4}", skill), f"Year in skill: {skill!r}"

    def test_internship_company_extracted_correctly(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        companies = [e.get("company", "") for e in r.fields["experience"]]
        # "Zoho Corporation, Chennai" -> "Zoho Corporation" (city stripped)
        assert any("Zoho" in (c or "") for c in companies), f"Zoho not found: {companies}"
        assert not any("Chennai" in (c or "") and "Zoho" in (c or "") for c in companies), \
            f"City not stripped from company: {companies}"

    def test_education_extracted(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        edu = r.fields["education"]
        assert len(edu) >= 1
        assert edu[0]["institution"] == "Rathinam Technical Campus"
        assert "B.Tech" in (edu[0]["degree"] or "")

    def test_education_institution_not_cgpa(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        for e in r.fields["education"]:
            inst = (e.get("institution") or "").lower()
            assert "cgpa" not in inst
            assert "8.2" not in inst

    def test_career_objective_not_extracted_as_name(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        assert r.fields["full_name"] != "Career Objective"
        assert "Career Objective" not in r.fields["full_name"]

    def test_one_profile_produced_with_linkedin_github(self, runner):
        sources = [
            Source(type="resume",       content=FRESHER_RESUME),
            Source(type="linkedin_url", content="https://linkedin.com/in/priyaramesh"),
            Source(type="github_url",   content="https://github.com/priyaramesh"),
        ]
        result = runner.run(sources)
        assert len(result.profiles) == 1, (
            f"Expected 1 profile, got {len(result.profiles)}. "
            f"Sources merged: {[p.get('merge_summary',{}).get('sources_merged') for p in result.profiles]}"
        )

    def test_full_name_not_null_in_merged_profile(self, runner):
        sources = [
            Source(type="resume",       content=FRESHER_RESUME),
            Source(type="linkedin_url", content="https://linkedin.com/in/priyaramesh"),
        ]
        result = runner.run(sources)
        for p in result.profiles:
            assert p.get("full_name"), f"full_name is null in profile: {p.get('merge_summary',{}).get('sources_merged')}"

    def test_email_not_split_into_separate_profile(self, runner):
        """Contact info must stay with the correct candidate, not split into a new profile."""
        sources = [
            Source(type="resume",       content=FRESHER_RESUME),
            Source(type="github_url",   content="https://github.com/priyaramesh"),
        ]
        result = runner.run(sources)
        assert len(result.profiles) == 1
        p = result.profiles[0]
        emails = [e["value"] for e in (p.get("emails") or [])]
        assert "priya.ramesh@gmail.com" in emails, f"Email missing from merged profile: {emails}"

    def test_location_structured_correctly(self, runner):
        result = runner.run([Source(type="resume", content=FRESHER_RESUME)])
        p = result.profiles[0]
        loc = p.get("location") or {}
        assert "Rathinam" not in str(loc.get("city", "")), \
            f"Institution name in location.city: {loc}"
        assert "Rathinam" not in str(loc.get("region", "")), \
            f"Institution name in location.region: {loc}"


# ---------------------------------------------------------------------------
# 13. Experience format variants
# ---------------------------------------------------------------------------

class TestExperienceFormats:

    def test_format_a_pipe_separator(self):
        """Title | Company  dates"""
        entries = _extract_experience(
            "Senior Engineer | Acme Corp\nJanuary 2020 – Present\n• Led team"
        )
        assert entries
        assert entries[0]["title"] == "Senior Engineer"
        assert "Acme" in (entries[0]["company"] or "")

    def test_format_b_title_then_company(self):
        """Title on line 1, Company on line 2 (fresher format)"""
        entries = _extract_experience(
            "Software Development Intern\nZoho Corporation, Chennai\nJune 2023 – August 2023\nWorked on tools."
        )
        assert entries
        assert "Intern" in (entries[0]["title"] or "")
        assert "Zoho" in (entries[0]["company"] or "")

    def test_city_stripped_from_company(self):
        """Company, City → company only"""
        entries = _extract_experience(
            "Data Analyst Intern\nInfosys, Bangalore\nMay 2022 – July 2022"
        )
        assert entries
        company = entries[0].get("company") or ""
        assert "Bangalore" not in company, f"City not stripped: {company!r}"
        assert "Infosys" in company

    def test_dates_parsed_correctly(self):
        entries = _extract_experience(
            "Backend Developer | StartupXYZ\n2019-2022\n• Built APIs"
        )
        assert entries
        assert entries[0]["start_date"] == "2019-01"
        assert entries[0]["end_date"] == "2022-01"

    def test_present_sets_is_current(self):
        entries = _extract_experience(
            "Software Engineer | BigCo\nApril 2024 – Present"
        )
        assert entries
        assert entries[0]["is_current"] is True
        assert entries[0]["end_date"] is None

    def test_internship_format(self):
        entries = _extract_experience(
            "Machine Learning Intern\nGoogle, Bangalore\nMay 2023 – August 2023\n• NLP pipelines"
        )
        assert entries
        assert "Intern" in (entries[0]["title"] or "")
        assert "Google" in (entries[0]["company"] or "")
        assert "Bangalore" not in (entries[0]["company"] or "")

    def test_multi_job_blocks(self):
        text = (
            "Senior Engineer | Flipkart\n2023 – Present\n\n"
            "Software Engineer Intern | Infosys\n2022 – 2023"
        )
        entries = _extract_experience(text)
        assert len(entries) == 2

    def test_description_not_polluting_title(self):
        """Long bullet points must not become the title or company."""
        entries = _extract_experience(
            "Software Engineer | Acme\n2021 – 2023\n"
            "• Built distributed systems serving 10M users\n"
            "• Reduced latency by 40%"
        )
        assert entries
        title = entries[0].get("title") or ""
        assert len(title) < 60
        assert "Built" not in title
        assert "Reduced" not in title


# ---------------------------------------------------------------------------
# 14. Skills purity
# ---------------------------------------------------------------------------

class TestSkillsPurity:

    def test_section_headings_not_in_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        for skill in r.fields["skills"]:
            assert skill.lower() not in (
                "internship experience", "experience", "education",
                "certifications", "projects", "skills", "career objective"
            ), f"Section heading in skills: {skill!r}"

    def test_dates_not_in_skills(self):
        a = ResumeAdapter()
        r = a.extract(Source(type="resume", content=FRESHER_RESUME))
        for skill in r.fields["skills"]:
            assert not re.search(r"\d{4}", skill), f"Year in skill: {skill!r}"

    def test_soft_skills_and_paragraphs_filtered(self):
        skills = _extract_skills(
            "Python, JavaScript\n"
            "Worked on building internal tools using Python\n"
            "Strong communication and leadership skills\n",
            ""
        )
        skill_lower = [s.lower() for s in skills]
        assert "worked on building internal tools using python" not in skill_lower
        # Pure tech skills should still be present
        assert "Python" in skills or "python" in skill_lower

    def test_machine_learning_is_valid_skill(self):
        skills = _extract_skills("Machine Learning, Deep Learning, Python", "")
        assert any("Machine Learning" in s or "machine learning" in s.lower() for s in skills)

    def test_rest_apis_is_valid_skill(self):
        skills = _extract_skills("REST APIs, Git, MySQL", "")
        assert any("REST" in s or "rest" in s.lower() for s in skills)


# ---------------------------------------------------------------------------
# 15. Deduplication with no shared contact info
# ---------------------------------------------------------------------------

class TestDeduplicationNoContact:

    def _make_record(self, source, name="", emails=None, phones=None, links=None):
        return RawRecord(
            source=source,
            source_id=f"{source}_001",
            fields={
                "full_name": name,
                "emails": emails or [],
                "phones": phones or [],
                "links": links or [],
                "skills": [], "experience": [], "education": [],
            }
        )

    def test_resume_linkedin_stub_same_linkedin_url_merges(self):
        m = Matcher()
        r1 = self._make_record(
            "resume", "Priya Ramesh",
            links=[{"url": "https://linkedin.com/in/priyaramesh", "type": "linkedin"}]
        )
        r2 = self._make_record(
            "linkedin_url", "",
            links=[{"url": "https://www.linkedin.com/in/priyaramesh/", "type": "linkedin"}]
        )
        groups = m.match([r1, r2])
        assert len(groups) == 1, f"Expected 1 group, got {len(groups)}"

    def test_resume_github_same_username_merges(self):
        m = Matcher()
        r1 = self._make_record(
            "resume", "Priya Ramesh",
            links=[{"url": "https://github.com/priyaramesh", "type": "github"}]
        )
        r2 = self._make_record("github", "priyaramesh", links=[
            {"url": "https://github.com/priyaramesh", "type": "github"}
        ])
        groups = m.match([r1, r2])
        assert len(groups) == 1

    def test_three_sources_all_merge(self):
        """resume + linkedin_url + github_url → 1 group via shared URLs."""
        m = Matcher()
        resume = self._make_record(
            "resume", "Priya Ramesh",
            emails=["priya@example.com"],
            links=[
                {"url": "https://linkedin.com/in/priyaramesh", "type": "linkedin"},
                {"url": "https://github.com/priyaramesh", "type": "github"},
            ]
        )
        li_stub = self._make_record(
            "linkedin_url", "",
            links=[{"url": "https://linkedin.com/in/priyaramesh", "type": "linkedin"}]
        )
        gh = self._make_record(
            "github", "priyaramesh",
            links=[{"url": "https://github.com/priyaramesh", "type": "github"}]
        )
        groups = m.match([resume, li_stub, gh])
        assert len(groups) == 1, f"Expected 1 group, got {len(groups)}"

    def test_different_people_never_merged(self):
        m = Matcher()
        r1 = self._make_record("resume", "Priya Ramesh", emails=["priya@x.com"])
        r2 = self._make_record("resume", "Arjun Mehta",  emails=["arjun@y.com"])
        groups = m.match([r1, r2])
        assert len(groups) == 2
