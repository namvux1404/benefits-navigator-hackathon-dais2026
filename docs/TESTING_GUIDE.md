# Simple Testing Guide — BENEFITBRIDGE AI

Use this guide for quick manual testing during the hackathon.

---

## Main demo scenario

Paste this into the Family Navigator:

```text
I live in pincode 560001. I am pregnant and have a 3-year-old child. I do not know where to go for affordable health services. I need help with nutrition, vaccination, and finding a nearby facility.
```

Expected:

- PIN `560001` resolves to `BENGALURU URBAN / KARNATAKA`.
- NFHS context finds `Bangalore / Karnataka` through alias matching.
- Maternal Health Support and Child Nutrition Support appear.
- Health Insurance Awareness may appear depending on profile extraction.
- Facilities from Bengaluru/Karnataka appear.
- An action plan is generated.
- Session saves successfully.

---

## Test A — Fully local fallback

Purpose: prove the app works even if Databricks and Lakebase are unavailable.

Setup:

```powershell
cd C:\Hackathon\benefits-navigator-hackathon
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="json_only"
$env:BENEFITS_DATA_MODE="json_only"

$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SAMPLE_DATA_DIR="sample_data"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"
$env:SHOW_LOCAL_STATE_DEBUG="true"
```

Run:

```powershell
python -m compileall .
python -m pytest tests -q
streamlit run app.py
```

Expected UI:

```text
Data source: Local sample JSON (Gate A)
State: Local SQLite fallback
AI: Claude Sonnet
```

Expected flow:

- Family Navigator works.
- Data Trust / Debug shows local JSON row counts.
- SQLite recent session appears after saving.
- Program Leader Dashboard reflects local sample and saved session.

SQLite check:

```powershell
Get-ChildItem .\.local_state\

python -c "import sqlite3; db='.local_state/benefitbridge_local.db'; con=sqlite3.connect(db); print(con.execute('select name from sqlite_master where type=''table''').fetchall()); con.close()"
```

---

## Test A fallback — no Claude key

Stop the app with `Ctrl + C`.

Remove the key:

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
streamlit run app.py
```

Expected:

- App still runs.
- Deterministic action plan fallback appears.
- SQLite save still works.
- No secret values are shown.

---

## Test B — Local app with Unity Catalog + SQLite

Purpose: prove trusted Databricks data works locally.

Setup:

```powershell
$env:DATABRICKS_CONFIG_PROFILE="hackathon-free"
$env:DATABRICKS_HOST="https://dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_SERVER_HOSTNAME="dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/81c2d8e2b863208b"
$env:DATABRICKS_TOKEN="<your_databricks_token>"

$env:UC_CATALOG="benefits_navigator"
$env:UC_SCHEMA="trusted"

$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="uc"
$env:BENEFITS_DATA_MODE="uc"
$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"
```

Validate tables:

```powershell
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

Run:

```powershell
streamlit run app.py
```

Expected UI:

```text
Data source: Unity Catalog trusted tables
State: Local SQLite fallback
AI: Claude Sonnet
```

---

## Test C — Databricks App + Unity Catalog + Lakebase

Purpose: final deployment path.

Expected UI:

```text
Data source: Unity Catalog trusted tables
State: Lakebase
AI: Claude Sonnet
```

Expected:

- App opens from Databricks App URL.
- Unity Catalog trusted data loads.
- Lakebase save works.
- Program Leader Dashboard updates.
- Feedback save works.
- No secrets appear.

Lakebase count checks:

```sql
SELECT COUNT(*) AS intake_count FROM family_intake_events;
SELECT COUNT(*) AS pathway_match_count FROM pathway_matches;
SELECT COUNT(*) AS facility_recommendation_count FROM facility_recommendations;
SELECT COUNT(*) AS plan_count FROM action_plans;
SELECT COUNT(*) AS feedback_count FROM user_feedback;
```

---

## Scenario set

Use these for extra testing.

### Scenario 1 — Main winning demo

```text
I live in pincode 560001. I am pregnant and have a 3-year-old child. I do not know where to go for affordable health services. I need help with nutrition, vaccination, and finding a nearby facility.
```

Expected:

- Maternal Health Support
- Child Nutrition Support
- Relevant Bengaluru/Karnataka facilities
- Bangalore NFHS context

### Scenario 2 — Child nutrition

```text
I live in pincode 560001. I have a 2-year-old child who needs nutrition and growth support. I want to find nearby healthcare help.
```

Expected:

- Child Nutrition Support
- Possibly Child Immunization Support
- Nearby facilities

### Scenario 3 — Missing location

```text
I am helping a mother with a young child who needs nutrition and vaccination support.
```

Expected:

- App asks for missing location or PIN code.
- App does not fake nearby facilities.
- App still extracts needs.

### Scenario 4 — Facility search only

```text
I live near pincode 560001 and need a nearby facility for pregnancy checkups.
```

Expected:

- Maternal Health Support
- Nearby facility recommendations
- No unsupported benefit claims

### Scenario 5 — Control test

```text
I live in pincode 560001. I do not have an urgent health need. I just want to understand what local health resources may exist near me.
```

Expected:

- Fewer urgent pathways
- Safe, general guidance
- No forced eligibility or crisis claims

---

## Pass criteria

Pass if:

- App launches.
- Source badge is clear.
- State badge is clear.
- Main scenario works.
- District alias matching works.
- Facilities display.
- Action plan is grounded.
- SQLite save works locally.
- App works without Claude key.
- Debug panel does not leak secrets.
- Tests pass.
