"""Offline end-to-end smoke test for AgentHR (no AWS credentials required).

Exercises the full pipeline:
  - CV parse → candidate → application → agent coordinator run
  - Understanding → Reasoning → Decision (deterministic policy engine)
  - Action (Strands tools + HITL approval gate)
  - Approval checkpoint: pauses high-scoring candidate before outward actions
  - Resumption: simulated recruiter approval executes scheduling & email drafting
  - Verification: all 3 sample CVs evaluated against memory store and mock LLM

Run:
  python scripts/smoke_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Force offline mode before importing app modules
os.environ["STORE_BACKEND"] = "memory"
os.environ["LLM_BACKEND"] = "mock"
os.environ["AGENT_AUTONOMOUS"] = "0"
os.environ["ENABLE_APPROVAL_GATE"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.agent import run_application, resume_application  # noqa: E402
from app.services.cv_parser import extract_cv_text, parse_profile  # noqa: E402
from app.services.event_service import seed  # noqa: E402
from app.services.store import get_store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    store = get_store()
    print("Seeding demo job and admin user...")
    seed(store)

    jobs = store.list_jobs(open_only=True)
    assert len(jobs) > 0, "Failed to seed job"
    job = jobs[0]
    print(f"Seeded job: {job['title']} (id={job['id']})")
    print(f"  mandatory: {job['mandatory']}")
    print(f"  preferred: {job['preferred']}\n")

    cv_files = sorted((ROOT / "sample_cvs").glob("*.txt"))
    assert len(cv_files) > 0, "No sample CVs found in sample_cvs/"

    for cv_file in cv_files:
        print("=" * 70)
        print(f"CV: {cv_file.name}")
        text = extract_cv_text(cv_file.read_bytes(), cv_file.name)
        profile = parse_profile(text)
        print(f"  profile: name={profile.name!r} years={profile.experience_years} skills={profile.skills}")

        candidate_id = store.create_candidate(profile.model_dump())
        application_id = store.create_application(
            {
                "job_id": job["id"],
                "candidate_id": candidate_id,
                "candidate_name": profile.name,
                "candidate_email": profile.email,
                "cv_text": text,
                "status": "new",
            }
        )

        result = run_application(application_id, store)
        outcome = result.get("outcome")
        score = result.get("score")
        status = result.get("status")
        print(f"  outcome: {outcome}  score: {score}  status: {status}")

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            sys.exit(1)

        # Verify HITL approval gate behavior for INTERVIEW outcome
        if outcome == "INTERVIEW":
            assert status == "awaiting_approval", f"Expected awaiting_approval for {cv_file.name}, got {status}"
            app_doc = store.get_application(application_id)
            assert app_doc.get("status") == "awaiting_approval", "Application status not updated to awaiting_approval"

            pending_approvals = store.list_approvals(application_id=application_id, status="pending")
            assert len(pending_approvals) > 0, "Expected pending approval in store"
            approval = pending_approvals[0]
            print(f"  [HITL GATE] Paused at checkpoint: approval_id={approval['id']} (tool={approval.get('tool_name')})")

            # Check that interview is not yet scheduled before approval
            pre_interview = store.get_interview_for_application(application_id)
            assert pre_interview is None, "Interview scheduled before approval was granted!"

            # Simulate recruiter approval
            print("  [HITL GATE] Simulating recruiter approval...")
            res = resume_application(application_id, approved=True, decided_by="hr@agenthr.ai", store=store)
            assert res.get("status") == "approved", "Resumption failed"

            # Check that interview and email are now created
            post_interview = store.get_interview_for_application(application_id)
            assert post_interview is not None, "Interview not created after approval"
            post_email = store.get_email_for_application(application_id, "interview_invite")
            assert post_email is not None, "Invitation email not created after approval"
            print(f"  [HITL GATE] Resumed successfully: interview scheduled at {post_interview['slot_start']}")

        log = store.get_activity_log(result["run_id"])
        print("  Activity log steps:")
        for step in log.get("steps", []):
            action = step.get("action")
            detail = {k: v for k, v in step.items() if k not in ("action", "timestamp")}
            print(f"    - {action}  {detail}")

    print("\n" + "=" * 70)
    print("Summary of Final Store State:")
    print("  Interviews scheduled:", [i.get("slot_start") for i in store.list_interviews()])
    print("  Human reviews:", [r.get("status") for r in store.list_human_reviews()])
    print("  Action approvals:", [(a.get("status"), a.get("tool_name")) for a in store.list_approvals()])
    print("  Emails drafted:", [(e.get("type"), e.get("to")) for e in store.list_emails()])
    print("=" * 70)
    print("ALL SMOKE TESTS PASSED!")


if __name__ == "__main__":
    main()
