"""RecruitmentCoordinatorAgent (Strands Agents SDK) + the per-application pipeline.

``run_application`` is the entry point called by the event service whenever a
``NEW_APPLICATION`` event fires. It:

  1. opens an activity log for the run,
  2. UNDERSTANDING  — reads candidate profile + job requirements,
  3. REASONING      — reads the hiring policy,
  4. DECISION       — applies the deterministic policy engine,
  5. ACTION         — executes the outcome via Strands Agent (Amazon Nova Pro)
                       with a supervised Human-in-the-Loop approval gate,
  6. RECORD         — finalises the activity log.

The approval gate intercepts outward actions (scheduling interviews and drafting
candidate emails), putting the application in ``awaiting_approval`` status until
a recruiter reviews and approves the action.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import settings
from app.agent import tools as agent_tools
from app.agent.prompts import SYSTEM_INSTRUCTION, TASK_TEMPLATE
from app.services.scoring import evaluate_application, record_decision
from app.services.store import Store, get_store

logger = logging.getLogger("agenthr.agent")


# ---------------------------------------------------------------------------
# Strands Hook for Human-in-the-Loop Approval
# ---------------------------------------------------------------------------
try:
    from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

    class ApprovalHook(HookProvider):
        """Intercepts outward-facing tool calls and requests human authorization."""

        def __init__(self, app_name: str = "agenthr") -> None:
            self.app_name = app_name

        def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
            registry.add_callback(BeforeToolCallEvent, self.approve)

        def approve(self, event: BeforeToolCallEvent) -> None:
            tool_name = event.tool_use.get("name", "")
            if tool_name not in ("schedule_interview", "draft_candidate_email"):
                return

            approval = event.interrupt(
                f"{self.app_name}-approval",
                reason={
                    "tool": tool_name,
                    "input": event.tool_use.get("input", {}),
                    "message": f"Approval required before executing {tool_name}",
                },
            )
            if str(approval).strip().lower() not in ("y", "yes", "true", "approved"):
                event.cancel_tool = f"Action {tool_name} was rejected by human recruiter"

except ImportError:  # pragma: no cover
    ApprovalHook = None  # type: ignore


class RecruitmentCoordinatorAgent:
    """AgentHR coordinator built on the Strands Agents SDK."""

    name = "RecruitmentCoordinatorAgent"

    def __init__(self) -> None:
        self._strands_agent = None

    def _build_strands_agent(self):
        if self._strands_agent is not None:
            return self._strands_agent

        try:
            from strands import Agent
            from strands.models import BedrockModel

            bedrock_model = BedrockModel(
                model_id=settings.bedrock_model_id,
                region_name=settings.aws_region,
                temperature=0.2,
            )

            tool_list = [
                agent_tools.get_candidate_profile,
                agent_tools.get_job_requirements,
                agent_tools.get_hiring_policy,
                agent_tools.check_interview_slots,
                agent_tools.schedule_interview,
                agent_tools.create_human_review,
                agent_tools.draft_candidate_email,
            ]

            hooks = [ApprovalHook("agenthr")] if (ApprovalHook and settings.enable_approval_gate) else []

            self._strands_agent = Agent(
                name=self.name,
                model=bedrock_model,
                system_prompt=SYSTEM_INSTRUCTION,
                tools=tool_list,
                hooks=hooks,
                callback_handler=None,
            )
            return self._strands_agent
        except Exception as exc:
            logger.warning("Could not initialize Strands Agent: %s. Using deterministic coordinator.", exc)
            return None

    def _run_strands(self, task: str, application_id: str, store: Store, run_id: str) -> dict[str, Any]:
        agent = self._build_strands_agent()
        if agent is None:
            raise RuntimeError("Strands Agent unavailable")

        result = agent(task)

        # Check for Strands Interrupt
        if getattr(result, "stop_reason", None) == "interrupt":
            interrupts = getattr(result, "interrupts", [])
            interrupt_data = interrupts[0] if interrupts else None
            reason = getattr(interrupt_data, "reason", {}) if interrupt_data else {}
            interrupt_id = getattr(interrupt_data, "id", "") if interrupt_data else ""

            approval_record = {
                "application_id": application_id,
                "tool_name": reason.get("tool", "schedule_interview"),
                "tool_input": reason.get("input", {}),
                "status": "pending",
                "reason": reason.get("message", "Recruiter authorization required"),
                "interrupt_id": interrupt_id,
            }
            approval_id = store.create_approval(approval_record)
            store.update_application(application_id, {"status": "awaiting_approval"})
            store.append_activity_step(
                run_id,
                {
                    "action": "awaiting_approval",
                    "level": "major",
                    "approval_id": approval_id,
                    "detail": f"Interrupted execution for tool '{approval_record['tool_name']}' pending recruiter approval.",
                },
            )
            return {
                "status": "awaiting_approval",
                "approval_id": approval_id,
                "summary": "Agent paused at approval gate",
            }

        summary = getattr(result, "message", "") or str(result)
        return {"status": "completed", "summary": summary}

    # -- orchestration -------------------------------------------------------
    def run(self, application_id: str, store: Optional[Store] = None) -> dict[str, Any]:
        store = store or get_store()
        app = store.get_application(application_id)
        if not app:
            raise ValueError(f"application {application_id} not found")

        run_id = store.create_activity_log({"application_id": application_id})
        agent_tools.set_run_context(application_id, run_id)
        store.update_application(application_id, {"status": "evaluating"})

        def _phase(phase: str, detail: str) -> None:
            store.append_activity_step(
                run_id,
                {"action": "phase", "phase": phase, "level": "major", "detail": detail},
            )

        try:
            # UNDERSTANDING
            _phase("UNDERSTANDING", "Read candidate profile and job requirements")
            agent_tools.get_candidate_profile(application_id)
            agent_tools.get_job_requirements(app.get("job_id", ""))

            # REASONING
            _phase("REASONING", "Read the hiring policy")
            agent_tools.get_hiring_policy()

            # DECISION (Deterministic policy engine)
            _phase("DECISION", "Apply the policy scoring engine")
            evaluation = evaluate_application(application_id, store)
            record_decision(store, evaluation)
            store.append_activity_step(
                run_id,
                {"action": "decision", "level": "major", "outcome": evaluation.outcome, "score": evaluation.score},
            )

            # ACTION — Strands Agent (Amazon Nova Pro) or deterministic execution
            _phase("ACTION", f"Execute outcome {evaluation.outcome}")
            action_result = self._execute(application_id, evaluation, app, store, run_id)

            if action_result.get("status") == "awaiting_approval":
                return {
                    "run_id": run_id,
                    "application_id": application_id,
                    "outcome": evaluation.outcome,
                    "score": evaluation.score,
                    "status": "awaiting_approval",
                    "approval_id": action_result.get("approval_id"),
                    "summary": action_result.get("summary", "Awaiting recruiter approval"),
                }

            # RECORD
            _phase("RECORD", "Finalise records and finish the run")
            store.finish_activity_log(run_id, "completed")
            return {
                "run_id": run_id,
                "application_id": application_id,
                "outcome": evaluation.outcome,
                "score": evaluation.score,
                "status": "completed",
                "summary": action_result.get("summary", ""),
            }

        except Exception as exc:  # Record failure, never crash
            logger.exception("Pipeline failed for application %s: %s", application_id, exc)
            store.finish_activity_log(run_id, "failed")
            store.update_application(application_id, {"status": "evaluating_failed"})
            return {
                "run_id": run_id,
                "application_id": application_id,
                "error": str(exc),
            }

    def _execute(
        self, application_id: str, evaluation, app: dict[str, Any], store: Store, run_id: str
    ) -> dict[str, Any]:
        if settings.agent_autonomous and not settings.is_mock_llm:
            try:
                task = TASK_TEMPLATE.format(
                    application_id=application_id,
                    job_title=app.get("job_title", app.get("job_id", "")),
                    candidate_name=app.get("candidate_name", "candidate"),
                    score=evaluation.score,
                    outcome=evaluation.outcome,
                    rationale=evaluation.rationale,
                )
                res = self._run_strands(task, application_id, store, run_id)
                if res:
                    return res
            except Exception as exc:
                logger.warning("Strands execution fell back to deterministic executor: %s", exc)

        return self._execute_deterministic(application_id, evaluation.outcome, store, run_id)

    def _execute_deterministic(
        self, application_id: str, outcome: str, store: Store, run_id: str
    ) -> dict[str, Any]:
        """Deterministic executor with supervised HITL approval checkpoint."""
        if outcome == "INTERVIEW":
            # Check if approval gate is active
            if settings.enable_approval_gate:
                existing_approval = store.get_approval_for_application(application_id)
                if not existing_approval:
                    # Pause before schedule_interview and draft_candidate_email
                    slots = agent_tools.check_interview_slots()
                    slot = slots.get("available_slots", [{}])[0] if slots.get("available_slots") else {}
                    approval_id = store.create_approval(
                        {
                            "application_id": application_id,
                            "tool_name": "schedule_interview",
                            "tool_input": {"slot_start": slot.get("slot_start")},
                            "status": "pending",
                            "reason": "Recruiter approval required before scheduling interview and sending candidate invite",
                            "proposed_slot": slot.get("label", ""),
                        }
                    )
                    store.update_application(application_id, {"status": "awaiting_approval"})
                    store.append_activity_step(
                        run_id,
                        {
                            "action": "awaiting_approval",
                            "level": "major",
                            "approval_id": approval_id,
                            "detail": "Paused execution before scheduling interview. Awaiting human recruiter approval.",
                        },
                    )
                    return {
                        "status": "awaiting_approval",
                        "approval_id": approval_id,
                        "summary": "Application paused at approval gate",
                    }

            # If approval gate is disabled or already approved
            slots = agent_tools.check_interview_slots()
            if not slots.get("available_slots"):
                rev = agent_tools.create_human_review(
                    application_id, "no available interview slot", "review manually and reschedule"
                )
                return {"status": "completed", "summary": rev["status"]}
            agent_tools.schedule_interview(application_id)
            agent_tools.draft_candidate_email(application_id, "interview_invite")
            return {"status": "completed", "summary": "interview scheduled and invitation drafted"}

        if outcome == "HUMAN_REVIEW":
            agent_tools.create_human_review(
                application_id,
                "Policy engine requires human review",
                evaluation_outcome_recommendation("HUMAN_REVIEW"),
            )
            return {"status": "completed", "summary": "escalated to human review"}

        if outcome == "REJECT":
            agent_tools.draft_candidate_email(application_id, "rejection")
            return {"status": "completed", "summary": "rejection email drafted"}

        return {"status": "completed", "summary": f"unknown outcome: {outcome}"}


def evaluation_outcome_recommendation(outcome: str) -> str:
    return {
        "HUMAN_REVIEW": "Review eligibility manually before deciding",
        "INTERVIEW": "Proceed to interview",
        "REJECT": "Reject application",
    }.get(outcome, "Review manually")


# Module-level singleton
_agent: Optional[RecruitmentCoordinatorAgent] = None


def get_agent() -> RecruitmentCoordinatorAgent:
    global _agent
    if _agent is None:
        _agent = RecruitmentCoordinatorAgent()
    return _agent


def run_application(application_id: str, store: Optional[Store] = None) -> dict[str, Any]:
    """Public entry point: run the full pipeline for one application."""
    return get_agent().run(application_id, store)


def resume_application(
    application_id: str, approved: bool, decided_by: str = "hr", store: Optional[Store] = None
) -> dict[str, Any]:
    """Resume execution of an application paused at the HITL approval checkpoint."""
    store = store or get_store()
    approval = store.get_approval_for_application(application_id)
    if not approval:
        raise ValueError(f"No pending approval for application {application_id}")

    new_status = "approved" if approved else "rejected"
    store.update_approval(
        approval["id"],
        {"status": new_status, "decided_by": decided_by},
    )

    if approved:
        # Recruiter approved -> proceed with interview scheduling and invitation email
        slots = agent_tools.check_interview_slots()
        if not slots.get("available_slots"):
            agent_tools.create_human_review(
                application_id, "no available interview slot", "review manually and reschedule"
            )
            return {"status": "escalated_to_human_review", "reason": "no available slot"}

        sched = agent_tools.schedule_interview(application_id)
        email = agent_tools.draft_candidate_email(application_id, "interview_invite")
        store.update_application(application_id, {"status": "interview"})

        # Record resumption step in activity log
        logs = store.list_activity_logs(application_id)
        if logs:
            run_id = logs[0]["id"]
            store.append_activity_step(
                run_id,
                {
                    "action": "approval_resumed",
                    "level": "major",
                    "status": "approved",
                    "decided_by": decided_by,
                    "detail": "Recruiter approved action. Interview scheduled and email invitation prepared.",
                },
            )
            store.finish_activity_log(run_id, "completed")

        return {"status": "approved", "interview": sched, "email": email}

    # Recruiter rejected the action
    store.update_application(application_id, {"status": "rejected"})
    logs = store.list_activity_logs(application_id)
    if logs:
        run_id = logs[0]["id"]
        store.append_activity_step(
            run_id,
            {
                "action": "approval_resumed",
                "level": "major",
                "status": "rejected",
                "decided_by": decided_by,
                "detail": "Recruiter rejected proposed action.",
            },
        )
        store.finish_activity_log(run_id, "completed")

    return {"status": "rejected"}
