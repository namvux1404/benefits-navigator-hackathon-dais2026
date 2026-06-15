# 🧭 BENEFITBRIDGE AI — Health & Family Support Navigator

> **Databricks Apps & Agents for Good Hackathon**
> An AI-powered public-health and family-support navigator that helps families, caregivers, and field workers understand local health context, find relevant facilities, and receive a clear action plan grounded in trusted data.

---

## What it does

1. A family or field worker describes a situation in plain language.
2. **Claude** extracts a structured profile and asks clarifying questions when needed.
3. The app resolves location using **India PIN code geography**.
4. The app enriches the situation with **NFHS-5 district-level health indicators**.
5. A **deterministic rules engine** matches the user to support pathways such as maternal care, child nutrition, immunization, health-insurance awareness, household health risk, and women preventive screening.
6. The app recommends relevant healthcare facilities from trusted facility data.
7. **Claude** writes a warm, grounded action plan based only on retrieved data and matched pathways.
8. Intake, pathway matches, recommended facilities, action plans, and feedback are persisted for analytics.

This app is informational and referral-oriented. It does **not** provide medical diagnosis, legal advice, or final eligibility determination.

---

## Core demo scenario

```text
I live in pincode 560001. I am pregnant and have a 3-year-old child. 
I do not know where to go for affordable health services. 
I need help with nutrition, vaccination, and finding a nearby facility.
```

Expected result:

* PIN code resolves to **BENGALURU URBAN / KARNATAKA**
* NFHS context finds **Bangalore / Karnataka** or uses state fallback
* Support pathways include maternal care, child nutrition, and immunization
* Facilities are recommended from Karnataka sample data
* Action plan is generated
* SQLite save succeeds in local mode
* Program Leader Dashboard reflects the saved local intake

---

## Architecture

| Layer               | Technology                                                      |
| ------------------- | --------------------------------------------------------------- |
| UI / app host       | Python **Streamlit**                                            |
| Final cloud host    | **Databricks Apps**                                             |
| AI reasoning        | **Anthropic Claude**                                            |
| Trusted data        | **Unity Catalog** Delta tables via **Databricks SQL Warehouse** |
| Matching logic      | Deterministic rules engine                                      |
| Local app state     | **SQLite**                                                      |
| Final app state     | **Lakebase** / managed Postgres                                 |
| Local fallback data | JSON files in `sample_data/`                                    |

---

## Trusted Unity Catalog data

Current source of truth:

```text
Catalog: benefits_navigator
Schema: trusted
```

Expected tables:

```text
benefits_navigator.trusted.facilities
benefits_navigator.trusted.india_post_pincode_directory
benefits_navigator.trusted.pincode_district_lookup
benefits_navigator.trusted.nfhs_5_district_health_indicators
benefits_navigator.trusted.support_pathways
```

### Table purpose

| Table                               | Purpose                                            |
| ----------------------------------- | -------------------------------------------------- |
| `facilities`                        | Healthcare facility and service-provider directory |
| `india_post_pincode_directory`      | India Post PIN code geography source               |
| `pincode_district_lookup`           | Derived PIN-to-district/state lookup               |
| `nfhs_5_district_health_indicators` | District-level public-health context               |
| `support_pathways`                  | Deterministic support-pathway rules                |

---

## Data-quality notes

The app intentionally handles real-world public-data issues:

* PIN code and district mappings can be ambiguous.
* Facility coordinates may be missing or contain `"NA"` string values.
* NFHS values may contain suppressed values such as `*`, unavailable values such as `NA`, or parenthesized estimates such as `(29.5)`.
* District names differ across datasets. For example:

   * PIN lookup: `BENGALURU URBAN`
   * NFHS: `Bangalore`
* The app uses normalization, alias handling, and state fallback instead of assuming exact string matches.

---

## Project layout

```text
app.py                              Streamlit UI + orchestration

src/
  config.py                         Environment/config handling
  data_loader.py                    Local JSON loading and row-count validation
  profile_extractor.py              Scenario parsing and profile extraction
  rules_engine.py                   Deterministic support-pathway matching
  action_plan.py                    Claude and deterministic fallback action plan
  state_store.py                    SQLite local state persistence
  ui_helpers.py                     Shared UI helpers and badges

sample_data/
  facilities.json
  india_post_pincode_directory.json
  pincode_district_lookup.json
  nfhs_5_district_health_indicators.json
  support_pathways.json
  sample_scenarios.json

scripts/
  export_sample_data.py             Read-only Unity Catalog sample exporter

tests/
  test_data_loader.py
  test_rules_engine.py
  test_profile_extractor.py

.local_state/                       Local SQLite DB folder, git-ignored

requirements.txt                    Python dependencies
.env.example                        Placeholder env template only, no secrets
.gitignore                          Protects secrets and local DB files
```

---

## Local setup

Run from:

```powershell
C:\Hackathon\benefits-navigator-hackathon
```

Create and activate virtual environment:

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create local folders:

```powershell
New-Item -ItemType Directory -Force sample_data | Out-Null
New-Item -ItemType Directory -Force .local_state | Out-Null
```

---

## Export local sample JSON from Unity Catalog

Use this only if `sample_data/*.json` files are missing or need refresh.

Set environment variables in PowerShell. Do **not** commit secrets.

```powershell
$env:DATABRICKS_CONFIG_PROFILE="hackathon-free"
$env:DATABRICKS_HOST="https://dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_SERVER_HOSTNAME="dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/81c2d8e2b863208b"
$env:DATABRICKS_TOKEN="<your_databricks_token>"

$env:UC_CATALOG="benefits_navigator"
$env:UC_SCHEMA="trusted"
$env:SQL_WAREHOUSE_NAME="Serverless Starter"
```

Run exporter:

```powershell
python scripts/export_sample_data.py
```

Or use the CLI profile path:

```powershell
python scripts/export_sample_data.py --profile hackathon-free --warehouse 81c2d8e2b863208b
```

Expected output:

```text
wrote facilities.json
wrote india_post_pincode_directory.json
wrote pincode_district_lookup.json
wrote nfhs_5_district_health_indicators.json
wrote support_pathways.json
```

Validate sample files:

```powershell
Get-ChildItem .\sample_data\*.json
```

---

## Run locally — Gate A: JSON + SQLite

Use local JSON files and SQLite only.

```powershell
$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="json_only"
$env:BENEFITS_DATA_MODE="json_only"

$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SAMPLE_DATA_DIR="sample_data"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"

$env:SHOW_LOCAL_STATE_DEBUG="true"

streamlit run app.py
```

Open:

```text
http://localhost:8501
```

---

## Local test checklist

Gate A passes when:

* Streamlit app starts locally.
* Local JSON files load successfully.
* App does not require Unity Catalog during launch.
* App does not require Lakebase.
* PIN code `560001` resolves to Bengaluru/Karnataka context.
* NFHS district context appears using alias or state fallback.
* Support pathways are matched deterministically.
* Facilities are recommended.
* Claude action plan is generated, or deterministic fallback works if Anthropic key is missing.
* SQLite save succeeds.
* Program Leader Dashboard reflects saved local intake.
* No secrets are printed or committed.

---

## Security and secrets

Never commit:

```text
.env
.local_state/
*.db
*.sqlite
*.sqlite3
__pycache__/
.venv/
```

Secrets must be provided through environment variables or Databricks App secrets.

If a Databricks PAT or Anthropic API key is accidentally pasted into chat, logs, or a file, rotate it immediately.

---

## Final deployment path

The planned progression is:

```text
Gate A: Local JSON + SQLite
Gate B: Unity Catalog trusted data + SQLite
Gate C: Databricks App + Unity Catalog + Lakebase
```

Do not move to Gate B or Gate C until Gate A passes end-to-end.

---

## Submission positioning

**BENEFITBRIDGE AI** is an AI-powered public-health and family-support navigator that combines family needs, trusted healthcare facility data, postal geography, and district-level health indicators to recommend practical next steps for families and visibility for program leaders.

It is built to be:

* grounded in trusted data
* compassionate for families
* explainable for judges
* useful for program leaders
* resilient through local and cloud fallbacks
