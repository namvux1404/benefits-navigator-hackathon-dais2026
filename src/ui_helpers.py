from __future__ import annotations
import json
import re
from typing import Any


def safe_nfhs_value(v: Any) -> tuple[str, str]:
    """Return (display_str, quality) — quality in {'certain','uncertain','suppressed','missing'}."""
    if v is None:
        return ("N/A", "missing")
    s = str(v).strip()
    if s in ("", "NA", "nan", "None"):
        return ("N/A", "missing")
    if s == "*":
        return ("Not available - suppressed", "suppressed")
    if s.startswith("(") and s.endswith(")"):
        inner = s[1:-1].strip()
        if _is_number(inner):
            return (f"{inner}%", "uncertain")
        return (inner or "N/A", "uncertain")
    try:
        float(s)
        return (f"{s}%", "certain")
    except ValueError:
        return (s, "uncertain")


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def clean_indicator_label(label: str) -> str:
    return label.replace(" (%)", "").strip()


def plan_method_label(plan_method: str) -> str:
    if str(plan_method).lower().strip() == "claude":
        return "Claude Sonnet"
    return "Deterministic fallback"


def safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).strip()
        if s in ("", "NA", "na", "nan", "None"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def format_facility(f: dict) -> dict:
    """Return a display-ready dict for a facility row."""
    phone = f.get("officialPhone") or ""
    if not phone:
        raw_phones = f.get("phone_numbers", "")
        if raw_phones and raw_phones.startswith("["):
            try:
                phones = json.loads(raw_phones)
                if phones:
                    phone = str(phones[0])
            except Exception:
                pass

    return {
        "name": f.get("name", "Unnamed facility"),
        "type": f.get("organization_type", ""),
        "address": ", ".join(
            x for x in [
                f.get("address_line1", ""),
                f.get("address_city", ""),
                f.get("address_stateOrRegion", ""),
                f.get("address_zipOrPostcode", ""),
            ] if x
        ),
        "phone": phone,
        "email": f.get("email", ""),
        "specialties": f.get("specialties", ""),
        "service_tags": service_tags_for_facility(f),
        "lat": safe_float(f.get("latitude")),
        "lon": safe_float(f.get("longitude")),
    }


# Curated subset of NFHS indicators shown in the UI
_NFHS_KEY_LABELS: dict[str, str] = {
    "institutional_birth_5y_pct": "Institutional births (%)",
    "mothers_who_had_at_least_4_anc_visits_lb5y_pct": "4+ ANC visits (%)",
    "mothers_who_consumed_ifa_for_100_days_or_more_when_they_wer_pct": "IFA 100+ days (%)",
    "child_12_23m_fully_vaccinated_based_on_information_from_eit_pct": "Children fully vaccinated (%)",
    "child_u5_who_are_stunted_height_for_age_18_pct": "Child stunting (%)",
    "child_u5_who_are_underweight_weight_for_age_18_pct": "Child underweight (%)",
    "prev_diarrhoea_2wk_child_u5_pct": "Child diarrhea prevalence (%)",
    "hh_member_covered_health_insurance_pct": "Health insurance coverage (%)",
    "hh_improved_water_pct": "Improved water source (%)",
    "hh_use_improved_sanitation_pct": "Improved sanitation (%)",
    "non_pregnant_w15_49_who_are_anaemic_lt_12_0_g_dl_22_pct": "Women anaemia (%)",
    "pregnant_w15_49_who_are_anaemic_lt_11_0_g_dl_22_pct": "Pregnant women anaemia (%)",
    "women_age_30_49_years_ever_undergone_a_cervical_screen_pct": "Cervical screening (%)",
    "w20_24_married_before_age_18_years_pct": "Child marriage (women 20-24, %)",
    "child_u6m_exclusively_breastfed_pct": "Exclusive breastfeeding <6m (%)",
}


def get_nfhs_display_rows(nfhs_row: dict) -> list[dict]:
    """Return curated NFHS indicators as a list of {label, value, quality, key} dicts."""
    result = []
    for key, label in _NFHS_KEY_LABELS.items():
        v = nfhs_row.get(key)
        display, quality = safe_nfhs_value(v)
        result.append({
            "label": clean_indicator_label(label),
            "value": display,
            "quality": quality,
            "key": key,
        })
    return result


def data_source_label(data_mode: str) -> str:
    """Human-readable data-source label for the app badge (no secrets)."""
    if data_mode.lower().strip() == "uc":
        return "Data source: Unity Catalog trusted tables"
    return "Data source: Local sample JSON (Gate A)"


def state_store_label(state_mode: str) -> str:
    """Human-readable state-store label for the app badge."""
    if state_mode.lower().strip() == "lakebase":
        return "State: Lakebase"
    return "State: Local SQLite fallback"


def ai_mode_label(claude_available: bool, claude_model: str) -> str:
    """Human-readable AI-mode label for the app badge."""
    if not claude_available:
        return "AI: Deterministic fallback (no API key)"
    return "AI: Claude Sonnet"


def preferred_district_index(district_names: list[str], recent_district_norm: str) -> int:
    """Return the best default selectbox index for the Program Leader Dashboard.

    Priority: most-recent session district → Bangalore → first available.
    """
    from .data_loader import get_district_alias

    def _norm(s: str) -> str:
        return s.upper().strip()

    if recent_district_norm:
        alias = _norm(get_district_alias(recent_district_norm))
        norm_recent = _norm(recent_district_norm)
        for i, dn in enumerate(district_names):
            n = _norm(dn)
            if n == norm_recent or n == alias:
                return i

    for i, dn in enumerate(district_names):
        if "BANGALORE" in _norm(dn):
            return i

    return 0


def pathway_reason(profile: dict, pathway: dict) -> str:
    pathway_id = pathway.get("pathway_id", "")
    if pathway_id == "immunization":
        age = profile.get("child_age_months")
        parts = []
        if age is not None:
            parts.append(f"child age {age} months")
        if profile.get("immunization_need"):
            parts.append("immunization need")
        return " + ".join(parts) or pathway.get("trigger_condition", "")
    if pathway_id == "maternal_care":
        if profile.get("pregnant"):
            return "pregnancy mentioned"
        if profile.get("recently_delivered"):
            return "recent delivery mentioned"
    if pathway_id == "child_nutrition" and profile.get("nutrition_need"):
        return "nutrition support requested"
    if pathway_id == "health_insurance_awareness":
        if profile.get("uninsured"):
            return "uninsured or no coverage mentioned"
        if profile.get("low_income"):
            return "affordability or low-cost need mentioned"
    return pathway.get("trigger_condition", "")


def next_steps_for_profile(profile: dict) -> list[str]:
    if profile.get("immunization_need"):
        return [
            "Check your child's vaccination card.",
            "Call one nearby facility.",
            "Ask which vaccines are due.",
            "Keep the facility phone number saved.",
        ]
    return [
        "Call or visit a nearby facility.",
        "Ask about maternal/child nutrition support.",
        "Bring any available health record.",
        "Confirm next visit or referral.",
    ]


def limited_facilities(facilities: list[dict], limit: int = 5) -> list[dict]:
    return facilities[:limit]


def results_section_order() -> list[str]:
    return [
        "header",
        "matched_pathways",
        "action_plan",
        "next_steps",
        "facilities",
        "district_indicators",
        "feedback",
    ]


_SERVICE_LABELS: dict[str, str] = {
    "pediatrics": "Pediatrics",
    "pediatric": "Pediatrics",
    "child": "Child Health",
    "neonatology": "Child Health",
    "immunization": "Immunization Support",
    "vaccination": "Immunization Support",
    "familymedicine": "General Medicine",
    "internalmedicine": "General Medicine",
    "generalsurgery": "General Medicine",
    "gynecologyandobstetrics": "Obstetrics",
    "obstetrics": "Obstetrics",
    "maternity": "Obstetrics",
    "maternal": "Obstetrics",
    "nutrition": "Nutrition Support",
    "dentistry": "Dental Care",
}


def _parse_raw_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    s = str(value).strip()
    if not s or s.lower() in ("na", "none", "null"):
        return []
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            return []
    return [s] if len(s) <= 40 and "[" not in s and "]" not in s else []


def _service_label(raw: str) -> str | None:
    compact = re.sub(r"[^a-z]", "", raw.lower())
    for key, label in _SERVICE_LABELS.items():
        if key in compact:
            return label
    return None


def service_tags_for_facility(facility: dict, limit: int = 3) -> list[str]:
    tags: list[str] = []
    for field in ("specialties", "capability", "organization_type"):
        for raw in _parse_raw_list(facility.get(field)):
            label = _service_label(raw)
            if label and label not in tags:
                tags.append(label)
            if len(tags) >= limit:
                return tags
    return tags


def facility_card_public_text(facility: dict) -> str:
    fd = format_facility(facility)
    parts = [fd["name"], fd["address"], fd["phone"], fd["email"]]
    parts.extend(fd["service_tags"])
    return "\n".join(p for p in parts if p)


def district_context_rows(profile: dict, nfhs_row: dict, limit: int = 6) -> tuple[list[dict], list[dict]]:
    rows = get_nfhs_display_rows(nfhs_row)
    if profile.get("immunization_need"):
        priority = [
            "child_12_23m_fully_vaccinated_based_on_information_from_eit_pct",
            "child_u5_who_are_stunted_height_for_age_18_pct",
            "child_u5_who_are_underweight_weight_for_age_18_pct",
            "prev_diarrhoea_2wk_child_u5_pct",
            "hh_member_covered_health_insurance_pct",
            "hh_improved_water_pct",
        ]
    else:
        priority = [
            "mothers_who_had_at_least_4_anc_visits_lb5y_pct",
            "institutional_birth_5y_pct",
            "mothers_who_consumed_ifa_for_100_days_or_more_when_they_wer_pct",
            "child_u5_who_are_stunted_height_for_age_18_pct",
            "child_u5_who_are_underweight_weight_for_age_18_pct",
            "non_pregnant_w15_49_who_are_anaemic_lt_12_0_g_dl_22_pct",
            "hh_member_covered_health_insurance_pct",
        ]
    by_key = {r["key"]: r for r in rows}
    selected = [by_key[k] for k in priority if k in by_key][:limit]
    selected_keys = {r["key"] for r in selected}
    more = [r for r in rows if r["key"] not in selected_keys]
    return selected, more
