"""In-process data store (offline demo / tests / quickstart).

Backs every collection with an in-memory dict keyed by document id. Thread-safe
so it can be shared by FastAPI request handlers and background agent runs.
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Optional

from app.services.store import Store, now_iso


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class MemoryStore(Store):
    backend = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._collections: dict[str, dict[str, dict[str, Any]]] = {
            "jobs": {},
            "candidates": {},
            "applications": {},
            "decisions": {},
            "interviews": {},
            "human_reviews": {},
            "approvals": {},
            "emails": {},
            "activity_log": {},
            "users": {},
        }

    # -- helpers --------------------------------------------------------
    def _insert(self, coll: str, doc: dict[str, Any], doc_id: Optional[str] = None) -> str:
        with self._lock:
            doc_id = doc_id or _new_id()
            record = dict(doc)
            record.setdefault("id", doc_id)
            record.setdefault("created_at", now_iso())
            self._collections[coll][doc_id] = record
            return doc_id

    def _get(self, coll: str, doc_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            doc = self._collections[coll].get(doc_id)
            return dict(doc) if doc else None

    def _list(self, coll: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(d) for d in self._collections[coll].values()]

    def _update(self, coll: str, doc_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._lock:
            doc = self._collections[coll].get(doc_id)
            if not doc:
                return None
            doc.update(updates)
            doc["updated_at"] = now_iso()
            return dict(doc)

    def _find_one(self, coll: str, key: str, value: Any) -> Optional[dict[str, Any]]:
        with self._lock:
            for doc in self._collections[coll].values():
                if doc.get(key) == value:
                    return dict(doc)
        return None

    # -- jobs ------------------------------------------------------------
    def create_job(self, job: dict[str, Any]) -> str:
        return self._insert("jobs", job)

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._get("jobs", job_id)

    def list_jobs(self, open_only: bool = False) -> list[dict[str, Any]]:
        jobs = self._list("jobs")
        if open_only:
            jobs = [j for j in jobs if j.get("status") != "closed"]
        return sorted(jobs, key=lambda j: j.get("created_at", ""))

    def update_job(self, job_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("jobs", job_id, updates)

    # -- candidates --------------------------------------------------------
    def create_candidate(self, candidate: dict[str, Any]) -> str:
        return self._insert("candidates", candidate)

    def get_candidate(self, candidate_id: str) -> Optional[dict[str, Any]]:
        return self._get("candidates", candidate_id)

    # -- applications -------------------------------------------------------
    def create_application(self, app: dict[str, Any]) -> str:
        return self._insert("applications", app)

    def get_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._get("applications", application_id)

    def list_applications(self, job_id: Optional[str] = None) -> list[dict[str, Any]]:
        apps = self._list("applications")
        if job_id:
            apps = [a for a in apps if a.get("job_id") == job_id]
        return sorted(apps, key=lambda a: a.get("created_at", ""), reverse=True)

    def update_application(self, application_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("applications", application_id, updates)

    # -- decisions -----------------------------------------------------------
    def create_decision(self, decision: dict[str, Any]) -> str:
        return self._insert("decisions", decision)

    def get_decision_by_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("decisions", "application_id", application_id)

    # -- interviews ------------------------------------------------------------
    def create_interview(self, interview: dict[str, Any]) -> str:
        return self._insert("interviews", interview)

    def list_interviews(self) -> list[dict[str, Any]]:
        return sorted(self._list("interviews"), key=lambda i: i.get("slot_start", ""))

    def get_interview_for_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("interviews", "application_id", application_id)

    # -- human reviews (Policy Engine Escalations) ------------------------------
    def create_human_review(self, review: dict[str, Any]) -> str:
        return self._insert("human_reviews", review)

    def list_human_reviews(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        reviews = self._list("human_reviews")
        if status:
            reviews = [r for r in reviews if r.get("status") == status]
        return sorted(reviews, key=lambda r: r.get("created_at", ""), reverse=True)

    def update_human_review(self, review_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("human_reviews", review_id, updates)

    def get_human_review_for_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("human_reviews", "application_id", application_id)

    # -- approvals (HITL Approval Gate Checkpoints) -----------------------------
    def create_approval(self, approval: dict[str, Any]) -> str:
        return self._insert("approvals", approval)

    def get_approval(self, approval_id: str) -> Optional[dict[str, Any]]:
        return self._get("approvals", approval_id)

    def list_approvals(self, application_id: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
        approvals = self._list("approvals")
        if application_id:
            approvals = [a for a in approvals if a.get("application_id") == application_id]
        if status:
            approvals = [a for a in approvals if a.get("status") == status]
        return sorted(approvals, key=lambda a: a.get("created_at", ""), reverse=True)

    def update_approval(self, approval_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("approvals", approval_id, updates)

    def get_approval_for_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("approvals", "application_id", application_id)

    # -- emails -------------------------------------------------------------------
    def create_email(self, email: dict[str, Any]) -> str:
        return self._insert("emails", email)

    def list_emails(self) -> list[dict[str, Any]]:
        return sorted(self._list("emails"), key=lambda e: e.get("created_at", ""))

    def get_email_for_application(self, application_id: str, email_type: Optional[str] = None) -> Optional[dict[str, Any]]:
        for doc in self._list("emails"):
            if doc.get("application_id") != application_id:
                continue
            if email_type and doc.get("type") != email_type:
                continue
            return doc
        return None

    # -- activity log --------------------------------------------------------------
    def create_activity_log(self, entry: dict[str, Any]) -> str:
        entry.setdefault("steps", [])
        entry.setdefault("status", "running")
        entry.setdefault("started_at", now_iso())
        return self._insert("activity_log", entry)

    def append_activity_step(self, run_id: str, step: dict[str, Any]) -> None:
        with self._lock:
            doc = self._collections["activity_log"].get(run_id)
            if doc:
                step.setdefault("timestamp", now_iso())
                doc.setdefault("steps", []).append(step)

    def finish_activity_log(self, run_id: str, status: str) -> None:
        with self._lock:
            doc = self._collections["activity_log"].get(run_id)
            if doc:
                doc["status"] = status
                doc["finished_at"] = now_iso()

    def get_activity_log(self, run_id: str) -> Optional[dict[str, Any]]:
        return self._get("activity_log", run_id)

    def list_activity_logs(self, application_id: Optional[str] = None) -> list[dict[str, Any]]:
        logs = self._list("activity_log")
        if application_id:
            logs = [l for l in logs if l.get("application_id") == application_id]
        return sorted(logs, key=lambda l: l.get("started_at", ""), reverse=True)

    # -- users ----------------------------------------------------------------------
    def get_user(self, email: str) -> Optional[dict[str, Any]]:
        for doc in self._list("users"):
            if doc.get("email", "").lower() == email.lower():
                return doc
        return None

    def create_user(self, user: dict[str, Any]) -> str:
        return self._insert("users", user)
