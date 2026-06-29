# Plant Doctor — Frontend

Streamlit single-page app that provides the user interface for Plant Doctor.

---

## Overview

The entire frontend lives in `frontend/app.py`. It communicates with the FastAPI backend via HTTP and renders all pages inside a single Streamlit session using `st.session_state` for navigation.

---

## Pages

| Page | What it does |
|---|---|
| **Login / Register** | Auth gate shown before anything else. Stores the JWT in a browser cookie so the user stays logged in on refresh. |
| **Home** | Dashboard — total plants, healthy / recovering / critical counts, and the six most recent diagnoses. |
| **My Plants** | Card grid of all plants with their latest status badge, photo thumbnail, and quick-action buttons. Includes a Remove Plant button with a two-step confirmation. Inline gallery expands to show the full photo timeline for each plant. |
| **Add Plant** | Simple form to register a new plant (name + optional species). |
| **Diagnose** | Three-step flow: upload photo → answer clarifying questions → read care plan. The care plan renders as a checklist with a progress bar. |
| **7-Day Check-In** | Side-by-side before/after photo comparison. The agent returns a progress label (Improving / Stable / Worsening) and an updated care plan. |
| **Knowledge Base** | Paste text from any source (Reddit, UC IPM, care guides). The backend chunks and embeds it so the agent can cite it in future care plans. |

---

## Running

From the project root:

```bash
cd frontend
streamlit run app.py
```

The frontend reads `API_BASE` from `.env` (defaults to `http://localhost:8000`). The backend must be running first.

---

## Key dependencies

| Package | Used for |
|---|---|
| `streamlit` | UI framework |
| `extra-streamlit-components` | Cookie manager (persistent login) |
| `requests` | HTTP calls to the backend |
| `python-dotenv` | Loading `.env` |

---

## Notes

- All CSS is injected via `st.markdown(..., unsafe_allow_html=True)` at the top of `app.py` — dark earthy theme with green accents.
- Data fetched from the API is cached with `@st.cache_data(ttl=120)` and invalidated after any write operation via `_refresh()`.
- Session state keys are defined in `_DEFAULTS` near the top of `app.py` — reset them there if you add a new page.
