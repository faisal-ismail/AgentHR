"""Event plumbing + startup seeding for AgentHR.

A candidate application triggers the ``NEW_APPLICATION`` event; handling it fires the
RecruitmentCoordinatorAgent asynchronously (in a background thread) so the
candidate receives an immediate confirmation while the agent coordinates screening,
scoring, and action execution.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from app.config import settings
from app.security import hash_password
from app.services.store import Store, get_store


def trigger_agent(application_id: str) -> dict[str, Any]:
    """Kick off the autonomous run for a new application (non-blocking)."""
    from app.agent.agent import run_application  # local import to avoid cycles

    def _run() -> None:
        try:
            run_application(application_id)
        except Exception:  # noqa: BLE001 — the run itself records failures
            pass

    threading.Thread(target=_run, daemon=True, name=f"agenthr-{application_id}").start()
    return {"status": "agent_triggered", "application_id": application_id}


def seed(store: Optional[Store] = None) -> None:
    """Seed the admin user and demo job on first boot (idempotent)."""
    store = store or get_store()

    if not store.get_user(settings.admin_email):
        store.create_user(
            {
                "name": "HR Admin",
                "email": settings.admin_email,
                "role": "hr",
                "password_hash": hash_password(settings.admin_password),
            }
        )

    if not store.list_jobs():
        store.create_job(
            {
                "title": "Backend Engineer",
                "department": "Engineering",
                "description": (
                    "Build and maintain REST APIs and cloud services with Python. Design "
                    "data models, containerize microservices, and deploy reliable cloud backend systems."
                ),
                "mandatory": ["Python", "REST APIs", "3+ years experience"],
                "preferred": ["FastAPI", "Docker", "AWS"],
                "hiring_policy_ref": "data/policies/hiring_policy.md",
                "status": "open",
                "posted_by": "hr",
            }
        )
