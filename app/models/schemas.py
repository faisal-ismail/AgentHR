"""Pydantic schemas shared by the FastAPI API and the Streamlit frontend.

Validates all incoming requests and outgoing responses across the API boundary.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self, exclude_unset: bool = False) -> dict[str, Any]:
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def Field(default_factory=None, default=None):  # type: ignore
        return default_factory() if default_factory else default


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------
class JobCreate(BaseModel):
    title: str
    department: str = "General"
    description: str = ""
    mandatory: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)
    hiring_policy_ref: str = "data/policies/hiring_policy.md"
    posted_by: str = "hr"


class JobUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    mandatory: Optional[list[str]] = None
    preferred: Optional[list[str]] = None
    status: Optional[str] = None  # open | closed


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
class ApplicationCreate(BaseModel):
    job_id: str
    candidate_name: str
    candidate_email: str
    candidate_phone: str = ""
    cv_text: str = ""
    cv_filename: Optional[str] = None


class ApplicationOut(BaseModel):
    id: str
    job_id: str
    candidate_id: str
    candidate_name: str = ""
    candidate_email: str = ""
    status: str
    score: Optional[float] = None
    rationale: Optional[str] = None
    created_at: str = ""


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------
class CandidateProfile(BaseModel):
    name: str
    email: str
    phone: str = ""
    experience_years: Optional[float] = None
    education: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Human review (Policy engine escalation)
# --------------------------------------------------------------------------
class ReviewDecision(BaseModel):
    approved: bool
    decided_by: str = "hr"
    note: str = ""


# --------------------------------------------------------------------------
# Human In The Loop (HITL Approval Gate)
# --------------------------------------------------------------------------
class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str = "hr"
    note: str = ""


# --------------------------------------------------------------------------
# Amazon Bedrock AgentCore Runtime
# --------------------------------------------------------------------------
class AgentCoreInvocationRequest(BaseModel):
    prompt: Optional[str] = None
    application_id: Optional[str] = None


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


# --------------------------------------------------------------------------
# Health & Status
# --------------------------------------------------------------------------
class HealthOut(BaseModel):
    status: str
    store_backend: str
    llm_backend: str
    model: str
    agent: str = "RecruitmentCoordinatorAgent"


def to_camel(d: dict[str, Any]) -> dict[str, Any]:
    return d
