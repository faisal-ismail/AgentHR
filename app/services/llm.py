"""LLM client abstraction for AgentHR.

Wraps Amazon Bedrock (via boto3 bedrock-runtime converse API) behind a clean
interface so the rest of the application never cares whether it is talking to
a live foundation model (Amazon Nova Pro / Claude) or the deterministic offline mock.
``get_llm()`` returns the active instance based on ``LLM_BACKEND``.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.config import settings


class BaseLLM:
    backend = "base"

    def generate(self, prompt: str) -> str:
        raise NotImplementedError

    def generate_json(self, prompt: str) -> dict[str, Any]:
        text = self.generate(prompt)
        return _extract_json(text)


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction from a model response."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}


class BedrockLLM(BaseLLM):
    backend = "bedrock"

    def __init__(self) -> None:
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self._model_id = settings.bedrock_model_id

    def generate(self, prompt: str) -> str:
        resp = self._client.converse(
            modelId=self._model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={
                "temperature": 0.2,
                "maxTokens": 2048,
            },
        )
        content_list = resp.get("output", {}).get("message", {}).get("content", [])
        texts = [c.get("text", "") for c in content_list if "text" in c]
        return "".join(texts).strip()


class MockLLM(BaseLLM):
    """Deterministic offline fallback — used for local demos & smoke tests.

    The mock is deliberately rule-based so the pipeline runs predictably offline:
    structured extraction and email drafting never depend on external connectivity.
    """

    backend = "mock"

    def generate(self, prompt: str) -> str:
        if "email" in prompt.lower():
            return _mock_email(prompt)
        return "{}"


def _mock_email(prompt: str) -> str:
    """Compose a deterministic candidate email based on the prompt instructions."""
    lower = prompt.lower()
    if "reject" in lower or "regret" in lower:
        return (
            "Dear Candidate,\n\n"
            "Thank you for your interest in the role. After careful review we have "
            "decided to move forward with other candidates whose profiles more "
            "closely match our current needs.\n\n"
            "We appreciate your time and wish you the best in your career search.\n\n"
            "Regards,\nAgentHR — Talent Acquisition Team"
        )
    if "interview" in lower or "invite" in lower:
        return (
            "Dear Candidate,\n\n"
            "Great news — we were impressed by your application and would like to "
            "invite you to an interview. Please confirm your availability for the "
            "proposed time slot.\n\n"
            "We look forward to speaking with you soon.\n\n"
            "Regards,\nAgentHR — Talent Acquisition Team"
        )
    return (
        "Dear Candidate,\n\n"
        "Thank you for your application. Our team is reviewing your profile and "
        "will be in touch shortly.\n\n"
        "Regards,\nAgentHR — Talent Acquisition Team"
    )


@lru_cache
def get_llm() -> BaseLLM:
    if settings.is_mock_llm:
        return MockLLM()
    try:
        return BedrockLLM()
    except Exception:
        return MockLLM()
