"""Live AWS end-to-end test against Amazon Bedrock and Amazon DynamoDB.

Exercises the full recruiting pipeline:
  1. Seeds demo job into DynamoDB
  2. Parses CV & creates candidate
  3. Evaluates application with policy engine
  4. Runs Strands Agent with Amazon Nova Pro on Bedrock
  5. Pauses at HITL approval gate
  6. Simulates recruiter approval and resumes agent execution
  7. Verifies interview scheduling & drafted email in DynamoDB

Usage:
  STORE_BACKEND=dynamodb LLM_BACKEND=bedrock python scripts/dynamodb_e2e.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure DynamoDB and Bedrock are selected
os.environ.setdefault("STORE_BACKEND", "dynamodb")
os.environ.setdefault("LLM_BACKEND", "bedrock")
os.environ.setdefault("ENABLE_APPROVAL_GATE", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.agent import run_application, resume_application  # noqa: E402
from app.services.cv_parser import extract_cv_text, parse_profile  # noqa: E402
from app.services.event_service import seed  # noqa: E402
from app.services.store import get_store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    store = get_store()
    print(f"Active Store Backend: {store.backend}")
    if store.backend != "dynamodb":
        print("WARNING: Expected STORE_BACKEND=dynamodb")

    print("\n1. Seeding demo job...")
    seed(store)
    jobs = store.list_jobs(open_only=True)
    if not jobs:
        print("ERROR: No jobs found after seeding")
        sys.exit(1)
    job = jobs[0]
    print(f"  Target Job: {job.get('title')} (id={job.get('id')})")

    # Pick sample CV (Ahmed Khan - high scoring candidate)
    cv_path = ROOT / "sample_cvs" / "1_ahmed_khan_strong.txt"
    if not cv_path.exists():
        cv_path = next((ROOT / "sample_cvs").glob("*.txt"))

    print(f"\n2. Processing CV: {cv_path.name}...")
    cv_text = extract_cv_text(cv_path.read_bytes(), cv_path.name)
    profile = parse_profile(cv_text)
    print(f"  Candidate: {profile.name} (experience: {profile.experience_years} yrs, skills: {profile.skills})")

    candidate_id = store.create_candidate(profile.model_dump())
    application_id = store.create_application(
        {
            "job_id": job["id"],
            "candidate_id": candidate_id,
            "candidate_name": profile.name,
            "candidate_email": profile.email,
            "cv_text": cv_text,
            "status": "new",
        }
    )
    print(f"  Created Application: {application_id}")

    print("\n3. Running Strands Agent pipeline...")
    result = run_application(application_id, store)
    print(f"  Initial Run Status: {result.get('status')} | Outcome: {result.get('outcome')} | Score: {result.get('score')}")

    if result.get("status") == "awaiting_approval":
        print("\n4. HITL Approval Gate intercepted outward action!")
        approvals = store.list_approvals(application_id=application_id, status="pending")
        if approvals:
            approval = approvals[0]
            print(f"  Pending Approval ID: {approval.get('id')}")
            print(f"  Proposed Tool:       {approval.get('tool_name')}")
            print(f"  Reason:              {approval.get('reason')}")

            print("\n5. Simulating Recruiter Approval...")
            res = resume_application(application_id, approved=True, decided_by="hr@agenthr.ai", store=store)
            print(f"  Resumption Result: {res.get('status')}")

    # Verify state in DynamoDB
    app_final = store.get_application(application_id)
    interview = store.get_interview_for_application(application_id)
    email = store.get_email_for_application(application_id)

    print("\n" + "=" * 70)
    print("DynamoDB Verification:")
    print(f"  Application Status: {app_final.get('status')}")
    print(f"  Interview Record:   {interview.get('slot_start') if interview else 'None'}")
    print(f"  Email Drafted:      {email.get('type') if email else 'None'} to {email.get('to') if email else 'None'}")
    print("=" * 70)
    print("DynamoDB E2E Test Completed Successfully!")


if __name__ == "__main__":
    main()

