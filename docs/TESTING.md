# Testing — BENEFITBRIDGE AI

BENEFITBRIDGE AI is now a health and family support navigator, not the old New Jersey benefits-program demo.

The app uses:

- Facility data
- India Post PIN code geography
- PIN-to-district lookup
- NFHS-5 district health indicators
- Support pathways

Current trusted Unity Catalog source:

```text
Catalog: benefits_navigator
Schema: trusted
```

Expected Unity Catalog tables:

```text
benefits_navigator.trusted.facilities
benefits_navigator.trusted.india_post_pincode_directory
benefits_navigator.trusted.pincode_district_lookup
benefits_navigator.trusted.nfhs_5_district_health_indicators
benefits_navigator.trusted.support_pathways
```

Local Gate A uses exported JSON files from `sample_data/`.

---

## Main demo scenario

Use this intake text:

```text
I live in pincode 560001. I am pregnant and have a 3-year-old child. I do not know where to go for affordable health services. I need help with nutrition, vaccination, and finding a nearby facility.
```

Expected result:

- PIN `560001` resolves to `BENGALURU URBAN / KARNATAKA`.
- NFHS district context resolves through alias handling to `Bangalore / Karnataka`, or uses state fallback if needed.
- Relevant support pathways appear.
- Maternal Health Support and Child Nutrition Support should match.
- Health Insurance Awareness may match if the profile indicates uninsured, low-income, or affordable-care need.
- Women Preventive Screening should be lower-priority unless the user specifically asks for screening.
- Facilities from Karnataka/Bengaluru sample data appear.
- An action plan is generated.
- The plan should be cautious and grounded.
- The plan should not invent unsupported programs, benefits, or guaranteed eligibility.
- The local session saves to SQLite.

Important: if the child is interpreted as exactly 36 months old, Child Immunization Support may not match because the rule is `child_age_months BETWEEN 0 AND 35`. That is acceptable and explainable.

---

## Test gates

Run the gates in order.

| Gate | Data source | State store | Purpose |
|---|---|---|---|
| Gate A | Local sample JSON | SQLite | Prove the app works fully offline/local |
| Gate B | Unity Catalog trusted tables | SQLite | Prove trusted Databricks data works locally |
| Gate C | Unity Catalog trusted tables | Lakebase | Final deployed Databricks App path |

---

## Gate A — Local JSON + SQLite

Purpose: prove the app works even if Databricks and Lakebase are unavailable during the demo.

Run from:

```powershell
cd C:\Hackathon\benefits-navigator-hackathon
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Set local environment variables:

```powershell
$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="json_only"
$env:BENEFITS_DATA_MODE="json_only"

$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SAMPLE_DATA_DIR="sample_data"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"

$env:SHOW_LOCAL_STATE_DEBUG="true"
```

Validate sample files:

```powershell
Get-ChildItem .\sample_data\*.json

python -c "import json,glob; [print(f, len(json.load(open(f,encoding='utf-8')))) for f in glob.glob('sample_data/*.json')]"
```

Expected files:

```text
sample_data/facilities.json
sample_data/india_post_pincode_directory.json
sample_data/pincode_district_lookup.json
sample_data/nfhs_5_district_health_indicators.json
sample_data/support_pathways.json
sample_data/sample_scenarios.json
```

Run compile and tests:

```powershell
python -m compileall .
python -m pytest tests -q
```

Expected:

```text
36 passed
```

Launch the app:

```powershell
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

Expected UI badges near the app header:

```text
Data source: Local sample JSON (Gate A)
State: Local SQLite fallback
AI: Claude Sonnet
```

Expected Family Navigator behavior:

- The demo scenario runs end-to-end.
- The app shows matched support pathways.
- The app shows district health indicators.
- The app shows nearby health facilities.
- The app generates an action plan.
- The app saves the session to SQLite.
- The app does not require Unity Catalog or Lakebase.

Expected Data Trust / Debug behavior:

- Shows local JSON row counts.
- Shows `json_only` data mode.
- Shows SQLite state mode.
- Shows Anthropic key status without printing the key.
- Shows district matching trace for `560001`.
- Shows recent SQLite session after the first run.

SQLite validation:

```powershell
Get-ChildItem .\.local_state\

python -c "import sqlite3; db='.local_state/benefitbridge_local.db'; con=sqlite3.connect(db); print(con.execute('select name from sqlite_master where type=''table''').fetchall()); con.close()"
```

Expected:

- `.local_state/benefitbridge_local.db` exists.
- At least one app-state table exists.
- Recent session appears in the Debug tab.

---

## Gate A fallback test — no Anthropic key

Stop Streamlit with `Ctrl + C`.

Remove the Anthropic key:

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
```

Relaunch:

```powershell
streamlit run app.py
```

Run the same demo scenario.

Expected:

- App does not crash.
- Deterministic fallback action plan appears.
- SQLite save still works.
- Debug panel shows Anthropic key is missing without exposing secrets.

---

## Gate B — Unity Catalog trusted data + SQLite

Purpose: prove the app can run locally against trusted Unity Catalog data while still using SQLite for local state.

Set environment variables:

```powershell
$env:DATABRICKS_CONFIG_PROFILE="hackathon-free"
$env:DATABRICKS_HOST="https://dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_SERVER_HOSTNAME="dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/81c2d8e2b863208b"
$env:DATABRICKS_TOKEN="<your_databricks_token>"

$env:UC_CATALOG="benefits_navigator"
$env:UC_SCHEMA="trusted"
$env:SQL_WAREHOUSE_NAME="Serverless Starter"

$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="uc"
$env:BENEFITS_DATA_MODE="uc"
$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"
$env:SHOW_LOCAL_STATE_DEBUG="true"
```

Validate Unity Catalog access:

```powershell
databricks current-user me --profile hackathon-free
databricks catalogs list --profile hackathon-free
databricks schemas list benefits_navigator --profile hackathon-free
databricks tables list benefits_navigator trusted --profile hackathon-free
```

Expected tables:

```text
facilities
india_post_pincode_directory
pincode_district_lookup
nfhs_5_district_health_indicators
support_pathways
```

Optional SQL row-count validation:

```sql
SELECT COUNT(*) FROM benefits_navigator.trusted.facilities;
SELECT COUNT(*) FROM benefits_navigator.trusted.india_post_pincode_directory;
SELECT COUNT(*) FROM benefits_navigator.trusted.pincode_district_lookup;
SELECT COUNT(*) FROM benefits_navigator.trusted.nfhs_5_district_health_indicators;
SELECT COUNT(*) FROM benefits_navigator.trusted.support_pathways;
```

Launch:

```powershell
streamlit run app.py
```

Expected UI badges:

```text
Data source: Unity Catalog trusted tables
State: Local SQLite fallback
AI: Claude Sonnet
```

Expected result:

- Same main demo scenario works.
- Data source badge clearly says Unity Catalog.
- State still saves locally to SQLite.

---

## Gate C — Databricks App + Unity Catalog + Lakebase

Purpose: final hackathon path.

Expected UI badges:

```text
Data source: Unity Catalog trusted tables
State: Lakebase
AI: Claude Sonnet
```

Expected result:

- App opens at Databricks App URL.
- Family Navigator runs the main demo.
- Unity Catalog trusted data loads.
- Lakebase app-state save works.
- Program Leader Dashboard reflects saved activity.
- Feedback save works.
- No secrets appear in UI, logs, screenshots, or repo.

Lakebase validation examples:

```sql
SELECT COUNT(*) AS intake_count FROM family_intake_events;
SELECT COUNT(*) AS pathway_match_count FROM pathway_matches;
SELECT COUNT(*) AS facility_recommendation_count FROM facility_recommendations;
SELECT COUNT(*) AS plan_count FROM action_plans;
SELECT COUNT(*) AS feedback_count FROM user_feedback;
```

---

## What to screenshot for submission/demo

Capture:

- App title and source badge
- Family Navigator scenario input
- Resolved PIN and district/state
- Matched support pathway cards
- Action plan
- District health indicators
- Nearby facility recommendations
- Data Trust / Debug row counts
- SQLite recent session for Gate A
- Program Leader Dashboard
- Lakebase analytics for Gate C, if available

---

## Pass criteria

The app passes testing when:

- Data-source badge is visible and correct.
- State-store badge is visible and correct.
- Main demo scenario works end-to-end.
- District alias handling works for `BENGALURU URBAN` → `Bangalore`.
- Matches come from support pathways only.
- Facilities come from trusted data or approved local sample data only.
- Action plan avoids unsupported benefit/program claims.
- App does not claim diagnosis or guaranteed eligibility.
- SQLite save works locally.
- Lakebase save works in final deployed mode.
- Feedback save works.
- No secret/token/debug leakage appears in UI or logs.
