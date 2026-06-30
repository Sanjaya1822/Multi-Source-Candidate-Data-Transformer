"""
LLM-Powered Conflict Resolution.
Addresses the 'wrong but confident' problem using semantic reasoning.
Includes a Mock implementation and a real Phi-3 backend.
"""
import json
from typing import List, Any
from .base import ConflictResolver, ResolvedValue, SourceValue


class LLMResolver(ConflictResolver):
    """
    Base class for LLM resolvers to handle the fallback pattern.
    """
    def __init__(self, fallback_resolver: ConflictResolver, confidence_threshold: float = 0.60):
        self.fallback = fallback_resolver
        self.confidence_threshold = confidence_threshold

    def resolve(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        valid_values = [v for v in values if v.value not in (None, "", [], {})]
        if len(valid_values) < 2:
            return self.fallback.resolve(field_name, values)

        try:
            result = self._call_llm(field_name, valid_values)
            if result.confidence < self.confidence_threshold:
                fallback_res = self.fallback.resolve(field_name, valid_values)
                fallback_res.reasoning = f"LLM confidence ({result.confidence}) below threshold. {fallback_res.reasoning}"
                return fallback_res
            return result
        except Exception as e:
            fallback_res = self.fallback.resolve(field_name, valid_values)
            fallback_res.reasoning = f"LLM failure: {e}. {fallback_res.reasoning}"
            return fallback_res

    def _call_llm(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        raise NotImplementedError


class MockLLMResolver(LLMResolver):
    """
    Simulates LLM inference for local testing without GPUs.
    Returns deterministic structured reasoning.
    """
    def _call_llm(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        import structlog
        log = structlog.get_logger()
        log.info("mock_llm_inference", field=field_name, num_sources=len(values))

        # Sort by trust to simulate LLM picking the best
        sorted_vals = sorted(values, key=lambda x: -x.trust_score)
        chosen = sorted_vals[0]

        reasoning = (
            f"[MOCK LLM] Evaluated {len(values)} conflicting sources. "
            f"Selected '{chosen.source}' due to highest structural reliability "
            f"({chosen.trust_score}) and semantic alignment with canonical standard for {field_name}."
        )

        return ResolvedValue(
            value=chosen.value,
            confidence=round(0.92, 4),
            provenance=[chosen.to_provenance()],
            reasoning=reasoning
        )


class PhiLLMResolver(LLMResolver):
    """
    Real integration with microsoft/Phi-3-mini-4k-instruct.
    Requires transformers and torch.
    """
    def __init__(self, fallback_resolver: ConflictResolver, model_name: str, **kwargs):
        super().__init__(fallback_resolver, **kwargs)
        try:
            from transformers import pipeline
            self.pipe = pipeline(
                "text-generation",
                model=model_name,
                trust_remote_code=True,
                device_map="auto"
            )
        except ImportError:
            raise ImportError("Please install optional dependencies: pip install .[llm]")

    def _call_llm(self, field_name: str, values: List[SourceValue]) -> ResolvedValue:
        # Build prompt context
        sources_str = ""
        for v in values:
            sources_str += f"- Source: {v.source} (Trust: {v.trust_score}, Updated: {v.ingested_at})\n  Value: {v.value}\n\n"

        prompt = f"""You are an expert HR data integrator resolving conflicts.
FIELD: {field_name}
SOURCES:
{sources_str}
Choose the most accurate value. Output ONLY valid JSON:
{{
    "chosen_source": "...",
    "confidence": 0.95,
    "reasoning": "Clear human-readable explanation"
}}
"""
        response = self.pipe(prompt, max_new_tokens=256, return_full_text=False)[0]['generated_text']

        # Parse JSON output
        try:
            parsed = json.loads(response[response.find('{'):response.rfind('}')+1])
            chosen_source_name = parsed["chosen_source"]

            chosen_value_obj = next((v for v in values if v.source == chosen_source_name), values[0])

            return ResolvedValue(
                value=chosen_value_obj.value,
                confidence=round(float(parsed.get("confidence", 0.8)), 4),
                provenance=[chosen_value_obj.to_provenance()],
                reasoning=parsed.get("reasoning", "LLM determined best fit")
            )
        except Exception:
            raise ValueError("LLM returned invalid JSON")
