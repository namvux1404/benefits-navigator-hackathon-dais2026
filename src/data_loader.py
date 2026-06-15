from __future__ import annotations
import json
from typing import Any

from .config import SAMPLE_DATA_DIR

# Maps district_norm values (pincode_district_lookup) → NFHS district_name values (normalised)
_DISTRICT_ALIAS: dict[str, str] = {
    "BENGALURU URBAN": "BANGALORE",
    "BENGALURU RURAL": "BANGALORE RURAL",
    "MYSURU": "MYSORE",
    "KALABURAGI": "GULBARGA",
    "VIJAYAPURA": "BIJAPUR",
    "BELAGAVI": "BELGAUM",
    "BALLARI": "BELLARY",
    "SHIVAMOGGA": "SHIMOGA",
    "TUMAKURU": "TUMKUR",
    "DAVANAGERE": "DAVANGERE",
    "CHIKKAMAGALURU": "CHIKMAGALUR",
    "RAMANAGARA": "RAMANAGARAM",
}


def _norm(s: Any) -> str:
    return str(s or "").upper().strip()


def _safe_float(v: Any) -> float | None:
    try:
        if str(v).strip() in ("", "NA", "na", "None", "null"):
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _load(name: str) -> list[dict]:
    path = SAMPLE_DATA_DIR / f"{name}.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_pathways() -> list[dict]:
    return _load("support_pathways")


def load_scenarios() -> list[dict]:
    return _load("sample_scenarios")


def get_district_for_pincode(pincode: str) -> dict | None:
    """Return {district_norm, state_norm, lat, lon} for pincode, or None."""
    pincode = str(pincode).strip()

    for row in _load("pincode_district_lookup"):
        if str(row.get("pincode", "")).strip() == pincode:
            return {
                "district_norm": _norm(row.get("district_norm")),
                "state_norm": _norm(row.get("state_norm")),
                "lat": _safe_float(row.get("sample_latitude")),
                "lon": _safe_float(row.get("sample_longitude")),
            }

    # Fallback: india_post directory (less precise district names)
    for row in _load("india_post_pincode_directory"):
        if str(row.get("pincode", "")).strip() == pincode:
            return {
                "district_norm": _norm(row.get("district")),
                "state_norm": _norm(row.get("statename")),
                "lat": _safe_float(row.get("latitude")),
                "lon": _safe_float(row.get("longitude")),
            }

    return None


def get_nfhs_for_district(district_norm: str, state_norm: str) -> list[dict]:
    """Return NFHS rows matching the district (via alias map) or state fallback."""
    rows = _load("nfhs_5_district_health_indicators")
    alias = _DISTRICT_ALIAS.get(district_norm, district_norm)

    matches = [
        r for r in rows
        if _norm(r.get("district_name")) in (district_norm, alias)
    ]
    if matches:
        return matches

    # State-level fallback (capped to avoid returning too much data)
    return [r for r in rows if _norm(r.get("state_ut")) == state_norm][:5]


def get_facilities(pincode: str, district_norm: str, state_norm: str) -> list[dict]:
    """Return facilities sorted: exact pincode first, then same state, then rest."""
    rows = _load("facilities")

    def _sort_key(r: dict) -> int:
        z = _norm(r.get("address_zipOrPostcode"))
        s = _norm(r.get("address_stateOrRegion"))
        if z == _norm(pincode):
            return 0
        if s == state_norm:
            return 1
        return 2

    return sorted(rows, key=_sort_key)


def get_district_alias(district_norm: str) -> str:
    return _DISTRICT_ALIAS.get(district_norm, district_norm)


def list_nfhs_districts() -> list[str]:
    rows = _load("nfhs_5_district_health_indicators")
    return sorted({r.get("district_name", "").strip() for r in rows if r.get("district_name", "").strip()})
