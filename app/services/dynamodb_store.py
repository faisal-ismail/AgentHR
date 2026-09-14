"""AWS DynamoDB store implementation for AgentHR.

Mirrors each collection into a dedicated DynamoDB table with partition key 'id':
  - {prefix}jobs
  - {prefix}candidates
  - {prefix}applications
  - {prefix}decisions
  - {prefix}interviews
  - {prefix}human_reviews
  - {prefix}approvals
  - {prefix}emails
  - {prefix}activity_log
  - {prefix}users

Automatically handles conversions between Python float and DynamoDB Decimal types.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key

from app.config import settings
from app.services.store import Store, now_iso


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _to_dynamo(obj: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB serialization."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _from_dynamo(obj: Any) -> Any:
    """Recursively convert Decimals back to float or int."""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_dynamo(v) for v in obj]
    return obj


class DynamoDBStore(Store):
    backend = "dynamodb"

    def __init__(self) -> None:
        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint_url:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
        self._dynamodb = boto3.resource("dynamodb", **kwargs)
        self._prefix = settings.dynamodb_table_prefix

    def _table(self, name: str):
        return self._dynamodb.Table(f"{self._prefix}{name}")

    # -- Generic helpers ----------------------------------------------------
    def _insert(self, coll: str, doc: dict[str, Any], doc_id: Optional[str] = None) -> str:
        table = self._table(coll)
        doc_id = doc_id or _new_id()
        record = dict(doc)
        record.setdefault("id", doc_id)
        record.setdefault("created_at", now_iso())
        table.put_item(Item=_to_dynamo(record))
        return doc_id

    def _get(self, coll: str, doc_id: str) -> Optional[dict[str, Any]]:
        table = self._table(coll)
        resp = table.get_item(Key={"id": doc_id})
        item = resp.get("Item")
        return _from_dynamo(item) if item else None

    def _list(self, coll: str, filter_exp=None) -> list[dict[str, Any]]:
        table = self._table(coll)
        scan_kwargs: dict[str, Any] = {}
        if filter_exp is not None:
            scan_kwargs["FilterExpression"] = filter_exp

        items: list[dict[str, Any]] = []
        done = False
        start_key = None
        while not done:
            if start_key:
                scan_kwargs["ExclusiveStartKey"] = start_key
            resp = table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                done = True
        return [_from_dynamo(i) for i in items]

    def _update(self, coll: str, doc_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        doc = self._get(coll, doc_id)
        if not doc:
            return None
        doc.update(updates)
        doc["updated_at"] = now_iso()
        self._table(coll).put_item(Item=_to_dynamo(doc))
        return doc

    def _find_one(self, coll: str, key: str, value: Any) -> Optional[dict[str, Any]]:
        items = self._list(coll, filter_exp=Attr(key).eq(value))
        return items[0] if items else None

    # -- jobs ---------------------------------------------------------------
    def create_job(self, job: dict[str, Any]) -> str:
        return self._insert("jobs", job)

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._get("jobs", job_id)

    def list_jobs(self, open_only: bool = False) -> list[dict[str, Any]]:
        f = Attr("status").ne("closed") if open_only else None
        jobs = self._list("jobs", filter_exp=f)
        return sorted(jobs, key=lambda j: j.get("created_at", ""))

    def update_job(self, job_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("jobs", job_id, updates)

    # -- candidates ---------------------------------------------------------
    def create_candidate(self, candidate: dict[str, Any]) -> str:
        return self._insert("candidates", candidate)

    def get_candidate(self, candidate_id: str) -> Optional[dict[str, Any]]:
        return self._get("candidates", candidate_id)

    # -- applications --------------------------------------------------------
    def create_application(self, app: dict[str, Any]) -> str:
        return self._insert("applications", app)

    def get_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._get("applications", application_id)

    def list_applications(self, job_id: Optional[str] = None) -> list[dict[str, Any]]:
        f = Attr("job_id").eq(job_id) if job_id else None
        apps = self._list("applications", filter_exp=f)
        return sorted(apps, key=lambda a: a.get("created_at", ""), reverse=True)

    def update_application(self, application_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("applications", application_id, updates)

    # -- decisions -----------------------------------------------------------
    def create_decision(self, decision: dict[str, Any]) -> str:
        return self._insert("decisions", decision)

    def get_decision_by_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("decisions", "application_id", application_id)

    # -- interviews -----------------------------------------------------------
    def create_interview(self, interview: dict[str, Any]) -> str:
        return self._insert("interviews", interview)

    def list_interviews(self) -> list[dict[str, Any]]:
        interviews = self._list("interviews")
        return sorted(interviews, key=lambda i: i.get("slot_start", ""))

    def get_interview_for_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("interviews", "application_id", application_id)

    # -- human reviews (Policy Engine Escalations) ----------------------------
    def create_human_review(self, review: dict[str, Any]) -> str:
        return self._insert("human_reviews", review)

    def list_human_reviews(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        f = Attr("status").eq(status) if status else None
        reviews = self._list("human_reviews", filter_exp=f)
        return sorted(reviews, key=lambda r: r.get("created_at", ""), reverse=True)

    def update_human_review(self, review_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("human_reviews", review_id, updates)

    def get_human_review_for_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("human_reviews", "application_id", application_id)

    # -- approvals (HITL Approval Gate Checkpoints) ---------------------------
    def create_approval(self, approval: dict[str, Any]) -> str:
        return self._insert("approvals", approval)

    def get_approval(self, approval_id: str) -> Optional[dict[str, Any]]:
        return self._get("approvals", approval_id)

    def list_approvals(self, application_id: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
        conditions = []
        if application_id:
            conditions.append(Attr("application_id").eq(application_id))
        if status:
            conditions.append(Attr("status").eq(status))

        f = None
        if len(conditions) == 1:
            f = conditions[0]
        elif len(conditions) > 1:
            f = conditions[0] & conditions[1]

        approvals = self._list("approvals", filter_exp=f)
        return sorted(approvals, key=lambda a: a.get("created_at", ""), reverse=True)

    def update_approval(self, approval_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._update("approvals", approval_id, updates)

    def get_approval_for_application(self, application_id: str) -> Optional[dict[str, Any]]:
        return self._find_one("approvals", "application_id", application_id)

    # -- emails ----------------------------------------------------------------
    def create_email(self, email: dict[str, Any]) -> str:
        return self._insert("emails", email)

    def list_emails(self) -> list[dict[str, Any]]:
        emails = self._list("emails")
        return sorted(emails, key=lambda e: e.get("created_at", ""))

    def get_email_for_application(self, application_id: str, email_type: Optional[str] = None) -> Optional[dict[str, Any]]:
        f = Attr("application_id").eq(application_id)
        if email_type:
            f = f & Attr("type").eq(email_type)
        items = self._list("emails", filter_exp=f)
        return items[0] if items else None

    # -- activity log -----------------------------------------------------------
    def create_activity_log(self, entry: dict[str, Any]) -> str:
        entry.setdefault("steps", [])
        entry.setdefault("status", "running")
        entry.setdefault("started_at", now_iso())
        return self._insert("activity_log", entry)

    def append_activity_step(self, run_id: str, step: dict[str, Any]) -> None:
        doc = self.get_activity_log(run_id)
        if doc:
            step.setdefault("timestamp", now_iso())
            steps = doc.get("steps", [])
            steps.append(step)
            self._update("activity_log", run_id, {"steps": steps})

    def finish_activity_log(self, run_id: str, status: str) -> None:
        self._update("activity_log", run_id, {"status": status, "finished_at": now_iso()})

    def get_activity_log(self, run_id: str) -> Optional[dict[str, Any]]:
        return self._get("activity_log", run_id)

    def list_activity_logs(self, application_id: Optional[str] = None) -> list[dict[str, Any]]:
        f = Attr("application_id").eq(application_id) if application_id else None
        logs = self._list("activity_log", filter_exp=f)
        return sorted(logs, key=lambda l: l.get("started_at", ""), reverse=True)

    # -- users ------------------------------------------------------------------
    def get_user(self, email: str) -> Optional[dict[str, Any]]:
        users = self._list("users")
        for u in users:
            if u.get("email", "").lower() == email.lower():
                return u
        return None

    def create_user(self, user: dict[str, Any]) -> str:
        return self._insert("users", user)

