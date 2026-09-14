"""Dedicated test suite for AgentHR's Human-In-The-Loop (HITL) approval gate.

Tests both positive (recruiter approves) and negative (recruiter rejects) paths.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["STORE_BACKEND"] = "memory"
os.environ["LLM_BACKEND"] = "mock"
os.environ["AGENT_AUTONOMOUS"] = "0"
os.environ["ENABLE_APPROVAL_GATE"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.agent import run_application, resume_application  # noqa: E402
from app.services.event_service import seed  # noqa: E402
from app.services.store import get_store  # noqa: E402


def test_approval_and_resumption():
    print("Testing HITL Approval Path...")
    store = get_store()
    seed(store)
    job = store.list_jobs(open_only=True)[0]

    # Create candidate with strong match (score >= 85)
    cand_id = store.create_candidate(
        {
            "name": "Jane Developer",
            "email": "jane@example.com",
            "experience_years": 6.0,
            "skills": ["Python", "REST APIs", "FastAPI", "Docker", "AWS"],
        }
    )
    app_id = store.create_application(
        {
            "job_id": job["id"],
            "candidate_id": cand_id,
            "candidate_name": "Jane Developer",
            "candidate_email": "jane@example.com",
            "status": "new",
        }
    )

    # 1. Run pipeline
    result = run_application(app_id, store)
    assert result["outcome"] == "INTERVIEW", f"Expected INTERVIEW, got {result['outcome']}"
    assert result["status"] == "awaiting_approval", f"Expected awaiting_approval, got {result['status']}"

    # Verify no interview was booked prematurely
    assert store.get_interview_for_application(app_id) is None, "Interview booked prematurely!"
    assert store.get_email_for_application(app_id, "interview_invite") is None, "Email drafted prematurely!"

    # 2. Approve action
    res = resume_application(app_id, approved=True, decided_by="hr@agenthr.ai", store=store)
    assert res["status"] == "approved"

    # Verify interview and email now exist
    assert store.get_interview_for_application(app_id) is not None, "Interview not created after approval!"
    assert store.get_email_for_application(app_id, "interview_invite") is not None, "Email not drafted after approval!"
    assert store.get_application(app_id)["status"] == "interview"
    print("  ✓ Approval path passed!\n")


def test_rejection_at_checkpoint():
    print("Testing HITL Rejection Path...")
    store = get_store()
    seed(store)
    job = store.list_jobs(open_only=True)[0]

    cand_id = store.create_candidate(
        {
            "name": "John Candidate",
            "email": "john@example.com",
            "experience_years": 5.0,
            "skills": ["Python", "REST APIs", "FastAPI", "AWS"],
        }
    )
    app_id = store.create_application(
        {
            "job_id": job["id"],
            "candidate_id": cand_id,
            "candidate_name": "John Candidate",
            "candidate_email": "john@example.com",
            "status": "new",
        }
    )

    result = run_application(app_id, store)
    assert result["status"] == "awaiting_approval"

    # Reject the action
    res = resume_application(app_id, approved=False, decided_by="hr@agenthr.ai", store=store)
    assert res["status"] == "rejected"

    # Verify no interview was booked and status is rejected
    assert store.get_interview_for_application(app_id) is None, "Interview booked after rejection!"
    assert store.get_application(app_id)["status"] == "rejected"
    print("  ✓ Rejection path passed!\n")


if __name__ == "__main__":
    test_approval_and_resumption()
    test_rejection_at_checkpoint()
    print("ALL APPROVAL GATE TESTS PASSED!")
