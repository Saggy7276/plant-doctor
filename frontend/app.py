import base64
import json
import os
import re
from pathlib import Path
import requests
import streamlit as st
import extra_streamlit_components as stx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

API = os.getenv("API_BASE", "http://localhost:8000")

_cm = stx.CookieManager(key="pd_cm")

st.set_page_config(
    page_title="Plant Doctor",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── global ── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {
    background: #1c1a16 !important;
}
[data-testid="stMain"] { padding-top: 1.5rem; }

/* native Streamlit text on dark bg */
[data-testid="stMainBlockContainer"] p,
[data-testid="stMainBlockContainer"] span,
[data-testid="stMainBlockContainer"] label,
[data-testid="stMainBlockContainer"] small,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stMarkdownContainer"] li { color: #f5f0e8 !important; }

/* inputs / textareas / selectboxes */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div,
[data-baseweb="input"] > div {
    background: #2a2520 !important;
    border-color: #5a4a35 !important;
    color: #f5f0e8 !important;
}

/* ── sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#1a1507 0%,#231c0e 100%) !important;
}
[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.12) !important; }
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p { color:#f5f0e8 !important; }
[data-testid="stSidebar"] .stButton > button {
    border:1px solid rgba(255,255,255,.18) !important;
    background:rgba(255,255,255,.07) !important;
    color:#f5f0e8 !important;
    border-radius:8px !important;
    text-align:left !important;
    font-size:.88rem !important;
}
[data-testid="stSidebar"] .stButton > button p,
[data-testid="stSidebar"] .stButton > button span,
[data-testid="stSidebar"] .stButton > button div { color:#f5f0e8 !important; }
[data-testid="stSidebar"] .stButton > button:hover {
    background:rgba(255,255,255,.18) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background:rgba(134,239,172,.18) !important;
    border-color:#86efac !important;
    font-weight:700 !important;
}

/* ── tabs ── */
button[data-baseweb="tab"] { color:#a09070 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color:#86efac !important; font-weight:700 !important; }
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: #2a2520 !important;
    border-radius: 10px 10px 0 0;
}

/* ── main buttons ── */
[data-testid="stMainBlockContainer"] .stButton > button {
    background: #2a2520 !important;
    border: 1px solid #5a4a35 !important;
    color: #f5f0e8 !important;
    border-radius: 8px !important;
}
[data-testid="stMainBlockContainer"] .stButton > button p,
[data-testid="stMainBlockContainer"] .stButton > button span,
[data-testid="stMainBlockContainer"] .stButton > button div { color: #f5f0e8 !important; }
[data-testid="stMainBlockContainer"] .stButton > button[kind="primary"] {
    background: #5a7a3a !important;
    border-color: #5a7a3a !important;
}
[data-testid="stMainBlockContainer"] .stButton > button[kind="primary"] p,
[data-testid="stMainBlockContainer"] .stButton > button[kind="primary"] span,
[data-testid="stMainBlockContainer"] .stButton > button[kind="primary"] div { color: #f5f0e8 !important; }
[data-testid="stMainBlockContainer"] .stButton > button:hover {
    border-color: #86efac !important;
    background: #332d24 !important;
}

/* ── plant card ── */
.pcard {
    border-radius:14px;
    background:#2a2520;
    box-shadow:0 1px 6px rgba(0,0,0,.4),0 4px 18px rgba(0,0,0,.3);
    margin-bottom:.5rem;
    border-left:5px solid #5a4a35;
    transition:box-shadow .2s;
    overflow:hidden;
}
.pcard:hover { box-shadow:0 4px 28px rgba(0,0,0,.5); }
.pcard-body  { padding:.85rem 1rem .7rem; }
.pcard-name    { font-size:1.05rem; font-weight:700; margin:0 0 2px; color:#86efac; }
.pcard-species { font-size:.8rem; color:#a09070; margin:0 0 8px; }
.pcard-date    { font-size:.72rem; color:#7a6a58; margin-top:6px; }

/* ── status badge ── */
.badge {
    display:inline-block; padding:3px 12px;
    border-radius:999px; font-size:.72rem;
    font-weight:700; color:#fff; letter-spacing:.04em;
}
@keyframes pulse-red {
    0%,100% { box-shadow:0 0 0 0 rgba(239,68,68,.55); }
    55%      { box-shadow:0 0 0 7px rgba(239,68,68,0); }
}
.badge-crit { animation:pulse-red 1.8s ease-in-out infinite; }

/* ── stat card ── */
.stat-box {
    background:#2a2520; border:1px solid #3d3328;
    border-radius:14px; padding:1rem 1.2rem;
    text-align:center;
    box-shadow:0 1px 6px rgba(0,0,0,.35);
}
.stat-num { font-size:2.2rem; font-weight:800; line-height:1.1; }
.stat-lbl { font-size:.78rem; color:#a09070; margin-top:3px; font-weight:500; }

/* ── section header strip ── */
.sec-hdr {
    background:#332d1e; border-left:4px solid #86efac;
    padding:.35rem .8rem; border-radius:0 8px 8px 0;
    font-weight:600; color:#f5f0e8; margin:.9rem 0 .4rem;
}

/* ── gallery caption ── */
.gcap { font-size:.72rem; color:#a09070; text-align:center; margin-top:2px; }

/* ── step pill ── */
.step-pill {
    display:inline-block; background:#332d1e; color:#86efac;
    border-radius:999px; padding:3px 14px; font-size:.78rem;
    font-weight:700; margin-bottom:.5rem;
    border:1px solid #5a4a35;
}

/* ── timeline row ── */
.tl-row {
    display:flex; align-items:center; gap:.75rem;
    padding:.5rem 0; border-bottom:1px solid #3d3328;
}
.tl-dot  { width:11px; height:11px; border-radius:50%; flex-shrink:0; }
.tl-date { font-size:.75rem; color:#7a6a58; white-space:nowrap; min-width:75px; }
.tl-text { font-size:.87rem; color:#f5f0e8; }

/* ── detail hero ── */
.hero {
    border-radius:16px;
    background:linear-gradient(135deg,#2a1f0a,#3d2e12);
    padding:1.6rem 2rem; color:#f5f0e8; margin-bottom:1.2rem;
    box-shadow:0 4px 20px rgba(0,0,0,.5);
    border:1px solid #5a4a35;
}
.hero-name    { font-size:1.9rem; font-weight:800; margin:0 0 2px; color:#f5f0e8; }
.hero-species { font-size:1rem; opacity:.7; margin:0 0 .9rem; color:#f5f0e8; }

/* ── checkin arrow ── */
.ck-arrow {
    display:flex; align-items:center; justify-content:center;
    font-size:2.4rem; padding:.5rem; color:#86efac;
}

/* ── change tag ── */
.ch-tag {
    display:inline-block; background:#332d1e;
    border:1px solid #5a4a35; border-radius:8px;
    padding:4px 12px; font-size:.83rem; color:#f5f0e8;
    margin:3px 4px 3px 0;
}

/* ── upload zone placeholder ── */
.upload-ph {
    border:2px dashed #5a4a35; border-radius:14px;
    padding:2rem 1rem; text-align:center;
    background:#2a2520; color:#86efac; font-size:2.5rem;
}

/* ── recent diag row ── */
.rd-row {
    display:flex; align-items:center; gap:.6rem;
    padding:.45rem 0; border-bottom:1px solid #3d3328;
}
.rd-ts   { font-size:.75rem; color:#7a6a58; min-width:110px; font-family:monospace; }
.rd-name { font-size:.88rem; font-weight:600; color:#f5f0e8; flex:1; }
</style>
""", unsafe_allow_html=True)


# ── constants ─────────────────────────────────────────────────────────────────
_ISSUE_TO_STATUS = {
    "healthy":       ("Healthy",    "#22c55e"),
    "disease":       ("Critical",   "#ef4444"),
    "pest":          ("Critical",   "#ef4444"),
    "overwatering":  ("Recovering", "#f97316"),
    "underwatering": ("Recovering", "#f97316"),
    "nutrient":      ("Recovering", "#eab308"),
    "light":         ("Recovering", "#8b5cf6"),
    "uncertain":     ("Uncertain",  "#6b7280"),
}
_PROG_COLORS = {"improving": "#22c55e", "stable": "#eab308", "worsening": "#ef4444"}
_PROG_LABELS = {"improving": "Improving ↑", "stable": "Stable →", "worsening": "Worsening ↓"}
_DOT_EMOJI   = {"Healthy": "🟢", "Recovering": "🟡", "Critical": "🔴", "Uncertain": "❓", "Unknown": "⚪"}


def _status(issue: str | None) -> tuple[str, str]:
    return _ISSUE_TO_STATUS.get(issue or "", ("Unknown", "#9ca3af"))


def badge_html(issue: str | None, animate: bool = False) -> str:
    label, color = _status(issue)
    cls = "badge badge-crit" if animate and label == "Critical" else "badge"
    return f'<span class="{cls}" style="background:{color}">{label}</span>'


# ── API helpers ───────────────────────────────────────────────────────────────
def _h() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}

def _get(path: str, **kw) -> requests.Response:
    return requests.get(f"{API}{path}", headers=_h(), timeout=10, **kw)

def _post(path: str, **kw) -> requests.Response:
    return requests.post(f"{API}{path}", headers=_h(), timeout=60, **kw)

def _err(r: requests.Response, fallback: str = "Request failed.") -> str:
    try:
        return r.json().get("detail", fallback)
    except Exception:
        return f"{fallback} (HTTP {r.status_code})"

def _refresh() -> None:
    _load_plants.clear()
    _load_history.clear()

def img_url(stored: str) -> str:
    p = stored.replace("\\", "/")
    i = p.find("uploads/")
    return f"{API}/{p[i:]}" if i != -1 else ""


# ── care-plan parser ──────────────────────────────────────────────────────────
def _extract_bold_header(content: str) -> str | None:
    """Return inner text if content is purely a bold label (**Title** or **Title**:), else None."""
    m = re.fullmatch(r'\*\*(.+?)\*\*:?', content.strip())
    return m.group(1).strip() if m else None


def parse_care_plan(text: str) -> list[tuple[str, str]]:
    items = []
    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r'^\d+\.\s+', line):
            content = re.sub(r'^\d+\.\s+', '', line)
            hdr = _extract_bold_header(content)
            items.append(("header", hdr) if hdr else ("step", content))
        elif line.startswith(("- ", "* ", "• ")):
            content = line[2:].strip()
            hdr = _extract_bold_header(content)
            items.append(("header", hdr) if hdr else ("step", content))
        elif re.match(r'^#{1,3}\s', line):
            items.append(("header", re.sub(r'^#+\s*', '', line).strip()))
        else:
            hdr = _extract_bold_header(line)
            items.append(("header", hdr) if hdr else ("text", line))
    return items


def render_care_plan(text: str, key_prefix: str) -> None:
    items     = parse_care_plan(text)
    step_keys = [f"{key_prefix}_{i}" for i, (k, _) in enumerate(items) if k == "step"]
    n         = len(step_keys)
    done      = sum(1 for k in step_keys if st.session_state.get(k, False))

    if n:
        st.progress(done / n)
        st.caption(f"{done} / {n} steps completed")

    si = 0
    for kind, content in items:
        if kind == "header":
            st.markdown(f'<div class="sec-hdr">{content}</div>', unsafe_allow_html=True)
        elif kind == "step":
            st.checkbox(content, key=step_keys[si])
            si += 1
        else:
            st.markdown(f"<small>{content}</small>", unsafe_allow_html=True)


# ── session defaults ──────────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "token":           None,
    "username":        "",
    "page":            "home",
    "gallery_pid":     None,
    "detail_pid":      None,
    "diag_pid":        None,
    "diag_thread":     None,
    "diag_questions":  [],
    "diag_diagnosis":  {},
    "diag_plant_pid":  None,
    "care_plan_text":  "",
    "care_plan_pfx":   "",
    "ck_pid":          None,
    "ck_thread":       None,
    "ck_prev_image":   None,
    "ck_result":       None,
}
for k, v in _DEFAULTS.items():
    st.session_state.setdefault(k, v)

def _jwt_username(token: str) -> str:
    """Decode the username from the JWT payload without verifying the signature."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # fix padding
        payload = json.loads(base64.b64decode(payload_b64))
        return payload.get("sub", "")
    except Exception:
        return ""

# Restore token from cookie on first load
if not st.session_state.token and not st.session_state.get("logout_pending"):
    _saved_token = _cm.get("pd_token")
    if _saved_token:
        st.session_state.token    = _saved_token
        st.session_state.username = _jwt_username(_saved_token)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH GATE
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.token:
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("## 🌿 Plant Doctor")
        st.markdown("AI-powered plant diagnosis & personalised care plans.")
        st.divider()
        tab_li, tab_su = st.tabs(["Login", "Create Account"])

        with tab_li:
            u = st.text_input("Username", key="li_u")
            p = st.text_input("Password", type="password", key="li_p")
            if st.button("Login", use_container_width=True, type="primary"):
                r = requests.post(f"{API}/auth/login",
                                  data={"username": u, "password": p}, timeout=10)
                if r.ok:
                    tok = r.json()["access_token"]
                    st.session_state.token          = tok
                    st.session_state.username       = u
                    st.session_state.page           = "home"
                    st.session_state["logout_pending"] = False
                    _cm.set("pd_token", tok, max_age=86400)
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Login failed"))

        with tab_su:
            ru       = st.text_input("Username", key="su_u")
            re_email = st.text_input("Email",    key="su_e")
            rp       = st.text_input("Password", type="password", key="su_p")
            if st.button("Create Account", use_container_width=True, type="primary"):
                r = requests.post(f"{API}/auth/register",
                                  json={"username": ru, "email": re_email, "password": rp},
                                  timeout=10)
                if r.ok:
                    st.success("Account created! Please log in.")
                else:
                    st.error(r.json().get("detail", "Registration failed"))
    st.stop()


# ── shared data ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _load_plants(token: str) -> list[dict]:
    try:
        r = requests.get(f"{API}/plants/", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return r.json() if r.ok else []
    except requests.exceptions.RequestException:
        return []

@st.cache_data(ttl=120, show_spinner=False)
def _load_history(token: str) -> list[dict]:
    try:
        r = requests.get(f"{API}/diagnose/history", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return r.json() if r.ok else []
    except requests.exceptions.RequestException:
        return []

def _latest_diag(history: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for d in history:
        pid = d.get("plant_id")
        if pid is not None and pid not in out:
            out[pid] = d
    return out


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🌿 Plant Doctor")
    st.markdown(f"<small>Signed in as <b>{st.session_state.username}</b></small>",
                unsafe_allow_html=True)
    st.divider()

    NAV = [
        ("🏠  Home",             "home"),
        ("🌿  My Plants",        "plants"),
        ("➕  Add Plant",        "add_plant"),
        ("📷  7-Day Check-In",   "checkin"),
        ("📚  Knowledge Base",   "knowledge"),
    ]
    for nav_label, nav_key in NAV:
        is_active = st.session_state.page == nav_key
        if st.button(nav_label, use_container_width=True,
                     type="primary" if is_active else "secondary",
                     key=f"nav_{nav_key}"):
            st.session_state.page = nav_key
            st.rerun()

    # ── plant mini-list ───────────────────────────────────────────────────────
    plants_sb = _load_plants(st.session_state.token)
    if plants_sb:
        st.divider()
        st.markdown(
            '<p style="font-size:.72rem;opacity:.6;margin:0 0 4px;letter-spacing:.06em">YOUR PLANTS</p>',
            unsafe_allow_html=True,
        )
        for _p in plants_sb[:8]:
            if st.button(f"🌿  {_p['name']}", key=f"sb_p_{_p['id']}",
                         use_container_width=True):
                st.session_state.detail_pid = _p["id"]
                st.session_state.page       = "plant_detail"
                st.rerun()

    st.divider()
    if st.button("Logout", use_container_width=True):
        _cm.set("pd_token", "", max_age=1)
        for k, v in _DEFAULTS.items():
            st.session_state[k] = v
        st.session_state["logout_pending"] = True
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.page == "home":
    st.markdown(f"## Welcome back, {st.session_state.username}! 👋")
    st.markdown("Here's a quick overview of your garden.")
    st.divider()

    plants  = _load_plants(st.session_state.token)
    history = _load_history(st.session_state.token)
    latest  = _latest_diag(history)

    n_critical   = sum(1 for p in plants if _status(latest.get(p["id"], {}).get("result"))[0] == "Critical")
    n_recovering = sum(1 for p in plants if _status(latest.get(p["id"], {}).get("result"))[0] == "Recovering")
    n_healthy    = sum(1 for p in plants if _status(latest.get(p["id"], {}).get("result"))[0] == "Healthy")

    s1, s2, s3, s4 = st.columns(4)
    for col, num, lbl, color in [
        (s1, len(plants),  "Total Plants",   "#15803d"),
        (s2, n_healthy,    "Healthy",         "#22c55e"),
        (s3, n_recovering, "Recovering",      "#f97316"),
        (s4, n_critical,   "Need Attention",  "#ef4444"),
    ]:
        col.markdown(
            f'<div class="stat-box">'
            f'<div class="stat-num" style="color:{color}">{num}</div>'
            f'<div class="stat-lbl">{lbl}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("#### Recent Diagnoses")
    if history:
        for d in history[:6]:
            ts    = d.get("created_at", "")[:16].replace("T", " ")
            pid   = d.get("plant_id")
            pname = next((p["name"] for p in plants if p["id"] == pid), f"Plant #{pid}")
            label, color = _status(d.get("result"))
            st.markdown(
                f'<div class="rd-row">'
                f'<span class="rd-ts">{ts}</span>'
                f'<span class="rd-name">{pname}</span>'
                f'<span class="badge" style="background:{color}">{label}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("No diagnoses yet. Upload a photo to get started.")

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("View My Plants", use_container_width=True, type="primary"):
        st.session_state.page = "plants"
        st.rerun()
    if c2.button("Add a New Plant", use_container_width=True):
        st.session_state.page = "add_plant"
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MY PLANTS
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "plants":
    st.markdown("## My Plants")

    plants  = _load_plants(st.session_state.token)
    history = _load_history(st.session_state.token)
    latest  = _latest_diag(history)

    if not plants:
        st.info("No plants yet.")
        if st.button("Add your first plant"):
            st.session_state.page = "add_plant"
            st.rerun()
        st.stop()

    cols = st.columns(3, gap="medium")
    for i, plant in enumerate(plants):
        pid   = plant["id"]
        diag  = latest.get(pid)
        issue = diag.get("result") if diag else None
        label, color = _status(issue)

        with cols[i % 3]:
            # ── card with colored left border ─────────────────────────────────
            st.markdown(
                f'<div class="pcard" style="border-left-color:{color}">'
                f'  <div class="pcard-body">'
                f'    <p class="pcard-name">{plant["name"]}</p>'
                f'    <p class="pcard-species">{plant.get("species") or "Species unknown"}</p>'
                f'    {badge_html(issue, animate=True)}'
                f'    <p class="pcard-date">Added {plant.get("created_at","")[:10]}</p>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # latest photo thumbnail
            thumb = img_url(diag["image_path"]) if diag and diag.get("image_path") else None
            if thumb:
                st.image(thumb, use_container_width=True)
            else:
                st.markdown(
                    '<div class="upload-ph" style="padding:1.2rem;font-size:2.2rem">🌱</div>',
                    unsafe_allow_html=True,
                )

            # buttons
            b1, b2 = st.columns(2)
            if b1.button("View", key=f"vw_{pid}", use_container_width=True, type="primary"):
                st.session_state.detail_pid = pid
                st.session_state.page       = "plant_detail"
                st.rerun()
            if b2.button("Diagnose", key=f"dx_{pid}", use_container_width=True):
                st.session_state.diag_pid = pid
                st.session_state.page     = "diagnose"
                for k in ("diag_thread","diag_questions","diag_diagnosis","care_plan_text","care_plan_pfx"):
                    st.session_state[k] = _DEFAULTS[k]
                _refresh()
                st.rerun()

            if st.button("Weekly Check-In", key=f"ck_{pid}", use_container_width=True):
                st.session_state.ck_pid             = pid
                st.session_state.ck_thread          = None
                st.session_state.ck_prev_image      = None
                st.session_state.ck_result          = None
                st.session_state["_ck_fetched_pid"] = None
                st.session_state.page               = "checkin"
                st.rerun()

            # inline gallery
            if st.button("Gallery", key=f"gal_{pid}", use_container_width=True):
                st.session_state.gallery_pid = (
                    None if st.session_state.gallery_pid == pid else pid
                )
                st.rerun()

            if st.session_state.get(f"confirm_del_{pid}"):
                st.warning(f"Remove **{plant['name']}**? This cannot be undone.")
                cd1, cd2 = st.columns(2)
                if cd1.button("Yes, remove", key=f"del_yes_{pid}", use_container_width=True):
                    r_del = requests.delete(f"{API}/plants/{pid}", headers=_h(), timeout=10)
                    if r_del.ok:
                        st.session_state[f"confirm_del_{pid}"] = False
                        _refresh()
                        st.rerun()
                    else:
                        st.error(_err(r_del, "Failed to remove plant."))
                if cd2.button("Cancel", key=f"del_no_{pid}", use_container_width=True):
                    st.session_state[f"confirm_del_{pid}"] = False
                    st.rerun()
            else:
                if st.button("Remove Plant", key=f"del_{pid}", use_container_width=True):
                    st.session_state[f"confirm_del_{pid}"] = True
                    st.rerun()

            if st.session_state.gallery_pid == pid:
                plant_diags = [d for d in history if d.get("plant_id") == pid and d.get("image_path")]
                if not plant_diags:
                    st.caption("No photos yet. Run a diagnosis to add photos.")
                else:
                    st.markdown('<div class="sec-hdr">Photo Timeline</div>', unsafe_allow_html=True)
                    gcols = st.columns(3)
                    for j, d in enumerate(reversed(plant_diags)):
                        url = img_url(d["image_path"])
                        ts  = d.get("created_at", "")[:10]
                        with gcols[j % 3]:
                            if url:
                                st.image(url, use_container_width=True)
                            st.markdown(f'<p class="gcap">{ts}</p>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PLANT DETAIL
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "plant_detail":
    plants  = _load_plants(st.session_state.token)
    history = _load_history(st.session_state.token)
    latest  = _latest_diag(history)

    pid   = st.session_state.detail_pid
    plant = next((p for p in plants if p["id"] == pid), None)

    if not plant:
        st.error("Plant not found.")
        if st.button("Back to My Plants"):
            st.session_state.page = "plants"
            st.rerun()
        st.stop()

    diag  = latest.get(pid)
    issue = diag.get("result") if diag else None
    label, color = _status(issue)

    # ── hero banner ───────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="hero">'
        f'  <p class="hero-name">{plant["name"]}</p>'
        f'  <p class="hero-species">{plant.get("species") or "Species unknown"}</p>'
        f'  {badge_html(issue, animate=True)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    col_photo, col_info = st.columns([1, 1], gap="large")

    # ── left: latest photo ────────────────────────────────────────────────────
    with col_photo:
        st.markdown("#### Latest Photo")
        thumb = img_url(diag["image_path"]) if diag and diag.get("image_path") else None
        if thumb:
            st.image(thumb, use_container_width=True)
        else:
            st.markdown(
                '<div class="upload-ph">🌱<br><small>No photo yet</small></div>',
                unsafe_allow_html=True,
            )

        st.markdown("")
        b1, b2, b3 = st.columns(3)
        if b1.button("Diagnose", key="det_dx", use_container_width=True, type="primary"):
            st.session_state.diag_pid = pid
            st.session_state.page     = "diagnose"
            for k in ("diag_thread","diag_questions","diag_diagnosis","care_plan_text","care_plan_pfx"):
                st.session_state[k] = _DEFAULTS[k]
            _refresh()
            st.rerun()
        if b2.button("Check-In", key="det_ck", use_container_width=True):
            st.session_state.ck_pid             = pid
            st.session_state.ck_thread          = None
            st.session_state.ck_prev_image      = None
            st.session_state.ck_result          = None
            st.session_state["_ck_fetched_pid"] = None
            st.session_state.page               = "checkin"
            st.rerun()
        if b3.button("← Plants", key="det_back", use_container_width=True):
            st.session_state.page = "plants"
            st.rerun()

        st.markdown("")
        if st.session_state.get("confirm_del_detail"):
            st.warning(f"Remove **{plant['name']}**? This cannot be undone.")
            dd1, dd2 = st.columns(2)
            if dd1.button("Yes, remove", key="det_del_yes", use_container_width=True):
                r_del = requests.delete(f"{API}/plants/{pid}", headers=_h(), timeout=10)
                if r_del.ok:
                    st.session_state["confirm_del_detail"] = False
                    st.session_state.detail_pid = None
                    _refresh()
                    st.session_state.page = "plants"
                    st.rerun()
                else:
                    st.error(_err(r_del, "Failed to remove plant."))
            if dd2.button("Cancel", key="det_del_no", use_container_width=True):
                st.session_state["confirm_del_detail"] = False
                st.rerun()
        else:
            if st.button("Remove Plant", key="det_del", use_container_width=True):
                st.session_state["confirm_del_detail"] = True
                st.rerun()

    # ── right: diagnosis history timeline ─────────────────────────────────────
    with col_info:
        st.markdown("#### Diagnosis History")
        plant_history = [d for d in history if d.get("plant_id") == pid]
        if plant_history:
            for d in plant_history[:8]:
                ts        = d.get("created_at", "")[:10]
                lbl, col  = _status(d.get("result"))
                conf      = d.get("confidence")
                conf_html = (
                    f'<br><small style="color:#9ca3af">conf {conf:.0%}</small>'
                    if isinstance(conf, (int, float)) and conf > 0 else ""
                )
                st.markdown(
                    f'<div class="tl-row">'
                    f'<div class="tl-dot" style="background:{col}"></div>'
                    f'<span class="tl-date">{ts}</span>'
                    f'<span class="tl-text">{lbl}{conf_html}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No diagnoses yet.")

    # ── care plan ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Current Care Plan")
    r_cp = _get(f"/diagnose/{pid}/latest-care-plan")
    if r_cp.ok:
        cp = r_cp.json()
        render_care_plan(cp["content"], f"cp_{cp['id']}")
    elif r_cp.status_code == 404:
        st.info("Run a diagnosis and complete the care plan to see it here.")
    else:
        st.error(_err(r_cp, "Failed to load care plan."))


# ══════════════════════════════════════════════════════════════════════════════
# ADD PLANT
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "add_plant":
    st.markdown("## Add a New Plant")
    st.markdown("Fill in the details below. You can add more after diagnosis.")

    with st.form("add_plant_form", clear_on_submit=True):
        name    = st.text_input("Plant name *", placeholder="e.g. My Monstera")
        species = st.text_input("Species (optional)", placeholder="e.g. Monstera deliciosa")
        st.caption("Species helps the AI give more accurate diagnoses.")
        submitted = st.form_submit_button("Add Plant", type="primary", use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("Plant name is required.")
        else:
            r = _post("/plants/", json={"name": name.strip(), "species": species.strip() or None})
            if r.ok:
                _refresh()
                st.session_state.page = "plants"
                st.rerun()
            else:
                st.error(_err(r, "Failed to add plant."))


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNOSE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "diagnose":
    st.markdown("## Diagnose a Plant")

    plants = _load_plants(st.session_state.token)
    if not plants:
        st.warning("Add a plant first.")
        st.stop()

    plant_map   = {p["name"]: p for p in plants}
    presel_name = next(
        (p["name"] for p in plants if p["id"] == st.session_state.diag_pid),
        list(plant_map)[0],
    )

    # ── step 1: upload ────────────────────────────────────────────────────────
    if not st.session_state.diag_thread:
        st.markdown('<span class="step-pill">Step 1 of 3 — Upload Photo</span>',
                    unsafe_allow_html=True)

        chosen_name  = st.selectbox("Plant", list(plant_map),
                                    index=list(plant_map).index(presel_name))
        chosen       = plant_map[chosen_name]
        species_hint = st.text_input("Species hint", value=chosen.get("species") or "",
                                     help="Leave blank to auto-detect from photo.")

        up_col, prev_col = st.columns([1, 1], gap="large")
        with up_col:
            uploaded = st.file_uploader("Upload photo", type=["jpg","jpeg","png","webp"])
        with prev_col:
            if uploaded:
                st.image(uploaded, caption="Preview", use_container_width=True)
            else:
                st.markdown('<div class="upload-ph">📷<br><small>Preview</small></div>',
                            unsafe_allow_html=True)

        user_context = st.text_area(
            "Extra info from Reddit / Google (optional)",
            height=120,
            placeholder=(
                "Paste anything helpful — a Reddit thread, care guide excerpt, "
                "or your own notes. The AI will use it when writing your care plan."
            ),
        )

        if st.button("Start Diagnosis", type="primary",
                     disabled=uploaded is None, use_container_width=True):
            try:
                with st.spinner("Identifying species and diagnosing..."):
                    _form_data = {"species": species_hint} if species_hint else {}
                    if user_context.strip():
                        _form_data["user_context"] = user_context.strip()
                    r = requests.post(
                        f"{API}/diagnose/{chosen['id']}",
                        files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                        data=_form_data,
                        headers=_h(), timeout=90,
                    )
            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach the server: {e}")
                st.stop()
            _refresh()
            if r.ok:
                data = r.json()
                st.session_state.diag_thread    = data["thread_id"]
                st.session_state.diag_questions = data["questions"]
                st.session_state.diag_diagnosis = data["diagnosis"]
                st.session_state.diag_plant_pid = chosen["id"]
                if data.get("completed"):
                    # High-confidence direct path: graph already prescribed,
                    # skip Q&A and jump straight to step 3.
                    st.session_state.care_plan_text = data["care_plan"]
                    st.session_state.care_plan_pfx  = f"cp_{data['care_plan_id']}"
                st.rerun()
            else:
                st.error(_err(r, "Diagnosis failed."))

    # ── step 2: questions ─────────────────────────────────────────────────────
    elif not st.session_state.care_plan_text:
        st.markdown('<span class="step-pill">Step 2 of 3 — Clarify (needed for accurate care plan)</span>',
                    unsafe_allow_html=True)

        diag  = st.session_state.diag_diagnosis
        issue = diag.get("issue_category")
        label, color = _status(issue)

        d1, d2 = st.columns(2)
        d1.markdown(
            f'<div class="stat-box">'
            f'<div class="stat-num" style="font-size:1.3rem;color:{color}">{issue or "—"}</div>'
            f'<div class="stat-lbl">Issue Detected</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        d2.markdown(
            f'<div class="stat-box">'
            f'<div class="stat-num" style="font-size:1.3rem;color:#15803d">'
            f'{diag.get("confidence", 0):.0%}</div>'
            f'<div class="stat-lbl">Confidence</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown("")
        st.markdown(
            f'**Diagnosis:** {badge_html(issue, animate=True)} '
            f'&nbsp; **Species:** {diag.get("species") or "Unknown"}',
            unsafe_allow_html=True,
        )

        if diag.get("symptoms"):
            st.markdown("**Observed symptoms**")
            for s in diag["symptoms"]:
                st.markdown(f"- {s}")

        if diag.get("evidence"):
            st.caption(f"Evidence: {diag['evidence']}")

        st.divider()
        st.markdown("### Clarifying Questions")
        st.caption("Answer these so the AI can write a personalised care plan.")
        for i, q in enumerate(st.session_state.diag_questions, 1):
            st.markdown(f"**{i}.** {q}")

        answers = st.text_area("Your answers", height=140,
                               placeholder="Answer each question in free text or numbered lines.")

        ca, cb = st.columns([3, 1])
        if ca.button("Get My Care Plan", type="primary",
                     disabled=not answers.strip(), use_container_width=True):
            try:
                with st.spinner("Writing your personalised care plan..."):
                    r = _post(
                        f"/diagnose/{st.session_state.diag_plant_pid}/resume",
                        json={"thread_id": st.session_state.diag_thread, "answers": answers},
                    )
            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach the server: {e}")
                st.stop()
            _refresh()
            if r.ok:
                data = r.json()
                st.session_state.care_plan_text = data["care_plan"]
                st.session_state.care_plan_pfx  = f"cp_{data['care_plan_id']}"
                st.rerun()
            else:
                st.error(_err(r, "Failed to generate care plan."))

        if cb.button("Start over", use_container_width=True):
            for k in ("diag_thread","diag_questions","diag_diagnosis","care_plan_text","care_plan_pfx"):
                st.session_state[k] = _DEFAULTS[k]
            st.rerun()

    # ── step 3: care plan ─────────────────────────────────────────────────────
    else:
        st.markdown('<span class="step-pill">Step 3 of 3 — Your Care Plan</span>',
                    unsafe_allow_html=True)
        st.markdown("### Your Care Plan")
        st.caption("Check off each step as you complete it.")
        st.divider()
        render_care_plan(st.session_state.care_plan_text, st.session_state.care_plan_pfx)
        st.divider()

        c1, c2, c3 = st.columns(3)
        if c1.button("7-Day Check-In", use_container_width=True, type="primary"):
            st.session_state.ck_pid             = st.session_state.diag_plant_pid
            st.session_state.ck_thread          = st.session_state.diag_thread
            st.session_state.ck_result          = None
            st.session_state["_ck_fetched_pid"] = None
            st.session_state.page               = "checkin"
            st.rerun()
        if c2.button("Diagnose another", use_container_width=True):
            for k in ("diag_thread","diag_questions","diag_diagnosis","care_plan_text","care_plan_pfx","diag_pid"):
                st.session_state[k] = _DEFAULTS[k]
            st.session_state.page = "diagnose"
            st.rerun()
        if c3.button("My Plants", use_container_width=True):
            for k in ("diag_thread","diag_questions","diag_diagnosis","care_plan_text","care_plan_pfx","diag_pid"):
                st.session_state[k] = _DEFAULTS[k]
            st.session_state.page = "plants"
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY CHECK-IN
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "checkin":
    st.markdown("## 📷 Weekly Check-In")
    st.caption("Upload a fresh photo — the AI compares it with the original and updates your care plan.")
    st.divider()

    plants    = _load_plants(st.session_state.token)
    plant_map = {p["name"]: p for p in plants}

    if not plants:
        st.warning("Add a plant first.")
        st.stop()

    if not st.session_state.ck_result:
        # plant selector
        presel = next(
            (p["name"] for p in plants if p["id"] == st.session_state.ck_pid),
            list(plant_map)[0] if plant_map else None,
        )
        chosen_name = st.selectbox(
            "Which plant are you checking in?",
            list(plant_map),
            index=list(plant_map).index(presel) if presel and presel in plant_map else 0,
        )
        chosen = plant_map.get(chosen_name, {})

        # auto-fetch thread + previous image
        if chosen and chosen.get("id") != st.session_state.get("_ck_fetched_pid"):
            try:
                with st.spinner("Fetching previous diagnosis..."):
                    r_lt = _get(f"/diagnose/{chosen['id']}/latest-thread")
            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach the server: {e}")
                r_lt = None
            if r_lt is not None and r_lt.ok:
                lt = r_lt.json()
                st.session_state.ck_thread     = lt["thread_id"]
                st.session_state.ck_prev_image = lt["image_path"]
            else:
                st.session_state.ck_thread     = None
                st.session_state.ck_prev_image = None
                if r_lt is not None and r_lt.status_code != 404:
                    st.error(_err(r_lt, "Failed to load previous diagnosis."))
            st.session_state["_ck_fetched_pid"] = chosen.get("id")

        thread_id = st.session_state.ck_thread or ""

        if thread_id:
            st.success(f"Previous diagnosis found — thread `{thread_id}`")
        else:
            st.warning("No completed diagnosis found. Run a diagnosis and complete the care plan first.")
            tid_override = st.text_input("Or paste a thread ID manually",
                                         placeholder="e.g. u1-p2-ab12cd34")
            if tid_override.strip():
                thread_id = tid_override.strip()

        st.divider()

        # side-by-side photos
        col_prev, col_arr, col_new = st.columns([5, 1, 5], gap="small")

        with col_prev:
            st.markdown("**Before — original photo**")
            prev_url = img_url(st.session_state.ck_prev_image or "")
            if prev_url:
                st.image(prev_url, use_container_width=True)
                st.caption("From your first diagnosis")
            else:
                st.markdown('<div class="upload-ph">🌱<br><small>No original</small></div>',
                            unsafe_allow_html=True)

        with col_arr:
            st.markdown('<div class="ck-arrow" style="height:100%;padding-top:2.5rem">→</div>',
                        unsafe_allow_html=True)

        with col_new:
            st.markdown("**After — new photo**")
            new_photo = st.file_uploader("Upload new photo", type=["jpg","jpeg","png","webp"],
                                         key="ck_uploader", label_visibility="collapsed")
            if new_photo:
                st.image(new_photo, use_container_width=True)
                st.caption("Taken today")
            else:
                st.markdown('<div class="upload-ph">📷<br><small>Upload now</small></div>',
                            unsafe_allow_html=True)

        st.divider()

        can_submit = bool(thread_id and new_photo and chosen)
        if not new_photo:
            st.info("Upload today's photo to enable comparison.")

        if st.button("Compare & Update Care Plan", type="primary",
                     disabled=not can_submit, use_container_width=True):
            try:
                with st.spinner("Comparing before and after photos — this takes ~30 seconds..."):
                    r = requests.post(
                        f"{API}/diagnose/{chosen['id']}/checkin",
                        files={"file": (new_photo.name, new_photo.getvalue(), new_photo.type)},
                        data={"thread_id": thread_id},
                        headers=_h(), timeout=120,
                    )
            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach the server: {e}")
                st.stop()
            _refresh()
            if r.ok:
                st.session_state.ck_result = r.json()
                st.session_state.ck_pid    = chosen["id"]
                st.session_state.ck_thread = thread_id
                st.rerun()
            else:
                st.error(_err(r, "Check-in failed."))

    else:
        # ── results ───────────────────────────────────────────────────────────
        result   = st.session_state.ck_result
        progress = result.get("progress", "unknown")
        changes  = result.get("changes", [])
        plan     = result.get("updated_care_plan", "")

        prog_color = _PROG_COLORS.get(progress, "#9ca3af")
        prog_label = _PROG_LABELS.get(progress, progress.capitalize())

        # progress hero
        st.markdown(
            f'<div class="hero" style="background:linear-gradient(135deg,{prog_color}cc,{prog_color})">'
            f'<p class="hero-name">{prog_label}</p>'
            f'<p class="hero-species">Plant progress after 7 days</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # before / after with arrow
        orig_url = img_url(result.get("original_image_path", ""))
        new_url  = img_url(result.get("new_image_path", ""))

        if orig_url or new_url:
            st.markdown("#### Before & After")
            c_b, c_arr, c_a = st.columns([5, 1, 5], gap="small")
            with c_b:
                st.markdown("**Before**")
                if orig_url:
                    st.image(orig_url, use_container_width=True)
                    st.caption("Original diagnosis")
            with c_arr:
                st.markdown(
                    f'<div class="ck-arrow" style="color:{prog_color};padding-top:2.5rem">→</div>',
                    unsafe_allow_html=True,
                )
            with c_a:
                st.markdown("**After (7 days)**")
                if new_url:
                    st.image(new_url, use_container_width=True)
                    st.caption("Latest photo")
            st.divider()

        # what changed — as tags
        if changes:
            st.markdown("#### What the AI Observed")
            tags = "".join(f'<span class="ch-tag">{ch}</span>' for ch in changes)
            st.markdown(tags, unsafe_allow_html=True)
            st.divider()

        # updated care plan
        st.markdown("#### Updated Care Plan")
        st.caption("Revised to reflect your plant's current condition.")
        render_care_plan(plan, f"ck_{result.get('care_plan_id', 0)}")
        st.divider()

        c1, c2 = st.columns(2)
        if c1.button("Do another check-in", use_container_width=True):
            st.session_state.ck_result          = None
            st.session_state["_ck_fetched_pid"] = None
            st.rerun()
        if c2.button("Back to My Plants", use_container_width=True, type="primary"):
            st.session_state.ck_result          = None
            st.session_state["_ck_fetched_pid"] = None
            st.session_state.page               = "plants"
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "knowledge":
    st.markdown("## 📚 Knowledge Base")
    st.caption(
        "Paste plant-care text from any source (Reddit, UC IPM, care guides). "
        "The AI will cite it when writing care plans."
    )
    st.divider()

    tab_add, tab_manage = st.tabs(["Add Knowledge", "Manage Sources"])

    # ── add ───────────────────────────────────────────────────────────────────
    with tab_add:
        with st.form("kb_add_form", clear_on_submit=True):
            kb_source = st.text_input(
                "Source name *",
                placeholder="e.g. UC IPM — Spider Mites, Reddit r/houseplants",
            )
            kb_topic = st.text_input(
                "Topic (optional)",
                placeholder="e.g. pest control, overwatering, Monstera care",
            )
            kb_text = st.text_area(
                "Paste content *",
                height=260,
                placeholder="Paste the full text here. Paragraphs are automatically split into searchable chunks.",
            )
            submitted = st.form_submit_button("Add to Knowledge Base", type="primary", use_container_width=True)

        if submitted:
            if not kb_source.strip():
                st.error("Source name is required.")
            elif not kb_text.strip():
                st.error("Content cannot be empty.")
            else:
                with st.spinner("Chunking and embedding…"):
                    r = _post("/knowledge/ingest", json={
                        "text":   kb_text.strip(),
                        "source": kb_source.strip(),
                        "topic":  kb_topic.strip(),
                    })
                if r.ok:
                    n = r.json().get("chunks_stored", 0)
                    st.success(f"Added **{n}** chunks from *{kb_source}* to the knowledge base.")
                else:
                    st.error(_err(r, "Failed to ingest content."))

    # ── manage ────────────────────────────────────────────────────────────────
    with tab_manage:
        r_src = _get("/knowledge/sources")
        if r_src.ok:
            sources = r_src.json()
            if not sources:
                st.info("No sources yet. Add some in the 'Add Knowledge' tab.")
            else:
                st.markdown(f"**{len(sources)} source(s)** in the knowledge base:")
                for src in sources:
                    col_info, col_del = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f'<div class="pcard-body">'
                            f'<p class="pcard-name">{src["source"]}</p>'
                            f'<p class="pcard-species">{src["topic"] or "No topic"} &nbsp;·&nbsp; '
                            f'{src["chunks"]} chunk(s)</p>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with col_del:
                        if st.button("🗑", key=f"del_{src['source']}", help="Delete this source"):
                            r_del = requests.delete(
                                f"{API}/knowledge/sources/{src['source']}",
                                headers=_h(), timeout=10,
                            )
                            if r_del.ok:
                                st.success(f"Deleted *{src['source']}*.")
                                st.rerun()
                            else:
                                st.error(_err(r_del, "Delete failed."))
        else:
            st.error(_err(r_src, "Could not load sources."))
