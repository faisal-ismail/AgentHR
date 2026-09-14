# Strands Agents SDK Integration in AgentHR

This document details how the **Strands Agents SDK** is integrated and utilized within **AgentHR** to power the `RecruitmentCoordinatorAgent`.

---

## Architecture Overview

AgentHR uses the **Strands Agents SDK** as its primary AI agent framework to orchestrate candidate application processing. The agent runs on **Amazon Nova Pro** via **AWS Bedrock**, interacting with structured tools and enforcement hooks to automate hiring workflows while preserving safety through a **Human-in-the-Loop (HITL)** approval gate.

```
                     ┌───────────────────────────────────────────┐
                     │       RecruitmentCoordinatorAgent         │
                     │          (Strands Agents SDK)             │
                     └─────────────────────┬─────────────────────┘
                                           │
             ┌─────────────────────────────┼─────────────────────────────┐
             ▼                             ▼                             ▼
   ┌───────────────────┐         ┌───────────────────┐         ┌───────────────────┐
   │   Bedrock Model   │         │   Strands Tools   │         │   Strands Hooks   │
   │ (Amazon Nova Pro) │         │   (7 Core Tools)  │         │  (HITL Approval)  │
   └───────────────────┘         └───────────────────┘         └───────────────────┘
```

---

## 1. Agent Initialization & Model Setup

The agent is constructed in [`app/agent/agent.py`](app/agent/agent.py). It initializes a `BedrockModel` pointing to Amazon Nova Pro:

```python
from strands import Agent
from strands.models import BedrockModel
from app.agent.prompts import SYSTEM_INSTRUCTION
from app.agent import tools as agent_tools

bedrock_model = BedrockModel(
    model_id=settings.bedrock_model_id,  # e.g., amazon.nova-pro-v1:0
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

agent = Agent(
    name="RecruitmentCoordinatorAgent",
    model=bedrock_model,
    system_prompt=SYSTEM_INSTRUCTION,
    tools=tool_list,
    hooks=hooks,
)
```

---

## 2. Strands Tools Registry

Tools are registered using the Strands `@tool` decorator in [`app/agent/tools.py`](app/agent/tools.py). Each tool includes type annotations and Google-style docstrings, which Strands converts into JSON schema definitions for model function calling.

### Available Tools:

| Tool Function | Type | Description |
| :--- | :--- | :--- |
| `get_candidate_profile(application_id)` | Read | Retrieves parsed candidate details (skills, experience, education, contact). |
| `get_job_requirements(job_id)` | Read | Retrieves mandatory and preferred job criteria. |
| `get_hiring_policy()` | Read | Reads the policy-as-code from `hiring_policy.md`. |
| `check_interview_slots()` | Action | Queries calendar service for open, non-conflicting interview slots. |
| `schedule_interview(application_id, slot_start)` | Action | Books an interview slot and updates candidate application status. |
| `create_human_review(application_id, reason, recommendation)` | Action | Escalates candidate to human recruiter queue with rationale. |
| `draft_candidate_email(application_id, email_type, subject, body)` | Action | Generates invitation/rejection emails via Bedrock LLM synthesis. |

---

## 3. Human-in-the-Loop (HITL) Gate via Strands Hooks

AgentHR leverages Strands Lifecycle Hooks ([`ApprovalHook`](app/agent/agent.py#L38-L64)) to prevent outward actions from executing without human oversight.

### How the Hook Works:
1. `ApprovalHook` inherits from `strands.hooks.HookProvider`.
2. Registers a callback on `BeforeToolCallEvent`.
3. Intercepts sensitive tool calls (`schedule_interview`, `draft_candidate_email`).
4. Triggers `event.interrupt(...)`, causing the Strands agent execution to cleanly pause.

```python
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

class ApprovalHook(HookProvider):
    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.approve)

    def approve(self, event: BeforeToolCallEvent) -> None:
        tool_name = event.tool_use.get("name", "")
        if tool_name not in ("schedule_interview", "draft_candidate_email"):
            return

        # Trigger Strands Interrupt
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
```

### Resuming Interrupted Runs:
When an interrupt occurs:
* The application status changes to `awaiting_approval`.
* An approval request is recorded in the store.
* When the human recruiter clicks **Approve** in the UI, `resume_application(...)` resumes the pipeline to execute the pending tool call.

---

## 4. End-to-End Execution Pipeline

Each application run follows a 5-phase structured lifecycle:

1. **`UNDERSTANDING`**: The agent calls `get_candidate_profile` and `get_job_requirements`.
2. **`REASONING`**: The agent calls `get_hiring_policy` to ingest decision rules.
3. **`DECISION`**: Executes deterministic policy evaluation (`scoring.py`) to compute mandatory/preferred breakdown and total score.
4. **`ACTION`**: Executes tool calls based on the policy outcome:
   * **`INTERVIEW`**: Pauses at the approval gate before booking calendar slots and drafting invite emails.
   * **`HUMAN_REVIEW`**: Invokes `create_human_review`.
   * **`REJECT`**: Invokes `draft_candidate_email` with `email_type="rejection"`.
5. **`RECORD`**: Finalizes the activity log and persists decision records.

---

## 5. Fallback & Offline Mode

If AWS Bedrock or the Strands SDK is unavailable (or when `USE_MOCK_LLM=1`), the pipeline automatically routes to `_execute_deterministic(...)`. This guarantees that the system remains fully testable offline while keeping identical scoring formulas, HITL gates, and database contracts intact.
