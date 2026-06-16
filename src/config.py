from __future__ import annotations
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
LOCAL_STATE_DIR = PROJECT_ROOT / ".local_state"
LOCAL_STATE_DIR.mkdir(exist_ok=True)
LOCAL_SQLITE_PATH = os.environ.get(
    "LOCAL_SQLITE_PATH",
    str(LOCAL_STATE_DIR / "benefitbridge_local.db"),
).strip()
SQLITE_PATH = Path(LOCAL_SQLITE_PATH)
SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
_DEFAULT_CLAUDE_MODEL = DEFAULT_CLAUDE_MODEL
raw_model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL).strip()
if not raw_model or "opus" in raw_model.lower():
    CLAUDE_MODEL = DEFAULT_CLAUDE_MODEL
else:
    CLAUDE_MODEL = raw_model
CLAUDE_AVAILABLE = bool(ANTHROPIC_API_KEY)

# Data source mode — controls the badge and (Gate B+) data fetching.
# Accept either env var name so the badge works without renaming existing vars.
DATA_MODE: str = (
    os.environ.get("BENEFITBRIDGE_DATA_MODE")
    or os.environ.get("BENEFITS_DATA_MODE")
    or "json_only"
).lower().strip()

DATABRICKS_SERVER_HOSTNAME = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "").strip()
DATABRICKS_HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "").strip()
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "").strip()
UC_CATALOG = os.environ.get("UC_CATALOG", "benefits_navigator").strip() or "benefits_navigator"
UC_SCHEMA = os.environ.get("UC_SCHEMA", "trusted").strip() or "trusted"

# State store mode — 'sqlite' (Gate A/B) or 'lakebase' (Gate C)
STATE_STORE_MODE: str = os.environ.get("STATE_STORE_MODE", "sqlite").lower().strip()
