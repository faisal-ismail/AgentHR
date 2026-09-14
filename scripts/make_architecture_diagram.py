"""Render architecture.png (and architecture.svg) from the proposal's §4 diagram.

Dependency-free PNG rendering via Pillow (no matplotlib). Also emits a crisp
SVG copy for the README.

Run:  python scripts/make_architecture_diagram.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_PNG = ROOT / "architecture.png"
OUT_SVG = ROOT / "architecture.svg"

W, H = 1400, 920
BG = (255, 255, 255)
INK = (30, 41, 59)
GREY = (100, 116, 139)

C_BLUE = (37, 99, 235)      # cloud/backend
C_ORANGE = (234, 88, 12)    # frontend
C_GREEN = (5, 150, 105)     # agent
C_PURPLE = (124, 58, 237)   # store
C_DARK = (15, 23, 42)


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_title = _font(34)
    f_h = _font(22)
    f_b = _font(16)
    f_s = _font(13)

    d.text((W // 2, 40), "RecruitFlow AI — Architecture", font=f_title, fill=INK, anchor="mm")

    def box(x0, y0, x1, y1, title, lines, fill, title_fill=None, outline=None, tsize=None):
        d.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=fill, outline=outline or fill)
        tcol = title_fill or "white"
        d.text(((x0 + x1) // 2, y0 + 28), title, font=tsize or f_h, fill=tcol, anchor="mm")
        yy = y0 + 58
        for ln in lines:
            d.text(((x0 + x1) // 2, yy), ln, font=f_s, fill=(255, 255, 255), anchor="mm")
            yy += 20

    def arrow(x0, y0, x1, y1, label=None):
        d.line([x0, y0, x1, y1], fill=INK, width=3)
        # arrowhead
        import math

        ang = math.atan2(y1 - y0, x1 - x0)
        hx, hy = 14, 14
        for da in (math.radians(150), math.radians(-150)):
            d.line(
                [x1, y1, x1 + hx * math.cos(ang + da), y1 + hy * math.sin(ang + da)],
                fill=INK,
                width=3,
            )
        if label:
            d.text(((x0 + x1) // 2, (y0 + y1) // 2 - 14), label, font=f_s, fill=GREY, anchor="mm")

    # Cloud Run boundary (dashed)
    d.rectangle([30, 30, W - 30, H - 30], outline=GREY, width=2)
    d.text((W - 45, H - 45), "Google Cloud Run", font=f_b, fill=GREY, anchor="rb")

    # Top actors
    box(90, 90, 430, 200, "Candidate", ["browse open jobs", "upload CV", "submit application"], C_ORANGE)
    box(970, 90, 1310, 200, "Recruiter (HR)", ["post/manage jobs", "watch agent run", "approve escalations"], C_ORANGE)

    # Streamlit
    box(340, 260, 1060, 400, "Streamlit App  (one frontend, two tabs)",
        ["Candidate tab — public, no login   ·   Admin tab — email/password session"],
        C_ORANGE)

    arrow(260, 200, 500, 260)
    arrow(1140, 200, 900, 260)

    # FastAPI
    box(520, 460, 880, 540, "FastAPI", ["NEW_APPLICATION event · job CRUD · query pipeline"], C_BLUE)
    arrow(700, 400, 700, 460)

    # ADK
    box(120, 620, 820, 860, "Google ADK — RecruitmentCoordinatorAgent",
        ["Gemini 3.7 Flash  ·  one agent, seven tools",
         "get_candidate_profile · get_job_requirements · get_hiring_policy",
         "check_interview_slots · schedule_interview · create_human_review",
         "draft_candidate_email  —  the agent decides the calls"],
        C_GREEN)

    # Firestore
    box(940, 620, 1360, 820, "Firestore",
        ["applications · jobs · candidates", "interviews · human_reviews", "emails · decisions · activity_log"],
        C_PURPLE)

    # Calendar
    box(940, 830, 1360, 880, "Interview Calendar  (DB-backed recruiter view)", [], C_DARK)

    arrow(700, 540, 470, 620)
    arrow(700, 540, 1140, 620)  # FastAPI -> Firestore (side)
    arrow(1140, 820, 1140, 830)  # Firestore -> calendar

    # Agent -> store
    arrow(820, 740, 940, 740, "state + logs")

    img.save(OUT_PNG)
    print(f"wrote {OUT_PNG}")


_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="920" viewBox="0 0 1400 920">
  <rect x="30" y="30" width="1340" height="860" fill="none" stroke="#64748b" stroke-width="2" stroke-dasharray="6 6"/>
  <text x="1370" y="880" text-anchor="end" font-family="sans-serif" font-size="16" fill="#64748b">Google Cloud Run</text>
  <text x="700" y="60" text-anchor="middle" font-family="sans-serif" font-size="34" font-weight="bold" fill="#0f172a">RecruitFlow AI — Architecture</text>

  <g font-family="sans-serif" text-anchor="middle">
    <rect x="90" y="90" width="340" height="110" rx="12" fill="#ea580c"/>
    <text x="260" y="128" fill="#fff" font-size="22" font-weight="bold">Candidate</text>
    <text x="260" y="156" fill="#fff" font-size="13">browse open jobs · upload CV</text>
    <text x="260" y="174" fill="#fff" font-size="13">submit application</text>

    <rect x="970" y="90" width="340" height="110" rx="12" fill="#ea580c"/>
    <text x="1140" y="128" fill="#fff" font-size="22" font-weight="bold">Recruiter (HR)</text>
    <text x="1140" y="156" fill="#fff" font-size="13">post jobs · watch agent run</text>
    <text x="1140" y="174" fill="#fff" font-size="13">approve escalations</text>

    <rect x="340" y="260" width="720" height="140" rx="12" fill="#ea580c"/>
    <text x="700" y="300" fill="#fff" font-size="22" font-weight="bold">Streamlit App — one frontend, two tabs</text>
    <text x="700" y="332" fill="#fff" font-size="14">Candidate tab (public) · Admin tab (login)</text>

    <rect x="520" y="460" width="360" height="80" rx="12" fill="#2563eb"/>
    <text x="700" y="492" fill="#fff" font-size="22" font-weight="bold">FastAPI</text>
    <text x="700" y="518" fill="#fff" font-size="13">NEW_APPLICATION event · job CRUD · query pipeline</text>

    <rect x="120" y="620" width="700" height="240" rx="12" fill="#059669"/>
    <text x="470" y="660" fill="#fff" font-size="22" font-weight="bold">Google ADK — RecruitmentCoordinatorAgent</text>
    <text x="470" y="692" fill="#fff" font-size="14">Gemini 3.7 Flash · one agent, seven tools</text>
    <text x="470" y="718" fill="#fff" font-size="13">get_candidate_profile · get_job_requirements · get_hiring_policy</text>
    <text x="470" y="738" fill="#fff" font-size="13">check_interview_slots · schedule_interview · create_human_review</text>
    <text x="470" y="758" fill="#fff" font-size="13">draft_candidate_email — the agent decides the calls</text>

    <rect x="940" y="620" width="420" height="200" rx="12" fill="#7c3aed"/>
    <text x="1150" y="660" fill="#fff" font-size="22" font-weight="bold">Firestore</text>
    <text x="1150" y="692" fill="#fff" font-size="13">applications · jobs · candidates</text>
    <text x="1150" y="712" fill="#fff" font-size="13">interviews · human_reviews</text>
    <text x="1150" y="732" fill="#fff" font-size="13">emails · decisions · activity_log</text>

    <rect x="940" y="830" width="420" height="50" rx="12" fill="#0f172a"/>
    <text x="1150" y="860" fill="#fff" font-size="15" font-weight="bold">Interview Calendar (DB-backed)</text>

    <g stroke="#0f172a" stroke-width="3" fill="#0f172a">
      <path d="M 260 200 L 500 258"/>
      <path d="M 1140 200 L 900 258"/>
      <path d="M 700 400 L 700 458"/>
      <path d="M 700 540 L 470 618"/>
      <path d="M 820 740 L 938 740"/>
      <path d="M 1140 820 L 1140 828"/>
    </g>
    <text x="880" y="734" font-size="13" fill="#64748b">state + logs</text>
  </g>
</svg>
"""


def write_svg() -> None:
    OUT_SVG.write_text(_SVG, encoding="utf-8")
    print(f"wrote {OUT_SVG}")


if __name__ == "__main__":
    draw()
    write_svg()
