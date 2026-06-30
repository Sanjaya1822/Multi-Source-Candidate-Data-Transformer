"""Tests for conflict resolvers."""
from data_transformer.conflict_resolution import (
    PriorityOrderResolver, MajorityVoteResolver, 
    LatestWinsResolver, MockLLMResolver
)

def test_priority_order(sample_source_values):
    resolver = PriorityOrderResolver({"ats": 1, "linkedin": 2, "resume": 3})
    res = resolver.resolve("title", sample_source_values)
    assert res.value == "SDE III"
    assert "ats" in res.reasoning

def test_latest_wins(sample_source_values):
    resolver = LatestWinsResolver()
    res = resolver.resolve("title", sample_source_values)
    assert res.value == "Senior Software Engineer"
    assert "linkedin" in res.reasoning

def test_majority_vote(sample_source_values):
    # Add a duplicate value to force majority
    sample_source_values.append(
        sample_source_values[0].__class__(
            value="SDE III", source="csv", source_id="4", 
            ingested_at="2026-02-01T00:00:00Z", trust_score=0.7
        )
    )
    fallback = PriorityOrderResolver({"ats": 1})
    resolver = MajorityVoteResolver(fallback)
    res = resolver.resolve("title", sample_source_values)
    assert res.value == "SDE III"
    assert "majority vote" in res.reasoning

def test_mock_llm(sample_source_values):
    fallback = PriorityOrderResolver({"ats": 1})
    resolver = MockLLMResolver(fallback)
    res = resolver.resolve("title", sample_source_values)
    # Mock LLM picks highest trust score (ATS)
    assert res.value == "SDE III"
    assert "[MOCK LLM]" in res.reasoning
