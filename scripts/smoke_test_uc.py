from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import (  # noqa: E402
    DATABRICKS_HTTP_PATH,
    DATABRICKS_SERVER_HOSTNAME,
    DATABRICKS_TOKEN,
    UC_CATALOG,
    UC_SCHEMA,
)

TABLES = [
    "facilities",
    "india_post_pincode_directory",
    "pincode_district_lookup",
    "nfhs_5_district_health_indicators",
    "support_pathways",
]


def _qualified(table: str) -> str:
    return f"`{UC_CATALOG}`.`{UC_SCHEMA}`.`{table}`"


def _required_env_missing() -> list[str]:
    return [
        key for key, value in [
            ("DATABRICKS_SERVER_HOSTNAME", DATABRICKS_SERVER_HOSTNAME),
            ("DATABRICKS_HTTP_PATH", DATABRICKS_HTTP_PATH),
            ("DATABRICKS_TOKEN", DATABRICKS_TOKEN),
        ] if not value
    ]


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    token = DATABRICKS_TOKEN
    if token:
        message = message.replace(token, "[REDACTED_TOKEN]")
    return message[:800]


def _fetch_support_pathways(cursor) -> list[dict]:
    cursor.execute(f"SELECT * FROM {_qualified('support_pathways')}")
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _compare_support_pathways(uc_rows: list[dict]) -> list[str]:
    local_path = ROOT / "sample_data" / "support_pathways.json"
    if not local_path.exists():
        return ["Local sample support_pathways.json not found for comparison."]
    local_rows = json.loads(local_path.read_text(encoding="utf-8"))
    local_by_id = {str(r.get("pathway_id")): r for r in local_rows}
    uc_by_id = {str(r.get("pathway_id")): r for r in uc_rows}
    mismatches: list[str] = []
    for pathway_id, local in local_by_id.items():
        uc = uc_by_id.get(pathway_id)
        if not uc:
            mismatches.append(f"{pathway_id}: missing in Unity Catalog")
            continue
        if str(local.get("trigger_condition", "")).strip() != str(uc.get("trigger_condition", "")).strip():
            mismatches.append(f"{pathway_id}: trigger_condition mismatch")
    for pathway_id in sorted(set(uc_by_id) - set(local_by_id)):
        mismatches.append(f"{pathway_id}: extra in Unity Catalog")
    return mismatches


def main() -> int:
    missing = _required_env_missing()
    if missing:
        print("Unity Catalog smoke test: failure")
        print("Missing env vars: " + ", ".join(missing))
        return 1

    try:
        from databricks import sql

        conn = sql.connect(
            server_hostname=DATABRICKS_SERVER_HOSTNAME,
            http_path=DATABRICKS_HTTP_PATH,
            access_token=DATABRICKS_TOKEN,
        )
        counts: dict[str, int] = {}
        with conn.cursor() as cursor:
            for table in TABLES:
                fqtn = f"{UC_CATALOG}.{UC_SCHEMA}.{table}"
                cursor.execute(f"SELECT COUNT(*) AS row_count FROM {_qualified(table)}")
                counts[fqtn] = int(cursor.fetchone()[0])
            support_rows = _fetch_support_pathways(cursor)
        conn.close()
    except Exception as exc:
        print("Unity Catalog smoke test: failure")
        print(f"Reason: {type(exc).__name__}")
        details = _safe_error(exc)
        if details:
            print(f"Details: {details}")
        return 1

    print("Unity Catalog smoke test: success")
    for table, count in counts.items():
        print(f"{table}: {count}")

    mismatches = _compare_support_pathways(support_rows)
    if mismatches:
        print("Support pathways consistency: mismatch")
        for item in mismatches:
            print(f"- {item}")
    else:
        print("Support pathways consistency: matches local JSON trigger logic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
