# RecruitFlow AI — Autonomous Application-to-Action Agent

**Hackathon:** All Things Agentic Hackathon
**Track:** 1 — Taskmaster
**Submission deadline:** 31 August 2026
**Status:** Finalized Proposal / Specification v3.1

---

## 1. Positioning

> **"From application received to recruitment action taken — autonomously."**

Most recruiting AI stops at a match score (`CV → LLM → 87% match`). That is weak for this hackathon. RecruitFlow AI does not just *score* a candidate — it **understands** the job and hiring policy, **evaluates** eligibility, **decides** the next action, **executes** that action, and **records** the result, all without a human in the loop.

The demo does not star a score. It stars the **action chain**:

```
EVENT         New application received
              ↓
UNDERSTANDING Candidate: Ahmed Khan   ·   Job: Backend Engineer
              ↓
REASONING     Mandatory: ✓ Python ✓ REST APIs ✓ 3+ yrs
              Preferred: ✓ FastAPI ✓ Docker ✗ Google Cloud
              ↓
DECISION      Interview recommended
              ↓
ACTION        ✓ Slot selected: Tue 11:30
              ✓ Interview created & added to calendar
              ✓ Candidate email prepared
              ✓ Application updated
```

The system has **one web app with two tabs**: a public **Candidate** tab where applicants apply to a job, and an **Admin** tab (login required) where the recruiter posts jobs, watches the agent work live, reviews escalations, and sees scheduled interviews on a calendar.

---

## 2. Problem Statement

A recruiter receives an application and must, by hand: read the CV, recall the job's requirements, recall company hiring policy, judge eligibility, decide what to do next, act on it (schedule / escalate / reject), and record everything. This is repetitive, inconsistent, and slow — and the moment a candidate applies, the clock starts on responsiveness.

**The agent removes this friction end-to-end.** The recruiter's role shrinks to reviewing a short list of *ready-to-send* outcomes on a dashboard, not processing applications.

---

## 3. Goals & Non-Goals

### Goals
- Fully autonomous flow: **application received → action taken → activity logged**.
- Rule-driven decision-making that follows an explicit, auditable **hiring policy**.
- A single, capable **ADK agent** that reasons and calls the right tools at the right time.
- **Candidate tab** — a public page where candidates browse open jobs, upload a CV, and apply.
- **Admin tab** — post/manage jobs, view the full pipeline, watch the agent run, act on escalations.
- **Interview calendar** — every scheduled interview is persisted and visible to the recruiter on a calendar view.
- Persistent state and a complete activity log for every run.
- Deployable on Google Cloud with reproducible setup.

### Non-Goals (out of scope for v1)
- **No real email sending** — emails are drafted and stored as `ready_to_send` (avoids email API debugging; still demonstrates external action).
- **Google Calendar API not required** — v1 uses a DB-backed calendar view; the API is an optional swap-in behind the same `schedule_interview()` interface (see §17).
- **No ATS/HRIS replacement**, no candidate "quality grading" beyond policy-driven eligibility.
- No social sign-in / OAuth for candidates (public apply requires no account).

---

## 4. Architecture

```
                 CANDIDATE                         RECRUITER (HR)
                     │                                   │
                     ▼                                   ▼
              ┌────────────── Streamlit App ─────────────┐
              │   Candidate tab          Admin tab       │
              │   (public, apply)      (login, manage)   │
              └──────────────────────┬───────────────────┘
                                     ▼
                                 FastAPI
                                     │
                         NEW_APPLICATION event  ·  job CRUD ·  query pipeline
                                     │
                                     ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                    Google ADK                                │
   │                                                              │
   │            RecruitmentCoordinatorAgent                       │
   │                  Gemini 3.7 Flash                            │
   │                                                              │
   │      Tool orchestration (agent decides the call)            │
   │   ┌───────────────┬───────────────┬────────────────────┐    │
   │   ▼               ▼               ▼                    │    │
   │ Candidate       Hiring          Action                │    │
   │   Tools         Tools           Tools                 │    │
   │ └───────────────┴───────────────┴────────────────────┘    │
   │                      │                                      │
   │                      ▼                                      │
   │   Firestore ── applications · jobs · interviews ·           │
   │                human_reviews · emails · activity_log        │
   │                      │                                      │
   │                      ▼                                      │
   │        Interview Calendar (DB-backed, recruiter view)       │
   └──────────────────────────────────────────────────────────────┘
               ─────────────────────────
                    Google Cloud Run
```

**Why this is genuinely agentic:** Gemini decides *which tools to call and what action to take*, rather than following a hardcoded script. ADK is purpose-built for agents that reason, plan, and use tools — a direct fit for the brief.

**Design choices (mapped to judging):**
- **One agent, seven tools** — deliberately minimal. The intelligence lives in tool selection and policy application, not a sprawling pipeline.
- **Policy as a first-class artifact** — the agent reads `hiring_policy.md` and applies it; the decision is auditable and changeable without touching code.
- **One frontend, two tabs** — a single Streamlit app with a public **Candidate** tab and an authenticated **Admin** tab, both thin clients over the same FastAPI backend.
- **DB-backed calendar** — interviews are first-class records rendered as a calendar, so "scheduled interview" is a real, queryable outcome without Calendar API debugging.
- **State + logs in Firestore** — every application, decision, and run step is a document, giving durable memory and a clean cross-session record.
- **Cloud Run** — stateless, auto-scaling container; scales to zero when idle (near-$0).

---

## 5. The Agent & Its Seven Tools

A single agent: **`RecruitmentCoordinatorAgent`** (Google ADK), backed by **Gemini 3.7 Flash**.

| # | Tool | What it returns / does |
|---|---|---|
| 1 | `get_candidate_profile()` | Structured candidate info extracted from the CV (name, experience, education, skills) |
| 2 | `get_job_requirements()` | Job's **mandatory** and **preferred** requirements |
| 3 | `get_hiring_policy()` | The decision rules the agent must follow |
| 4 | `check_interview_slots()` | Available interview slots (stored slot set; conflict-checked against existing interviews) |
| 5 | `schedule_interview()` | Creates an interview record **and adds it to the recruiter calendar** — a real action |
| 6 | `create_human_review()` | Creates a `HUMAN_REVIEW_REQUIRED` record with reason + recommendation |
| 7 | `draft_candidate_email()` | Produces the final communication, stored `ready_to_send` |

Status updates (`application.status`, activity log) happen transactionally *inside* each action tool, so every run leaves a complete audit trail.

### Hiring Policy (the decision engine)

The agent is not free to improvise. It applies `data/policies/hiring_policy.md`:

```
Score 85–100  → recommend INTERVIEW
Score 60–84   → if ALL mandatory requirements satisfied → HUMAN REVIEW
Score < 60    → REJECT
Never auto-reject when mandatory information is MISSING.
```

This turns "AI's opinion" into "company policy, applied consistently" — a key architectural-discipline signal.

### Interview scheduling & calendar

- `check_interview_slots()` reads the **interview slot store** (a seeded set of demo slots: Mon 10:00, Mon 14:00, Tue 11:30, Wed 09:00) and filters out any already-taken slot by querying existing `interviews` records.
- `schedule_interview()` writes an `interviews/{id}` document with `slot_start` / `slot_end`.
- The HR Dashboard renders these records as a **weekly calendar view**, so the recruiter sees every scheduled interview at a glance. No Calendar API, no OAuth — fully demoable, deterministic, and queryable.
- Google Calendar API is a drop-in future enhancement (§17) behind the same `schedule_interview()` interface.

---

## 6. Data Model (Firestore)

```
jobs/{jobId}
  title, department, description,
  mandatory[], preferred[], hiring_policy_ref,
  status (open|closed), posted_by, created_at

applications/{applicationId}
  candidate_id, job_id, cv_text, status (new|evaluating|interview|human_review|rejected),
  score, rationale, policy_version, created_at

candidates/{candidateId}
  name, email, phone, experience_years, education, skills[]

decisions/{decisionId}
  application_id, outcome (INTERVIEW|HUMAN_REVIEW|REJECT), score,
  mandatory_met[], mandatory_missing[], preferred_met[], preferred_missing[], rationale

interviews/{interviewId}
  application_id, candidate_id, job_id, slot_start, slot_end,
  status (scheduled), created_at          ← rendered on the recruiter calendar

human_reviews/{reviewId}
  application_id, candidate_id, reason, recommendation,
  status (pending|approved|rejected), decided_by, decided_at

emails/{emailId}
  application_id, type (interview_invite|rejection|review_notice), to, subject, body,
  email_status (ready_to_send)

activity_log/{runId}
  application_id, steps[{timestamp, action}], status (completed|failed), started_at, finished_at

users/{userId}
  name, email, role (hr|candidate), password_hash   ← Admin tab login (simple session)
```

---

## 7. Agent Workflow (per application)

1. **EVENT** — candidate applies via the portal → `NEW_APPLICATION` event triggers the agent (submission itself triggers the agent; there is **no** "Analyse CV" button).
2. **UNDERSTANDING** — agent calls `get_candidate_profile()` + `get_job_requirements()`.
3. **REASONING** — agent calls `get_hiring_policy()`, evaluates mandatory/preferred criteria, produces score + rationale.
4. **DECISION** — maps score + eligibility to `INTERVIEW` / `HUMAN_REVIEW` / `REJECT` per policy.
5. **ACTION** — executes the outcome:
   - **INTERVIEW** → `check_interview_slots()` → `schedule_interview()` (writes calendar record) → `draft_candidate_email()` (invite).
   - **HUMAN_REVIEW** → `create_human_review()` (with reason + recommendation).
   - **REJECT** → `draft_candidate_email()` (rejection).
6. **RECORD** — every step written to `activity_log` with timestamps; application status updated.

---

## 8. Web Application (one frontend, two tabs)

**Stack:** FastAPI (backend) → one Streamlit app with two tabs. Both tabs are thin clients over the same API.

### 8.1 Candidate tab (public — no login)

| Page | Purpose |
|---|---|
| **Open Jobs** | List active jobs with title + summary requirements |
| **Apply** | Select a job → upload `CV.pdf` → **[Submit Application]** → generates `NEW_APPLICATION` (submission itself triggers the agent) |
| **Confirmation** | Shows "Application received" — the agent runs in the background; the candidate sees no scoring UI |

### 8.2 Admin tab (login required)

| Page | Purpose |
|---|---|
| **Dashboard** | Counts per job: Applications / Interviews / Human Reviews / Completed Runs |
| **Jobs** | **Post a new job** (title, mandatory + preferred requirements, attach hiring policy), edit/close jobs |
| **Applications** | All applications with candidate profile, score, decision, and rationale |
| **Agent Activity** ⭐ | The centerpiece — a live, timestamped timeline of the autonomous run (`New application detected → … → Interview scheduled → RUN COMPLETED`) |
| **Interview Calendar** | **Weekly calendar view** of all scheduled interviews (from DB entries) — the recruiter's scheduling board |
| **Human Review** | Escalation queue: agent confidence, reason, recommendation, and **[Approve Interview] / [Reject]** buttons |
| **Agent Status** | Read-only **"Agent Status: Active"** indicator — shows the autonomous agent is running in the background |

The **Agent Activity** and **Interview Calendar** screens are deliberately prominent: they make the autonomous work and its concrete outcome (a scheduled interview) visible.

---

## 9. Robustness & Failure Handling

| Failure | Behavior |
|---|---|
| CV unparseable / low confidence | Candidate stored raw; application marked `evaluating_failed` and surfaced for manual review (never silently auto-rejected) |
| Mandatory info missing | Policy forbids auto-reject → routed to **HUMAN REVIEW** |
| Slot conflict / no slot available | Agent logs `no_slot`, marks application `human_review` (never double-books) |
| Tool call fails mid-run | ADK retries; idempotent writes keyed on `applicationId` so re-runs don't duplicate interviews/emails |
| Cloud Run crash | Stateless worker; application remains in a resumable state, re-triggered on next event |
| Policy file invalid/missing | Agent refuses to decide and escalates, rather than improvising |

---

## 10. Security & Compliance

- **No PII in logs** — logs reference `applicationId`/`candidateId` only; CV text is never logged.
- **Admin tab auth** — simple email/password session (hash via Secret Manager-managed secret); candidate tab is public by design.
- **Least-privilege IAM** — dedicated service account scoped to the Firestore collections it needs.
- **Secrets in Secret Manager** — API keys and password secrets never in code or build-time env.
- **Data governance** — Gemini API calls disable retention/use of prompts for model improvement.

---

## 11. Hackathon Requirements Checklist

| Requirement | How we satisfy it |
|---|---|
| Gemini 3.5 or newer | **Gemini 3.7 Flash** via Gemini API |
| ≥1 Google agent framework | **Google ADK** (`RecruitmentCoordinatorAgent`) |
| ≥1 Google Cloud infra service | **Cloud Run** (runtime) + **Firestore** (state & logs) |
| Asynchronous / background | Event-driven `NEW_APPLICATION` → agent runs unattended on Cloud Run |
| Heavy-lifting workflow | Full application→evaluate→decide→act→log pipeline with real actions |
| Deployable proof | Repo + reproducible deploy + demo video showing GCP console |

---

## 12. Judging Criteria Mapping

| Criterion (weight) | How we demonstrate |
|---|---|
| **Innovation & Utility (40%)** | Live demo: candidate applies via portal → agent evaluates, applies policy, decides, schedules interview (visible on calendar) / escalates / drafts rejection, logs every step — zero manual steps. The *action*, not a match score, is the star. |
| **Architectural Discipline (30%)** | Single ADK agent + 7 tools, policy-as-code decision engine, transactional Firestore state, DB-backed calendar, idempotent actions, complete activity log, Secret Manager, no-PII logs. |
| **Demo & Production Readiness (30%)** | Unedited video (candidate apply → admin live activity timeline → calendar → human-review queue), architecture diagram, one-command deploy, visible GCP console proof. |

---

## 13. Cost Controls (near $0)

- Cloud Run **scales to zero** when idle; app need not be live at judging.
- Firestore native mode, single small collection set.
- Gemini 3.7 Flash is low-cost per call; evaluation fires only on new applications.
- DB-backed calendar means no paid Calendar API usage.
- Demo video + repo screenshots serve as deployment proof.

---

## 14. Repository Structure

```
ai-recruitment-coordinator/
├── app/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py          # RecruitmentCoordinatorAgent (ADK)
│   │   ├── prompts.py
│   │   └── tools.py          # the 7 tools
│   ├── services/
│   │   ├── firestore.py
│   │   ├── cv_parser.py
│   │   ├── calendar.py       # slot store + conflict check → interview records
│   │   └── event_service.py  # NEW_APPLICATION event → agent trigger
│   ├── models/
│   │   └── schemas.py
│   ├── api/
│   │   └── routes.py         # jobs CRUD, applications, activity, calendar, reviews
│   └── main.py
├── frontend/
│   └── streamlit_app.py      # single app, two tabs: Candidate (apply) + Admin (jobs, activity, calendar, review)
├── data/
│   ├── jobs/
│   │   └── backend_engineer.md      # seed job (also creatable from dashboard)
│   └── policies/
│       └── hiring_policy.md
├── sample_cvs/
│   ├── strong_candidate.pdf
│   ├── borderline_candidate.pdf
│   └── weak_candidate.pdf
├── architecture.png
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
└── README.md
```

---

## 15. Deliverables

1. Source repository (ADK agent + 7 tools + FastAPI + Streamlit app (two tabs) + deploy config).
2. `README.md` — architecture, setup, one-command deploy, local run.
3. Architecture diagram (`architecture.png`).
4. Demo video (live, unedited) — candidate apply → autonomous run → HR calendar + review queue.
5. This proposal/specification.

---

## 16. Milestones

| # | Milestone | Outcome |
|---|---|---|
| 1 | Scaffold repo + ADK agent + FastAPI + Streamlit app (two tabs) skeleton | Local "hello" run |
| 2 | CV parser + `get_candidate_profile` | CV → structured profile |
| 3 | Jobs CRUD + `get_job_requirements` + `get_hiring_policy` + decision logic | HR posts jobs; score → INTERVIEW/HUMAN_REVIEW/REJECT |
| 4 | Action tools + `calendar.py` + Firestore | Full action chain; interviews persisted → calendar view |
| 5 | Candidate tab (apply) + Admin tab (activity timeline, calendar, review queue, agent status) | Two working tabs |
| 6 | Deploy to Cloud Run + demo video + README + architecture diagram | Submission-ready |

---

## 17. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Gemini structured-output variability | Enforce JSON schema in tools; validate + retry on failure |
| Scanned/image CVs | Gemini multimodal parsing; fallback to human review on failure |
| Over-engineering | 7-tool cap + explicit non-goals keep scope tight |
| "Just another score" perception | Demo leads with the action chain + activity timeline + calendar, not the number |
| HR auth complexity | Minimal email/password session for demo; note OAuth as future work |
| Calendar double-booking | `check_interview_slots()` conflict-checks against existing records before scheduling |

---

## 18. Future Work

- **Google Calendar API** swap-in behind `schedule_interview()` (real external calendar sync).
- Real email sending (swap `ready_to_send` for Gmail API).
- Recruiter feedback loop: approve/reject outcomes reweight scoring over time.
- Track 2 "intake partner": an agent that interviews the hiring manager to author the job spec + policy, feeding this Taskmaster agent.
- Multi-job routing and candidate-vs-candidate similarity search.
- Gmail/Drive ingestion via Pub/Sub for applications arriving outside the portal.
- OAuth / SSO for the Admin tab.
