"""The seven tools of RecruitmentCoordinatorAgent (Strands Agents SDK).

Read tools:
  1. get_candidate_profile   — structured candidate info extracted from the CV
  2. get_job_requirements    — job mandatory + preferred requirements
  3. get_hiring_policy       — the decision rules (policy-as-code)

Action tools (each writes records + updates application status + logs activity):
  4. check_interview_slots   — available, conflict-checked interview slots
  5. schedule_interview      — create interview record + add to recruiter calendar
  6. create_human_review     — escalate with reason + recommendation
  7. draft_candidate_email   — produce the final communication (ready_to_send)

Every action tool is idempotent (keyed on ``application_id``) so a re-run of
the agent never duplicates an interview / review / email.
"""
from __future__ import annotations

import contextvars
from pathlib import Path
from typing import Any, Optional

try:
    from strands import tool
except ImportError:  # pragma: no cover
    def tool(func=None, **kwargs):  # type: ignore
        if func is not None:
            return func
        def decorator(f):
            return f
        return decorator

from app.services.calendar import find_slot, list_available_slots
from app.services.llm import get_llm
from app.services.store import Store, get_store

# The active run context (set by the pipeline just before the agent runs).
_run_context: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "agenthr_run", default={}
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = PROJECT_ROOT / "data" / "policies" / "hiring_policy.md"
POLICY_REF = "data/policies/hiring_policy.md"


def set_run_context(application_id: str, run_id: str) -> None:
    _run_context.set({"application_id": application_id, "run_id": run_id})


def _store() -> Store:
    return get_store()


def _log(action: str, detail: dict[str, Any], level: str = "verbose") -> None:
    """Append a step to the active run's activity log (best-effort).

    ``level`` is ``"major"`` for headline milestones (phases, decisions, key
    actions) or ``"verbose"`` for fine-grained tool calls.
    """
    ctx = _run_context.get()
    run_id = ctx.get("run_id")
    if run_id:
        try:
            _store().append_activity_step(run_id, {"action": action, "level": level, **detail})
        except Exception:
            pass


def _app_ctx(application_id: str) -> dict[str, Any]:
    return {"application_id": application_id}


# ---------------------------------------------------------------------------
# 1. get_candidate_profile
# ---------------------------------------------------------------------------
@tool
def get_candidate_profile(application_id: str) -> dict[str, Any]:
    """Return the structured candidate profile for an application.

    Args:
        application_id: the id of the application to look up.
    """
    app = _store().get_application(application_id)
    if not app:
        return {"error": f"application {application_id} not found"}
    candidate = _store().get_candidate(app.get("candidate_id", "")) or {}
    profile = {
        "candidate_id": candidate.get("id"),
        "name": candidate.get("name"),
        "email": candidate.get("email"),
        "phone": candidate.get("phone"),
        "experience_years": candidate.get("experience_years"),
        "education": candidate.get("education", []),
        "skills": candidate.get("skills", []),
    }
    _log("get_candidate_profile", {"application_id": application_id, "profile": profile})
    return profile


# ---------------------------------------------------------------------------
# 2. get_job_requirements
# ---------------------------------------------------------------------------
@tool
def get_job_requirements(job_id: str) -> dict[str, Any]:
    """Return the mandatory and preferred requirements of a job.

    Args:
        job_id: the id of the job to look up.
    """
    job = _store().get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    requirements = {
        "job_id": job.get("id"),
        "title": job.get("title"),
        "department": job.get("department"),
        "mandatory": job.get("mandatory", []),
        "preferred": job.get("preferred", []),
    }
    _log("get_job_requirements", requirements)
    return requirements


# ---------------------------------------------------------------------------
# 3. get_hiring_policy
# ---------------------------------------------------------------------------
@tool
def get_hiring_policy() -> str:
    """Return the hiring policy text the agent must follow."""
    path = DEFAULT_POLICY_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        text = "No hiring policy file found — escalate to human review."
    _log("get_hiring_policy", {"policy": POLICY_REF, "characters": len(text)})
    return text


# ---------------------------------------------------------------------------
# 4. check_interview_slots
# ---------------------------------------------------------------------------
@tool
def check_interview_slots() -> dict[str, Any]:
    """Return the currently available interview slots (conflict-checked)."""
    slots = list_available_slots(_store())
    _log(
        "check_interview_slots",
        {"available_slots": [s.get("label") for s in slots], "count": len(slots)},
    )
    return {"available_slots": slots, "count": len(slots)}


# ---------------------------------------------------------------------------
# 5. schedule_interview
# ---------------------------------------------------------------------------
@tool
def schedule_interview(application_id: str, slot_start: Optional[str] = None) -> dict[str, Any]:
    """Schedule an interview for an application at an available slot.

    Creates an ``interviews`` record (which the recruiter calendar renders) and
    marks the application as ``interview``. Idempotent per application.

    Args:
        application_id: the application to schedule.
        slot_start: optional ISO slot start; picks the first free slot if omitted.
    """
    store = _store()
    app = store.get_application(application_id)
    if not app:
        return {"error": f"application {application_id} not found"}

    existing = store.get_interview_for_application(application_id)
    if existing:
        _log("schedule_interview", _app_ctx(application_id) | {"slot_start": existing.get("slot_start"), "status": "already_scheduled"}, level="major")
        return {"status": "already_scheduled", "interview": existing}

    slot = find_slot(store, slot_start)
    if not slot:
        _log("no_slot", _app_ctx(application_id), level="major")
        return {"error": "no available interview slot"}

    interview = {
        "application_id": application_id,
        "candidate_id": app.get("candidate_id"),
        "job_id": app.get("job_id"),
        "slot_start": slot["slot_start"],
        "slot_end": slot["slot_end"],
        "status": "scheduled",
    }
    interview_id = store.create_interview(interview)
    interview["id"] = interview_id

    store.update_application(application_id, {"status": "interview"})
    _log(
        "schedule_interview",
        _app_ctx(application_id) | {"interview_id": interview_id, "slot_start": slot["slot_start"], "slot_label": slot["label"]},
        level="major",
    )
    return {"status": "scheduled", "interview": interview, "slot_label": slot["label"]}


# ---------------------------------------------------------------------------
# 6. create_human_review
# ---------------------------------------------------------------------------
@tool
def create_human_review(application_id: str, reason: str, recommendation: str) -> dict[str, Any]:
    """Escalate an application to human review with a reason and recommendation.

    Args:
        application_id: the application to escalate.
        reason: why a human must look at it.
        recommendation: what the agent suggests the human do.
    """
    store = _store()
    app = store.get_application(application_id)
    if not app:
        return {"error": f"application {application_id} not found"}

    existing = store.get_human_review_for_application(application_id)
    if existing and existing.get("status") == "pending":
        _log("create_human_review", _app_ctx(application_id) | {"status": "already_pending"}, level="major")
        return {"status": "already_pending", "review": existing}

    review = {
        "application_id": application_id,
        "candidate_id": app.get("candidate_id"),
        "reason": reason,
        "recommendation": recommendation,
        "status": "pending",
    }
    review_id = store.create_human_review(review)
    review["id"] = review_id

    store.update_application(application_id, {"status": "human_review"})
    _log("create_human_review", _app_ctx(application_id) | {"review_id": review_id, "reason": reason}, level="major")
    return {"status": "pending", "review": review}


# ---------------------------------------------------------------------------
# 7. draft_candidate_email
# ---------------------------------------------------------------------------
@tool
def draft_candidate_email(
    application_id: str,
    email_type: str,
    subject: str = "",
    body: str = "",
) -> dict[str, Any]:
    """Draft and store a candidate email (ready_to_send).

    If ``body`` is empty, the email copy is composed automatically (Bedrock in
    cloud mode, deterministic template in mock mode).

    Args:
        application_id: the application this email concerns.
        email_type: one of interview_invite | rejection | review_notice.
        subject: optional subject line.
        body: optional body text (auto-composed when omitted).
    """
    store = _store()
    app = store.get_application(application_id)
    if not app:
        return {"error": f"application {application_id} not found"}
    candidate = store.get_candidate(app.get("candidate_id", "")) or {}

    existing = store.get_email_for_application(application_id, email_type)
    if existing:
        _log("draft_candidate_email", _app_ctx(application_id) | {"email_type": email_type, "status": "already_drafted"}, level="major")
        return {"status": "already_drafted", "email": existing}

    if not body:
        body = _compose_email(email_type, candidate, app, subject or _default_subject(email_type))
    if not subject:
        subject = _default_subject(email_type)

    email = {
        "application_id": application_id,
        "type": email_type,
        "to": candidate.get("email", ""),
        "subject": subject,
        "body": body,
        "email_status": "ready_to_send",
    }
    email_id = store.create_email(email)
    email["id"] = email_id
    _log("draft_candidate_email", _app_ctx(application_id) | {"email_id": email_id, "email_type": email_type}, level="major")
    return {"status": "drafted", "email": email}


def _default_subject(email_type: str) -> str:
    return {
        "interview_invite": "Interview Invitation — AgentHR",
        "rejection": "Update on your application — AgentHR",
        "review_notice": "Your application is under review — AgentHR",
    }.get(email_type, "AgentHR Talent Acquisition")


def _compose_email(email_type: str, candidate: dict[str, Any], app: dict[str, Any], subject: str) -> str:
    """Compose email copy via Bedrock (or deterministic mock)."""
    name = candidate.get("name", "Candidate")
    try:
        llm = get_llm()
        prompt = (
            f"Compose a short, professional {email_type.replace('_', ' ')} email to "
            f"{name}. Subject: {subject}. Include the candidate's name and a clear "
            "next step. Sign off as 'AgentHR Talent Acquisition Team'. Return only the email body text."
        )
        text = llm.generate(prompt).strip()
        if text:
            return text
    except Exception:
        pass
    return f"Dear {name},\n\nThank you for applying to AgentHR. We will be in touch shortly.\n\n— AgentHR Talent Acquisition Team"
