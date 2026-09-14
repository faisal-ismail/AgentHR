# Hiring Policy — AgentHR

This document is the single source of truth for candidate decisions. The
`RecruitmentCoordinatorAgent` reads this policy and applies it to every
application. It is deliberately human-readable so that HR can change the
rules without touching code.

## Decision rules

| Score range | All mandatory met? | Decision        |
|-------------|--------------------|-----------------|
| 85 – 100    | yes                | **INTERVIEW**   |
| 60 – 84     | yes                | **HUMAN REVIEW**|
| < 60        | yes                | **REJECT**      |
| any         | no (or unknown)    | **HUMAN REVIEW**|

**Overrides**

1. Never auto-`REJECT` when mandatory information is **MISSING** from the CV
   (i.e. the CV does not mention the requirement at all). Route to
   **HUMAN REVIEW** instead.
2. Never recommend `INTERVIEW` when any mandatory requirement is missing or
   unmet.
3. When a scheduled interview slot is unavailable (double-booking or no free
   slot), the application is escalated to **HUMAN REVIEW** — it is never
   silently dropped.

## Scoring formula

- Mandatory requirements contribute **70%** of the score.
- Preferred requirements contribute **30%** of the score.

```
mandatory_score = 70 * (mandatory_met / total_mandatory)
preferred_score = 30 * (preferred_met / total_preferred)
score = round(mandatory_score + preferred_score, 1)
```

- A requirement is **met** when the candidate's skills, experience, or CV
  text demonstrate it (keyword + experience-years matching).
- A requirement is **missing** when there is no evidence for it in the CV.
- A requirement is **not met** when the CV contradicts it (not auto-detected
  in v1; treated as missing for mandatory requirements).

## Example

Job — Backend Engineer:
- Mandatory: Python, REST APIs, 3+ years experience
- Preferred: FastAPI, Docker, AWS

A candidate with Python + REST APIs + 5 years + FastAPI + Docker:
- mandatory_met = 3/3 → 70
- preferred_met = 2/3 → 20
- score = 90 → **INTERVIEW**
