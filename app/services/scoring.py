"""Deterministic policy engine.

This module is the auditable core of the decision: it applies ``hiring_policy.md``
to a candidate + job and produces a score, an outcome (INTERVIEW / HUMAN_REVIEW /
REJECT), and the mandatory/preferred requirement breakdown. The ADK agent reads
this result and then orchestrates the corresponding *action* with its tools —
the eligibility mapping itself is never left to model improvisation.

Scoring (from the policy):
    mandatory_score = 70 * (mandatory_met / total_mandatory)
    preferred_score = 30 * (preferred_met / total_preferred)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.cv_parser import SKILL_ALIASES
from app.services.store import Store

MANDATORY_WEIGHT = 70.0
PREFERRED_WEIGHT = 30.0

_YEARS_IN_REQ = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_STOPWORDS = {"experience", "with", "in", "of", "knowledge", "and", "the", "a", "an", "plus", "or"}


@dataclass
class Evaluation:
    application_id: str
    job_id: str
    candidate_id: str
    score: float
    outcome: str  # INTERVIEW | HUMAN_REVIEW | REJECT
    mandatory_met: list[str] = field(default_factory=list)
    mandatory_missing: list[str] = field(default_factory=list)  # includes "not met"
    preferred_met: list[str] = field(default_factory=list)
    preferred_missing: list[str] = field(default_factory=list)
    has_unknown_mandatory: bool = False
    rationale: str = ""


# ---------------------------------------------------------------------------
# Requirement matching
# ---------------------------------------------------------------------------
def _canonical_label(req_lower: str) -> Optional[str]:
    """Map a requirement string to a known skill label, if any."""
    for label, aliases in SKILL_ALIASES.items():
        if any(a in req_lower for a in aliases):
            return label
    return None


def _years_required(req: str) -> Optional[float]:
    m = _YEARS_IN_REQ.search(req)
    return float(m.group(1)) if m else None


def _check_requirement(
    req: str,
    candidate: dict[str, Any],
    cv_text: str,
) -> str:
    """Return 'met' | 'missing' | 'not_met' for a single requirement."""
    req_lower = req.lower()
    text_lower = (cv_text or "").lower()
    skills = [s.lower() for s in (candidate.get("skills") or [])]
    skills_known = bool(skills)
    experience_years = candidate.get("experience_years")

    # 1. Experience-years requirement
    needed_years = _years_required(req)
    if needed_years is not None:
        if experience_years is None:
            return "missing"
        return "met" if experience_years >= needed_years else "not_met"

    # 2. Known-skill requirement
    label = _canonical_label(req_lower)
    if label:
        if label.lower() in skills:
            return "met"
        aliases = SKILL_ALIASES.get(label, [])
        if any(a in text_lower for a in aliases):
            return "met"
        # Absent -> not met only if the candidate enumerated a skill set;
        # otherwise the CV is too thin to judge -> missing.
        return "not_met" if skills_known else "missing"

    # 3. Generic keyword requirement
    tokens = [t for t in re.split(r"[^a-z0-9+#.]+", req_lower) if len(t) >= 2 and t not in _STOPWORDS]
    if not tokens:
        return "met"
    if all(any(t in s for s in skills) or t in text_lower for t in tokens):
        return "met"
    return "not_met" if skills_known else "missing"


def evaluate(
    candidate: dict[str, Any],
    job: dict[str, Any],
    cv_text: str = "",
    application_id: str = "",
) -> Evaluation:
    """Score a candidate against a job and return the policy outcome."""
    mandatory = job.get("mandatory") or []
    preferred = job.get("preferred") or []

    mandatory_met: list[str] = []
    mandatory_missing: list[str] = []
    has_unknown = False
    for req in mandatory:
        status = _check_requirement(req, candidate, cv_text)
        if status == "met":
            mandatory_met.append(req)
        else:
            mandatory_missing.append(req)
            if status == "missing":
                has_unknown = True

    preferred_met: list[str] = []
    preferred_missing: list[str] = []
    for req in preferred:
        if _check_requirement(req, candidate, cv_text) == "met":
            preferred_met.append(req)
        else:
            preferred_missing.append(req)

    m_score = MANDATORY_WEIGHT * (len(mandatory_met) / len(mandatory)) if mandatory else MANDATORY_WEIGHT
    p_score = PREFERRED_WEIGHT * (len(preferred_met) / len(preferred)) if preferred else PREFERRED_WEIGHT
    score = round(m_score + p_score, 1)

    outcome = _decide(score, mandatory_met, mandatory_missing, has_unknown)
    rationale = _build_rationale(score, outcome, mandatory_met, mandatory_missing, preferred_met, preferred_missing)

    return Evaluation(
        application_id=application_id,
        job_id=job.get("id", ""),
        candidate_id=candidate.get("id", ""),
        score=score,
        outcome=outcome,
        mandatory_met=mandatory_met,
        mandatory_missing=mandatory_missing,
        preferred_met=preferred_met,
        preferred_missing=preferred_missing,
        has_unknown_mandatory=has_unknown,
        rationale=rationale,
    )


def _decide(score: float, mandatory_met: list[str], mandatory_missing: list[str], has_unknown: bool) -> str:
    # Never auto-interview or auto-reject when mandatory information is MISSING.
    if has_unknown:
        return "HUMAN_REVIEW"
    # All mandatory met (score >= 85 implies this given the 70% mandatory weight)
    if not mandatory_missing and score >= 85:
        return "INTERVIEW"
    if score >= 60:
        return "HUMAN_REVIEW"
    return "REJECT"


def _build_rationale(
    score: float,
    outcome: str,
    mandatory_met: list[str],
    mandatory_missing: list[str],
    preferred_met: list[str],
    preferred_missing: list[str],
) -> str:
    parts = [f"Score {score}/100."]
    if mandatory_met:
        parts.append("Mandatory met: " + ", ".join(mandatory_met) + ".")
    if mandatory_missing:
        parts.append("Mandatory unmet/missing: " + ", ".join(mandatory_missing) + ".")
    if preferred_met:
        parts.append("Preferred met: " + ", ".join(preferred_met) + ".")
    if preferred_missing:
        parts.append("Preferred not met: " + ", ".join(preferred_missing) + ".")
    parts.append(f"Outcome: {outcome} (per hiring policy).")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Store-aware helpers
# ---------------------------------------------------------------------------
def evaluate_application(application_id: str, store: Store) -> Evaluation:
    app = store.get_application(application_id)
    if not app:
        raise ValueError(f"application not found: {application_id}")
    candidate = store.get_candidate(app.get("candidate_id", "")) or {}
    job = store.get_job(app.get("job_id", "")) or {}
    cv_text = app.get("cv_text", "")
    return evaluate(candidate, job, cv_text, application_id)


def record_decision(store: Store, ev: Evaluation) -> str:
    """Persist the evaluation as a ``decisions`` doc and update the application."""
    decision = {
        "application_id": ev.application_id,
        "job_id": ev.job_id,
        "candidate_id": ev.candidate_id,
        "outcome": ev.outcome,
        "score": ev.score,
        "mandatory_met": ev.mandatory_met,
        "mandatory_missing": ev.mandatory_missing,
        "preferred_met": ev.preferred_met,
        "preferred_missing": ev.preferred_missing,
        "rationale": ev.rationale,
    }
    decision_id = store.create_decision(decision)

    store.update_application(
        ev.application_id,
        {"score": ev.score, "rationale": ev.rationale, "status": _status_for_outcome(ev.outcome)},
    )
    return decision_id


def _status_for_outcome(outcome: str) -> str:
    return {"INTERVIEW": "interview", "HUMAN_REVIEW": "human_review", "REJECT": "rejected"}.get(outcome, "evaluating")
