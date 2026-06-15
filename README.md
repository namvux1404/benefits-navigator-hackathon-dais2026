# 🧭 Benefits Navigator for Families — NJ

> **Databricks Apps & Agents for Good Hackathon**
> A conversational tool that helps New Jersey families discover and act on public
> benefit programs — fast, compassionately, and without bureaucratic jargon.

---

## What it does

1. A family describes their situation in plain language.
2. **Claude** extracts a structured profile and asks 2–3 clarifying questions.
3. A **deterministic rules engine** screens benefit programs (explainable, not a
   legal determination).
4. **Claude** writes a warm, grounded action plan from the matched programs only.
5. Intake, matches, plan, and feedback are persisted for analytics.

## Architecture

| Layer | Technology |
|---|---|
| UI / app host | Python **Streamlit** on **Databricks Apps** |
| AI reasoning | **Anthropic Claude** (direct API) |
| Eligibility | Deterministic rules engine (`benefits_rules.py`) |
| Trusted data | **Unity Catalog** Delta table via **Databricks SQL Warehouse** |
| App state (primary) | **Lakebase** (managed Postgres) |
| App state (fallback) | Local **SQLite** — development/demo only |

**Data sources degrade gracefully:** trusted Unity Catalog data loads first, falling
back to the bundled `sample_data/programs.json`. **App state** writes to Lakebase
first, falling back to SQLite. The UI always tells the user which path was used.

## Project layout

```
app.py                  Streamlit UI + orchestration
agent.py                Claude reasoning (profile, questions, action plan)
benefits_rules.py       Deterministic FPL screening engine
databricks_client.py    Read trusted programs from Unity Catalog (SQL Warehouse)
lakebase_client.py      Primary app-state writers (native Postgres password)
local_state_client.py   SQLite fallback writers
sample_data/programs.json   12 synthetic NJ programs (local fallback)
sql/                    Trusted table, Lakebase tables, grants, analytics
app.yaml.template       Databricks App deployment template (placeholders only)
docs/                   Architecture, setup, testing, demo, troubleshooting
```

## Run locally (Test A — JSON + SQLite)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:BENEFITS_DATA_MODE="json_only"
$env:SHOW_LOCAL_STATE_DEBUG="true"
streamlit run app.py
```

See [docs/SETUP.md](docs/SETUP.md) for Test B (Unity Catalog) and Test C (deployed
Databricks App + Lakebase).
