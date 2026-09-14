"""REST API — authenticated backend for the Streamlit frontend & Bedrock AgentCore Runtime.

Public (candidate-facing): job listing + application submission.
Admin (Bearer-token): jobs CRUD, applications, activity, calendar, reviews, approvals.
AgentCore Runtime: /invocations and /ping endpoints.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
    from fastapi.responses import JSONResponse
except ImportError:
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 500, detail: str = "") -> None:
            self.status_code = status_code
            self.detail = detail

    class APIRouter:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None: pass
        def get(self, *args: Any, **kwargs: Any) -> Any: return lambda f: f
        def post(self, *args: Any, **kwargs: Any) -> Any: return lambda f: f
        def patch(self, *args: Any, **kwargs: Any) -> Any: return lambda f: f
        def delete(self, *args: Any, **kwargs: Any) -> Any: return lambda f: f

    def Depends(f: Any = None) -> Any: return f  # type: ignore
    def File(default: Any = ...) -> Any: return default  # type: ignore
    def Form(default: Any = ...) -> Any: return default  # type: ignore
    def Header(default: Any = None) -> Any: return default  # type: ignore

from app.config import settings
from app.models.schemas import JobCreate, JobUpdate, LoginRequest, AgentCoreInvocationRequest
from app.security import create_token, verify_token
from app.services.calendar import list_available_slots
from app.services.cv_parser import extract_cv_text, parse_profile
from app.services.event_service import trigger_agent
from app.services.store import get_store

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def require_admin(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    email = verify_token(authorization.removeprefix("Bearer ").strip())
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = get_store().get_user(email)
    if not user or user.get("role") != "hr":
        raise HTTPException(status_code=403, detail="Admin access required")
    return email


@router.post("/api/login")
def login(payload: LoginRequest):
    from app.security import verify_password

    user = get_store().get_user(payload.email)
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(user["email"]), "email": user["email"], "name": user.get("name")}


# ---------------------------------------------------------------------------
# Health / agent status
# ---------------------------------------------------------------------------
@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "store_backend": get_store().backend,
        "llm_backend": settings.llm_backend,
        "model": settings.bedrock_model_id,
        "agent": "RecruitmentCoordinatorAgent (Strands Agents SDK)",
        "approval_gate": settings.enable_approval_gate,
    }


@router.get("/api/agent/status")
def agent_status():
    return {
        "status": "Active",
        "agent": "RecruitmentCoordinatorAgent",
        "framework": "Strands Agents SDK",
        "model": settings.bedrock_model_id,
        "autonomous": settings.agent_autonomous,
        "approval_gate": settings.enable_approval_gate,
    }


# ---------------------------------------------------------------------------
# Amazon Bedrock AgentCore Runtime Endpoints
# ---------------------------------------------------------------------------
@router.get("/ping")
def agentcore_ping():
    """Bedrock AgentCore Runtime required liveness health check."""
    return {"status": "Healthy"}


@router.post("/invocations")
def agentcore_invocations(payload: dict[str, Any]):
    """Bedrock AgentCore Runtime invocation endpoint."""
    from app.agent.agent import run_application, get_agent

    app_id = payload.get("application_id")
    if app_id:
        result = run_application(app_id)
        return {"statusCode": 200, "result": result}

    prompt = payload.get("prompt", "Status check")
    agent = get_agent()
    return {
        "statusCode": 200,
        "agent": agent.name,
        "model": settings.bedrock_model_id,
        "response": f"AgentHR coordinator active. Processed invocation for: {prompt[:100]}",
    }


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
@router.get("/api/jobs")
def list_jobs(open_only: bool = False):
    return get_store().list_jobs(open_only=open_only)


@router.post("/api/jobs")
def create_job(payload: JobCreate, _admin: str = Depends(require_admin)):
    job = payload.model_dump()
    job.setdefault("status", "open")
    job_id = get_store().create_job(job)
    return {"id": job_id, **job}


@router.patch("/api/jobs/{job_id}")
def update_job(job_id: str, payload: JobUpdate, _admin: str = Depends(require_admin)):
    updates = payload.model_dump(exclude_unset=True)
    job = get_store().update_job(job_id, updates)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/jobs/{job_id}/close")
def close_job(job_id: str, _admin: str = Depends(require_admin)):
    job = get_store().update_job(job_id, {"status": "closed"})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Applications (public submit + admin listing)
# ---------------------------------------------------------------------------
@router.post("/api/applications")
async def submit_application(
    job_id: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    cv: UploadFile = File(...),
):
    store = get_store()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") == "closed":
        raise HTTPException(status_code=400, detail="Job is closed")

    file_bytes = await cv.read()
    cv_text = extract_cv_text(file_bytes, cv.filename or "")

    profile = parse_profile(cv_text, name=name, email=email, phone=phone)
    candidate_doc = profile.model_dump()
    candidate_id = store.create_candidate(candidate_doc)

    application = {
        "job_id": job_id,
        "candidate_id": candidate_id,
        "candidate_name": profile.name,
        "candidate_email": profile.email,
        "cv_text": cv_text,
        "cv_filename": cv.filename,
        "status": "new",
    }
    application_id = store.create_application(application)

    # Submission triggers the autonomous agent asynchronously
    trigger_agent(application_id)

    return {
        "application_id": application_id,
        "status": "received",
        "candidate_name": profile.name,
        "job_title": job.get("title"),
    }


@router.get("/api/applications")
def list_applications(job_id: Optional[str] = None, _admin: str = Depends(require_admin)):
    store = get_store()
    apps = store.list_applications(job_id=job_id)
    return [_application_view(store, a) for a in apps]


@router.get("/api/applications/{application_id}")
def get_application(application_id: str, _admin: str = Depends(require_admin)):
    app = get_store().get_application(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _application_view(get_store(), app)


def _application_view(store, app: dict[str, Any]) -> dict[str, Any]:
    job = store.get_job(app.get("job_id", "")) or {}
    candidate = store.get_candidate(app.get("candidate_id", "")) or {}
    decision = store.get_decision_by_application(app.get("id", ""))
    return {
        **app,
        "job_title": job.get("title"),
        "candidate_name": candidate.get("name") or app.get("candidate_name"),
        "candidate_email": candidate.get("email") or app.get("candidate_email"),
        "experience_years": candidate.get("experience_years"),
        "skills": candidate.get("skills", []),
        "education": candidate.get("education", []),
        "outcome": decision.get("outcome") if decision else None,
        "mandatory_met": decision.get("mandatory_met", []) if decision else [],
        "mandatory_missing": decision.get("mandatory_missing", []) if decision else [],
        "preferred_met": decision.get("preferred_met", []) if decision else [],
        "preferred_missing": decision.get("preferred_missing", []) if decision else [],
    }


# ---------------------------------------------------------------------------
# Interviews / calendar
# ---------------------------------------------------------------------------
def _interview_view(store, interview: dict[str, Any]) -> dict[str, Any]:
    app = store.get_application(interview.get("application_id", "")) or {}
    candidate = store.get_candidate(interview.get("candidate_id", "")) or {}
    job = store.get_job(interview.get("job_id", "")) or {}
    return {
        **interview,
        "candidate_name": candidate.get("name") or app.get("candidate_name"),
        "job_title": job.get("title"),
    }


@router.get("/api/interviews")
def list_interviews(_admin: str = Depends(require_admin)):
    store = get_store()
    return [_interview_view(store, i) for i in store.list_interviews()]


@router.get("/api/calendar")
def calendar_view(_admin: str = Depends(require_admin)):
    store = get_store()
    interviews = [_interview_view(store, i) for i in store.list_interviews()]
    return {"interviews": interviews, "available_slots": list_available_slots(store)}


# ---------------------------------------------------------------------------
# Human reviews (Policy Engine Escalations)
# ---------------------------------------------------------------------------
@router.get("/api/reviews")
def list_reviews(status: Optional[str] = None, _admin: str = Depends(require_admin)):
    store = get_store()
    reviews = store.list_human_reviews(status=status)
    out = []
    for r in reviews:
        app = store.get_application(r.get("application_id", "")) or {}
        candidate = store.get_candidate(r.get("candidate_id", "")) or {}
        out.append(
            {
                **r,
                "candidate_name": candidate.get("name") or app.get("candidate_name"),
                "job_title": (store.get_job(app.get("job_id", "")) or {}).get("title"),
                "score": app.get("score"),
            }
        )
    return out


@router.post("/api/reviews/{review_id}/decision")
def decide_review(review_id: str, payload: dict[str, Any], _admin: str = Depends(require_admin)):
    store = get_store()
    reviews = store.list_human_reviews()
    review = next((r for r in reviews if r.get("id") == review_id), None)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    approved = bool(payload.get("approved"))
    new_status = "approved" if approved else "rejected"
    store.update_human_review(review_id, {"status": new_status, "decided_by": _admin})

    application_id = review.get("application_id")
    if approved:
        from app.agent.tools import schedule_interview, draft_candidate_email

        result = schedule_interview(application_id)
        if result.get("error"):
            store.update_application(application_id, {"status": "human_review"})
        else:
            draft_candidate_email(application_id, "interview_invite")
    else:
        store.update_application(application_id, {"status": "rejected"})

    return {"status": new_status, "review_id": review_id}


# ---------------------------------------------------------------------------
# HITL Approval Gate (Supervised Action Authorization)
# ---------------------------------------------------------------------------
@router.get("/api/approvals")
def list_approvals(status: Optional[str] = None, _admin: str = Depends(require_admin)):
    store = get_store()
    approvals = store.list_approvals(status=status)
    out = []
    for a in approvals:
        app = store.get_application(a.get("application_id", "")) or {}
        candidate = store.get_candidate(app.get("candidate_id", "")) or {}
        job = store.get_job(app.get("job_id", "")) or {}
        out.append(
            {
                **a,
                "candidate_name": candidate.get("name") or app.get("candidate_name"),
                "candidate_email": candidate.get("email") or app.get("candidate_email"),
                "job_title": job.get("title"),
                "score": app.get("score"),
            }
        )
    return out


@router.post("/api/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, payload: dict[str, Any], _admin: str = Depends(require_admin)):
    store = get_store()
    approval = store.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    approved = bool(payload.get("approved"))
    from app.agent.agent import resume_application

    res = resume_application(
        approval["application_id"], approved=approved, decided_by=_admin, store=store
    )
    return {
        "approval_id": approval_id,
        "status": "approved" if approved else "rejected",
        "result": res,
    }


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------
@router.get("/api/emails")
def list_emails(_admin: str = Depends(require_admin)):
    store = get_store()
    emails = store.list_emails()
    out = []
    for e in emails:
        app = store.get_application(e.get("application_id", "")) or {}
        out.append({**e, "candidate_name": app.get("candidate_name")})
    return out


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------
@router.get("/api/activity")
def list_activity(application_id: Optional[str] = None, _admin: str = Depends(require_admin)):
    store = get_store()
    logs = store.list_activity_logs(application_id=application_id)
    out = []
    for l in logs:
        app = store.get_application(l.get("application_id", "")) or {}
        out.append({**l, "candidate_name": app.get("candidate_name")})
    return out


@router.get("/api/activity/{run_id}")
def get_activity(run_id: str, _admin: str = Depends(require_admin)):
    log = get_store().get_activity_log(run_id)
    if not log:
        raise HTTPException(status_code=404, detail="Run not found")
    return log


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@router.get("/api/dashboard")
def dashboard(_admin: str = Depends(require_admin)):
    store = get_store()
    jobs = store.list_jobs()
    pending_approvals = len([a for a in store.list_approvals() if a.get("status") == "pending"])
    pending_reviews = len([r for r in store.list_human_reviews() if r.get("status") == "pending"])

    rows = []
    for job in jobs:
        apps = store.list_applications(job_id=job.get("id"))
        job_review_count = 0
        for r in store.list_human_reviews(status="pending"):
            a = store.get_application(r.get("application_id", ""))
            if a and a.get("job_id") == job.get("id"):
                job_review_count += 1
        rows.append(
            {
                "job_id": job.get("id"),
                "title": job.get("title"),
                "status": job.get("status"),
                "applications": len(apps),
                "interviews": sum(1 for a in apps if a.get("status") == "interview"),
                "awaiting_approval": sum(1 for a in apps if a.get("status") == "awaiting_approval"),
                "human_reviews": job_review_count,
                "rejected": sum(1 for a in apps if a.get("status") == "rejected"),
            }
        )
    return {
        "jobs": rows,
        "pending_approvals": pending_approvals,
        "pending_reviews": pending_reviews,
    }
