"""AgentHR — Streamlit Application (Candidate Portal + HR Admin Portal).

- **Candidate** tab (public): a high-ticket careers portal — browse open roles,
  view skill breakdowns, and submit application profiles with CV uploads.
- **Admin** tab (login): executive dashboard, job posting manager, application
  evaluator, Action Approvals (HITL Gate), policy escalations, live agent activity trace,
  interview calendar, draft emails, and AgentCore runtime status.

Run:  streamlit run frontend/streamlit_app.py
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime
from typing import Any, Optional

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

st.set_page_config(
    page_title="AgentHR — High-Ticket AI Talent Platform",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# High-Ticket Styling & Theme (CSS)
# ---------------------------------------------------------------------------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Fira+Code:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Outfit', 'Plus Jakarta Sans', -apple-system, sans-serif;
}

.stApp {
    background-color: #0B0F19;
    color: #F8FAFC;
}

/* Page container padding */
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 3.5rem;
    max-width: 1280px;
}

/* ---------- Glow Gradients & Text ---------- */
.glow-text {
    background: linear-gradient(135deg, #00D2FF 0%, #0066FF 45%, #7000FF 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
}

/* ---------- Brand bar ---------- */
.rf-brand {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.1rem 1.8rem;
    background: rgba(19, 28, 49, 0.85);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 18px;
    margin-bottom: 1.4rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}

.rf-brand-left {
    display: flex;
    align-items: center;
    gap: 14px;
}

.rf-brand-logo-img {
    width: 42px;
    height: 42px;
}

.rf-brand-title {
    font-size: 1.6rem;
    font-weight: 900;
    letter-spacing: -0.03em;
    color: #FFFFFF;
    line-height: 1;
}

.rf-brand-sub {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    color: #94A3B8;
    text-transform: uppercase;
    margin-top: 3px;
}

.rf-brand-tag {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 0.4rem 0.9rem;
    background: rgba(0, 210, 255, 0.08);
    border: 1px solid rgba(0, 210, 255, 0.25);
    color: #00D2FF;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.03em;
}

.pulse-dot {
    width: 8px;
    height: 8px;
    background-color: #00D2FF;
    border-radius: 50%;
    box-shadow: 0 0 10px #00D2FF;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 210, 255, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(0, 210, 255, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 210, 255, 0); }
}

/* ---------- Hero (candidate) ---------- */
.rf-hero {
    background: linear-gradient(135deg, rgba(12, 27, 42, 0.9) 0%, rgba(22, 54, 92, 0.8) 50%, rgba(112, 0, 255, 0.15) 100%);
    backdrop-filter: blur(12px);
    border-radius: 24px;
    padding: 2.5rem 2.8rem;
    color: #fff;
    margin-bottom: 1.8rem;
    border: 1px solid rgba(255, 255, 255, 0.12);
    position: relative;
    overflow: hidden;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
}

.rf-hero::after {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 300px;
    height: 100%;
    background: radial-gradient(circle at 100% 0%, rgba(0, 210, 255, 0.15) 0%, transparent 70%);
    pointer-events: none;
}

.rf-hero h1 {
    margin: 0.6rem 0 0.6rem 0;
    font-size: 2.4rem;
    font-weight: 900;
    letter-spacing: -0.03em;
    line-height: 1.2;
}

.rf-hero p {
    margin: 0;
    font-size: 1.05rem;
    color: #CBD5E1;
    max-width: 720px;
    line-height: 1.6;
}

/* ---------- High-Ticket Cards ---------- */
.rf-card {
    background: rgba(19, 28, 49, 0.7);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 1.3rem 1.5rem;
    margin-bottom: 1rem;
    transition: all 0.25s ease;
}

.rf-card:hover {
    border-color: rgba(0, 210, 255, 0.3);
    box-shadow: 0 10px 25px rgba(0, 102, 255, 0.15);
}

.rf-job-card {
    background: rgba(19, 28, 49, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-left: 4px solid #0066FF;
    border-radius: 18px;
    padding: 1.4rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.rf-job-title {
    font-size: 1.2rem;
    font-weight: 800;
    color: #FFFFFF;
}

.rf-job-dept {
    font-size: 0.75rem;
    color: #00D2FF;
    font-weight: 700;
    margin: 0.2rem 0 0.6rem 0;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.rf-job-desc {
    font-size: 0.9rem;
    color: #94A3B8;
    margin-bottom: 0.8rem;
    line-height: 1.5;
}

.rf-pill {
    display: inline-block;
    padding: 0.25rem 0.7rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    margin: 0 0.3rem 0.3rem 0;
    letter-spacing: 0.02em;
}
.rf-pill-mand { background: rgba(0, 102, 255, 0.15); color: #38BDF8; border: 1px solid rgba(0, 102, 255, 0.3); }
.rf-pill-pref { background: rgba(112, 0, 255, 0.15); color: #C084FC; border: 1px solid rgba(112, 0, 255, 0.3); }

/* ---------- HITL Alert Box ---------- */
.rf-hitl-box {
    background: linear-gradient(135deg, rgba(180, 83, 9, 0.15) 0%, rgba(120, 53, 15, 0.25) 100%);
    border: 1px solid rgba(245, 158, 11, 0.4);
    border-left: 5px solid #F59E0B;
    border-radius: 16px;
    padding: 1.3rem 1.5rem;
    margin-bottom: 1rem;
}

/* ---------- Metrics Overrides ---------- */
div[data-testid="stMetric"] {
    background: rgba(19, 28, 49, 0.8) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 16px !important;
    padding: 1.1rem 1.2rem !important;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2) !important;
}
div[data-testid="stMetricLabel"] { color: #94A3B8 !important; font-weight: 700 !important; font-size: 0.8rem !important; text-transform: uppercase; letter-spacing: 0.05em; }
div[data-testid="stMetricValue"] { color: #FFFFFF !important; font-weight: 900 !important; font-size: 1.8rem !important; }

/* ---------- Buttons ---------- */
.stButton > button, .stFormSubmitButton > button {
    background: linear-gradient(135deg, #0066FF 0%, #7000FF 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.65rem 1.6rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.03em !important;
    box-shadow: 0 4px 15px rgba(0, 102, 255, 0.3) !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(0, 210, 255, 0.5) !important;
}

/* Form container */
div[data-testid="stForm"] {
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 20px !important;
    padding: 1.5rem 1.6rem !important;
    background: rgba(19, 28, 49, 0.7) !important;
    backdrop-filter: blur(16px) !important;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3) !important;
}

/* Tab styling */
.stTabs [data-baseweb="tab-list"] { gap: 0.6rem; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 0.5rem; }
.stTabs [data-baseweb="tab"] {
    font-weight: 700 !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 12px !important;
    color: #94A3B8 !important;
    background: transparent !important;
    border: 1px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #00D2FF !important;
    background: rgba(0, 210, 255, 0.1) !important;
    border: 1px solid rgba(0, 210, 255, 0.25) !important;
}

/* Footer */
.rf-footer {
    text-align: center;
    color: #64748B;
    font-size: 0.8rem;
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _brand_bar() -> str:
    return """
    <div class="rf-brand">
        <div class="rf-brand-left">
            <svg class="rf-brand-logo-img" viewBox="0 0 100 100">
                <defs>
                    <linearGradient id="brandGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#0066FF" />
                        <stop offset="50%" stop-color="#00D2FF" />
                        <stop offset="100%" stop-color="#7000FF" />
                    </linearGradient>
                </defs>
                <path d="M 50 10 L 80 80 L 62 80 L 50 50 L 38 80 L 20 80 Z" fill="url(#brandGrad)"/>
                <circle cx="50" cy="38" r="8" fill="#FFFFFF"/>
                <path d="M 38 58 C 38 50, 62 50, 62 58 L 62 66 L 38 66 Z" fill="#FFFFFF"/>
                <path d="M 15 70 C 15 90, 85 90, 85 65" stroke="url(#brandGrad)" stroke-width="5" stroke-linecap="round" fill="none"/>
            </svg>
            <div>
                <div class="rf-brand-title">Agent<span class="glow-text">HR</span></div>
                <div class="rf-brand-sub">HIRE • SCHEDULE • AUTOMATE</div>
            </div>
        </div>
        <div class="rf-brand-tag">
            <span class="pulse-dot"></span>
            AWS Hackathon Entry &bull; Strands SDK &amp; Amazon Nova Pro
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# API helper
# ---------------------------------------------------------------------------
def api(
    method: str,
    path: str,
    token: Optional[str] = None,
    json: Optional[dict] = None,
    data: Optional[dict] = None,
    files: Optional[dict] = None,
) -> tuple[Optional[Any], Optional[str]]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"{BACKEND_URL}{path}"
    try:
        resp = requests.request(method, url, headers=headers, json=json, data=data, files=files, timeout=35)
    except requests.RequestException as exc:
        return None, f"Cannot reach backend API at {BACKEND_URL}: {exc}"
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code >= 400:
        detail = (body or {}).get("detail", resp.text) if isinstance(body, dict) else resp.text
        return None, str(detail)
    return body, None


def format_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M:%S")
    except Exception:
        return iso


def slot_weekday(iso: str) -> int:
    try:
        return datetime.fromisoformat(iso).weekday()
    except Exception:
        return -1


# ---------------------------------------------------------------------------
# Candidate Tab (Public View)
# ---------------------------------------------------------------------------
def candidate_tab() -> None:
    st.markdown(
        """
        <div class="rf-hero">
            <span class="rf-pill rf-pill-mand" style="background:rgba(0,210,255,0.15); color:#00D2FF; font-size:0.75rem;">LIVE TALENT PORTAL</span>
            <h1>Autonomous Recruiting Coordinator Platform</h1>
            <p>Submit your profile for top roles. Our agent screens candidate qualifications objectively against policy rules, schedules interviews, and drafts personalized invites—with zero hallucination guarantees.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    jobs, err = api("GET", "/api/jobs?open_only=true")
    if err:
        st.error(err)
        return
    if not jobs:
        st.info("No open positions posted at the moment. Please check back soon.")
        return

    left, right = st.columns([5, 6], gap="large")

    # ---- Left Column: Position Catalog ----
    with left:
        st.markdown('<h3 style="color:#00D2FF; font-weight:800; margin-bottom:1rem;">⚡ Open Positions</h3>', unsafe_allow_html=True)
        for job in jobs:
            pills = ""
            for req in job.get("mandatory", []):
                pills += f'<span class="rf-pill rf-pill-mand">Mandatory: {html.escape(req)}</span>'
            for req in job.get("preferred", []):
                pills += f'<span class="rf-pill rf-pill-pref">Preferred: {html.escape(req)}</span>'
            st.markdown(
                f"""
                <div class="rf-job-card">
                    <div class="rf-job-title">{html.escape(job.get('title', ''))}</div>
                    <div class="rf-job-dept">{html.escape(job.get('department', 'Engineering'))}</div>
                    <div class="rf-job-desc">{html.escape((job.get('description') or '')[:180])}...</div>
                    <div>{pills}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ---- Right Column: Application Submission Form ----
    with right:
        st.markdown('<h3 style="color:#FFFFFF; font-weight:800; margin-bottom:1rem;">📝 Candidate Application</h3>', unsafe_allow_html=True)
        job_titles = {j.get("title"): j.get("id") for j in jobs}

        with st.form("apply_form", clear_on_submit=True):
            st.markdown("##### 1. Position Selection")
            selected_title = st.selectbox("Target Position", list(job_titles.keys()))
            
            st.markdown("##### 2. Contact Profile")
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Full Name", placeholder="e.g. Sarah Ali")
                email = st.text_input("Email Address", placeholder="sarah@example.com")
            with c2:
                phone = st.text_input("Phone (Optional)", placeholder="+1 (555) 019-2834")

            st.markdown("##### 3. Resume / CV Attachment")
            cv = st.file_uploader(
                "Upload Resume (PDF, DOCX, TXT, or MD)",
                type=["pdf", "docx", "txt", "md"],
            )
            
            submitted = st.form_submit_button("🚀 Submit Application & Run Agent Evaluation", use_container_width=True)

        if submitted:
            if not name or not email or not cv:
                st.warning("Please provide your full name, email address, and CV file.")
            else:
                job_id = job_titles[selected_title]
                files = {"cv": (cv.name, cv.getvalue(), cv.type or "application/octet-stream")}
                data = {"job_id": job_id, "name": name, "email": email, "phone": phone}
                result, err = api("POST", "/api/applications", data=data, files=files)
                if err:
                    st.error(err)
                else:
                    st.success("🎉 Application submitted successfully! The RecruitmentCoordinatorAgent is currently analyzing your qualifications.")

    st.markdown('<div class="rf-footer">AgentHR &bull; Powered by AWS Bedrock (Amazon Nova Pro) &amp; Strands Agents SDK &bull; agenthr.sineix.com</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Admin Tab (Recruiter Portal)
# ---------------------------------------------------------------------------
def admin_tab() -> None:
    if "token" not in st.session_state:
        _admin_login()
        return

    token = st.session_state.token
    with st.sidebar:
        st.markdown("### 🧭 Recruiter Control Center")
        st.caption(f"Authenticated as: **{st.session_state.get('admin_email')}**")
        st.markdown("---")
        page = st.radio(
            "Navigation",
            [
                "Dashboard",
                "Action Approvals (HITL)",
                "Applications",
                "Jobs Management",
                "Human Review Queue",
                "Agent Activity Trace",
                "Interview Calendar",
                "Candidate Emails",
                "Agent & Cloud Status",
            ],
        )
        st.markdown("---")
        if st.button("🚪 Log Out", use_container_width=True):
            for key in ("token", "admin_email"):
                st.session_state.pop(key, None)
            st.rerun()

    if page == "Dashboard":
        _admin_dashboard(token)
    elif page == "Action Approvals (HITL)":
        _admin_approvals(token)
    elif page == "Applications":
        _admin_applications(token)
    elif page == "Jobs Management":
        _admin_jobs(token)
    elif page == "Human Review Queue":
        _admin_reviews(token)
    elif page == "Agent Activity Trace":
        _admin_activity(token)
    elif page == "Interview Calendar":
        _admin_calendar(token)
    elif page == "Candidate Emails":
        _admin_emails(token)
    elif page == "Agent & Cloud Status":
        _admin_agent_status(token)


def _page_header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<h2 style="color:#FFFFFF; font-weight:900; margin-bottom:0.2rem;">{html.escape(title)}</h2>'
        + (f'<p style="color:#94A3B8; font-size:0.95rem; margin-bottom:1.5rem;">{html.escape(subtitle)}</p>' if subtitle else ""),
        unsafe_allow_html=True,
    )


def _admin_login() -> None:
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown('<h2 style="text-align:center; color:#FFFFFF; font-weight:900;">Recruiter Portal Authentication</h2>', unsafe_allow_html=True)
        st.caption("Access the AgentHR admin dashboard and Human-in-the-Loop action approval gate.")
        
        with st.form("login"):
            email = st.text_input("Administrator Email", value=os.getenv("ADMIN_EMAIL", "hr@agenthr.ai"))
            password = st.text_input("Password", type="password", value="admin123")
            submitted = st.form_submit_button("🔐 Sign In to Recruiter Console", use_container_width=True)
            
        if submitted:
            body, err = api("POST", "/api/login", json={"email": email, "password": password})
            if err:
                st.error(err)
            else:
                st.session_state.token = body["token"]
                st.session_state.admin_email = body["email"]
                st.rerun()


def _admin_dashboard(token: str) -> None:
    _page_header("Executive Dashboard", "Real-time recruitment metrics, application scores, and action checkpoints.")

    body, err = api("GET", "/api/dashboard", token=token)
    if err:
        st.error(err)
        return

    jobs = body.get("jobs", [])
    total_apps = sum(j.get("applications", 0) for j in jobs)
    total_interviews = sum(j.get("interviews", 0) for j in jobs)
    pending_approvals = body.get("pending_approvals", 0)
    pending_reviews = body.get("pending_reviews", 0)
    open_jobs = sum(1 for j in jobs if j.get("status") != "closed")

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric("Open Roles", open_jobs)
    with k2:
        st.metric("Applications", total_apps)
    with k3:
        st.metric("Action Approvals", pending_approvals, delta="HITL Intercept" if pending_approvals > 0 else None)
    with k4:
        st.metric("Human Reviews", pending_reviews)
    with k5:
        st.metric("Interviews Booked", total_interviews)

    st.markdown("---")
    if not jobs:
        st.info("No job postings available.")
        return

    st.markdown('<h3 style="color:#00D2FF; font-weight:800; margin-bottom:1rem;">Active Positions Status</h3>', unsafe_allow_html=True)
    for job in jobs:
        status = job.get("status", "open")
        badge = "🟢 Open" if status != "closed" else "⚫ Closed"
        with st.container():
            st.markdown(
                f"""
                <div class="rf-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="font-size:1.1rem; font-weight:800; color:#FFF;">{html.escape(job.get('title'))}</span>
                            <span style="font-size:0.8rem; margin-left:10px; color:#00D2FF; font-weight:700;">{badge}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#94A3B8;">Department: <strong>{html.escape(job.get('department', 'General'))}</strong></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _admin_approvals(token: str) -> None:
    _page_header("Action Approvals (HITL Gate)", "Supervised checkpoints intercepted by Strands BeforeToolCallEvent hook before executing outward actions.")

    approvals, err = api("GET", "/api/approvals", token=token)
    if err:
        st.error(err)
        return

    pending = [a for a in approvals if a.get("status") == "pending"]
    if not pending:
        st.success("✅ All proposed agent actions are authorized. No pending approval intercepts.")
        return

    for a in pending:
        tool_name = a.get("tool_name", "schedule_interview")
        action_desc = "Schedule Interview & Draft Invitation Email" if "interview" in tool_name else tool_name.replace("_", " ").title()

        st.markdown(
            f"""
            <div class="rf-hitl-box">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                    <span style="font-size:1.1rem; font-weight:800; color:#F59E0B;">⚠️ INTERCEPTED ACTION: {html.escape(action_desc)}</span>
                    <span style="font-size:0.8rem; font-weight:700; background:rgba(245,158,11,0.2); color:#FCD34D; padding:0.2rem 0.6rem; border-radius:999px;">Awaiting Recruiter Approval</span>
                </div>
                <div style="color:#CBD5E1; font-size:0.9rem;">
                    Candidate: <strong>{html.escape(a.get('candidate_name', ''))}</strong> ({html.escape(a.get('candidate_email', ''))}) &bull; Job: <strong>{html.escape(a.get('job_title', ''))}</strong> &bull; Score: <strong>{a.get('score')}</strong>
                </div>
                <div style="color:#FCD34D; font-size:0.85rem; margin-top:0.4rem;">
                    Checkpoint Reason: {html.escape(a.get('reason', 'Authorization required before sending email or booking calendar slot.'))}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2, _ = st.columns([1.5, 1.5, 3])
        with c1:
            if st.button("✅ Approve Action & Resume Agent", key=f"appr_act_{a['id']}", use_container_width=True):
                res, err = api("POST", f"/api/approvals/{a['id']}/decision", token=token, json={"approved": True})
                if err:
                    st.error(err)
                else:
                    st.success("Action approved! Agent execution resumed successfully.")
                    st.rerun()
        with c2:
            if st.button("❌ Reject Proposed Action", key=f"rej_act_{a['id']}", use_container_width=True):
                res, err = api("POST", f"/api/approvals/{a['id']}/decision", token=token, json={"approved": False})
                if err:
                    st.error(err)
                else:
                    st.warning("Action rejected by recruiter.")
                    st.rerun()


def _admin_jobs(token: str) -> None:
    _page_header("Jobs Management", "Post positions and update mandatory/preferred skill requirements.")

    with st.expander("➕ Post New Position", expanded=False):
        with st.form("new_job"):
            title = st.text_input("Job Title")
            department = st.text_input("Department", value="Engineering")
            description = st.text_area("Description")
            mandatory = st.text_area("Mandatory Criteria (one per line)", placeholder="Python\nREST APIs\n3+ years experience")
            preferred = st.text_area("Preferred Criteria (one per line)", placeholder="FastAPI\nDocker\nAWS")
            posted = st.form_submit_button("Post Position", use_container_width=True)
            
        if posted:
            payload = {
                "title": title,
                "department": department,
                "description": description,
                "mandatory": [l.strip() for l in mandatory.splitlines() if l.strip()],
                "preferred": [l.strip() for l in preferred.splitlines() if l.strip()],
            }
            _, err = api("POST", "/api/jobs", token=token, json=payload)
            if err:
                st.error(err)
            else:
                st.success("Position posted successfully.")
                st.rerun()

    jobs, err = api("GET", "/api/jobs", token=token)
    if err:
        st.error(err)
        return

    for job in jobs:
        with st.expander(f"{job.get('title')} ({job.get('status').upper()})", expanded=False):
            st.write(job.get("description"))
            st.markdown("**Mandatory Criteria:** " + ", ".join(job.get("mandatory", [])))
            st.markdown("**Preferred Criteria:** " + ", ".join(job.get("preferred", [])))
            if job.get("status") != "closed":
                if st.button("Close Position", key=f"close_{job['id']}"):
                    api("POST", f"/api/jobs/{job['id']}/close", token=token)
                    st.rerun()


def _admin_applications(token: str) -> None:
    _page_header("Applications Evaluated", "Candidates processed by the policy scoring engine and Strands agent.")

    apps, err = api("GET", "/api/applications", token=token)
    if err:
        st.error(err)
        return
    if not apps:
        st.info("No applications received yet.")
        return

    status_icon = {
        "new": "🆕", "evaluating": "⏳", "awaiting_approval": "⏸️", "interview": "✅",
        "human_review": "🟡", "rejected": "❌", "evaluating_failed": "⚠️",
    }
    for a in apps:
        outcome = a.get("outcome")
        title = (
            f"{status_icon.get(a.get('status'), '•')} {a.get('candidate_name')} → "
            f"{a.get('job_title')} | Status: {a.get('status')}"
        )
        if outcome:
            title += f" | Decision: {outcome} ({a.get('score')}/100)"

        with st.expander(title, expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Email:** {a.get('candidate_email')}")
                st.markdown(f"**Experience:** {a.get('experience_years')} years")
                st.markdown("**Skills:** " + ", ".join(a.get("skills", [])))
                st.markdown("**Education:** " + "; ".join(a.get("education", [])))
            with c2:
                st.markdown(f"**Calculated Score:** `{a.get('score')}/100`")
                st.markdown(f"**Policy Decision:** `{a.get('outcome')}`")
                st.markdown(f"**Current Status:** `{a.get('status')}`")
                st.markdown(f"**Rationale:** {a.get('rationale')}")
                if a.get("mandatory_met"):
                    st.markdown("**Mandatory Met:** " + ", ".join(a["mandatory_met"]))
                if a.get("mandatory_missing"):
                    st.markdown("**Mandatory Unmet:** " + ", ".join(a["mandatory_missing"]))
            if st.checkbox("View Raw CV Text", key=f"show_cv_{a.get('id')}"):
                st.code(a.get("cv_text", "")[:3000] or "(No text extracted)", language="text")


def _admin_activity(token: str) -> None:
    _page_header("Agent Activity Trace", "Step-by-step audit trail of Strands agent tool executions and policy decisions.")

    logs, err = api("GET", "/api/activity", token=token)
    if err:
        st.error(err)
        return
    if not logs:
        st.info("No activity logs recorded yet.")
        return

    for l in logs:
        c_name = l.get("candidate_name") or "Application"
        st_label = l.get("status", "completed").upper()
        title = f"⏰ {format_ts(l.get('started_at', ''))} &bull; {c_name} &bull; Status: {st_label}"

        with st.expander(title, expanded=False):
            steps = l.get("steps", [])
            major_steps = [s for s in steps if s.get("level") == "major"]

            st.markdown("##### 📍 Headline Milestones")
            for step in major_steps:
                ts = format_ts(step.get("timestamp", ""))
                st.markdown(f"- `{ts}` **{step.get('action')}**: {step.get('detail', '')}")

            with st.expander("🔍 Verbose Tool Invocation Trace", expanded=False):
                verbose_steps = [s for s in steps if s.get("level") != "major"]
                for step in verbose_steps:
                    action = step.get("action", "")
                    ts = format_ts(step.get("timestamp", ""))
                    st.markdown(f"**`{ts}` Tool Called: `{action}`**")
                    detail = {k: v for k, v in step.items() if k not in ("action", "timestamp", "level")}
                    if detail:
                        st.code(json.dumps(detail, indent=2), language="json")


def _admin_calendar(token: str) -> None:
    _page_header("Interview Calendar", "Booked candidate interview slots and calendar availability.")

    data, err = api("GET", "/api/calendar", token=token)
    if err:
        st.error(err)
        return

    interviews = data.get("interviews", [])
    available = data.get("available_slots", [])

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Booked Interviews", len(interviews))
    with c2:
        st.metric("Open Calendar Slots", len(available))

    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    cols = st.columns(5)
    for i, day in enumerate(weekdays):
        cols[i].markdown(f"### {day}")
        for it in interviews:
            if slot_weekday(it.get("slot_start", "")) == i:
                t = datetime.fromisoformat(it["slot_start"]).strftime("%b %d &bull; %H:%M")
                cols[i].success(f"**{t}**\n\nCandidate: {it.get('candidate_name')}\n\nRole: _{it.get('job_title')}_")


def _admin_reviews(token: str) -> None:
    _page_header("Human Review Queue", "Borderline candidates (Score 60-84) requiring manual recruiter review.")

    reviews, err = api("GET", "/api/reviews", token=token)
    if err:
        st.error(err)
        return
    pending = [r for r in reviews if r.get("status") == "pending"]
    if not pending:
        st.success("✅ No pending policy escalations in the queue.")
        return
    for r in pending:
        with st.expander(f"{r.get('candidate_name')} → {r.get('job_title')} (Score: {r.get('score')}/100)", expanded=True):
            st.markdown(f"**Escalation Reason:** {r.get('reason')}")
            st.markdown(f"**Agent Recommendation:** {r.get('recommendation')}")
            c1, c2, _ = st.columns([1.5, 1.5, 3])
            with c1:
                if st.button("✅ Approve Interview", key=f"appr_{r['id']}", use_container_width=True):
                    api("POST", f"/api/reviews/{r['id']}/decision", token=token, json={"approved": True})
                    st.rerun()
            with c2:
                if st.button("❌ Reject Candidate", key=f"rej_{r['id']}", use_container_width=True):
                    api("POST", f"/api/reviews/{r['id']}/decision", token=token, json={"approved": False})
                    st.rerun()


def _admin_emails(token: str) -> None:
    _page_header("Candidate Email Queue", "Personalized candidate communications synthesized by Amazon Nova Pro.")

    emails, err = api("GET", "/api/emails", token=token)
    if err:
        st.error(err)
        return
    if not emails:
        st.info("No candidate emails in the queue.")
        return
    for e in emails:
        with st.expander(f"✉️ {e.get('type').upper()} → {e.get('to')} ({e.get('candidate_name')})", expanded=False):
            st.markdown(f"**Subject Line:** {e.get('subject')}")
            st.markdown(f"**Status:** `{e.get('email_status')}`")
            st.code(e.get("body"), language="text")


def _admin_agent_status(token: str) -> None:
    _page_header("Agent & Cloud Status", "System runtime specifications, Strands SDK metadata, and Bedrock model configuration.")

    body, err = api("GET", "/api/agent/status", token=token)
    if err:
        st.error(err)
        return
        
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Agent Framework", "Strands Agents SDK")
    with c2:
        st.metric("Foundation Model", "Amazon Nova Pro")
    with c3:
        st.metric("HITL Approval Gate", "ACTIVE (Enforced)" if body.get("approval_gate") else "Disabled")

    st.markdown("---")
    st.markdown("#### System Specifications")
    st.markdown(f"- **Agent Coordinator Class**: `{body.get('agent', 'RecruitmentCoordinatorAgent')}`")
    st.markdown(f"- **Active Model ID**: `{body.get('model', 'us.amazon.nova-pro-v1:0')}`")
    st.markdown("- **AWS Bedrock AgentCore Runtime**: `POST /invocations` & `GET /ping` endpoints ready")
    st.markdown("- **Datastore Backend**: Amazon DynamoDB (10 Tables) / Memory Store")
    st.markdown("- **Supervised Checkpoint**: Strands `BeforeToolCallEvent` hook intercepting `schedule_interview` and `draft_candidate_email`")


# ---------------------------------------------------------------------------
# App Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    _inject_css()
    st.markdown(_brand_bar(), unsafe_allow_html=True)

    tab_candidate, tab_admin = st.tabs(["💼 Candidate Careers Portal", "🔐 Recruiter Control Console"])
    with tab_candidate:
        candidate_tab()
    with tab_admin:
        admin_tab()


if __name__ == "__main__":
    main()
