from __future__ import annotations
import json
import re
from typing import Any


def safe_nfhs_value(v: Any) -> tuple[str, str]:
    """Return (display_str, quality) - quality in {'certain','uncertain','suppressed','missing'}."""
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


def normalize_trust_score(raw: float | None) -> float | None:
    """Normalize a 0–1, 0–10, or 0–100 score to the 0–10 range. Returns None if unresolvable."""
    if raw is None:
        return None
    if 0.0 <= raw <= 1.0:
        return round(raw * 10, 1)
    if 1.0 < raw <= 10.0:
        return round(raw, 1)
    if 10.0 < raw <= 100.0:
        return round(raw / 10, 1)
    return None


def trust_signal_from_score(score: float | None) -> str:
    """Map a normalized 0–10 score to a trust signal label."""
    if score is None:
        return "Unknown"
    if score >= 8.0:
        return "High"
    if score >= 5.0:
        return "Medium"
    if score > 0:
        return "Limited"
    return "Unknown"


def score_from_signal(signal: str) -> float | None:
    """Return a representative numeric score for a named trust signal."""
    return {"high": 8.5, "medium": 6.5, "limited": 4.0, "low": 2.5}.get(
        (signal or "").lower()
    )


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
        "email": _clean_email(f.get("email", "")),
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


def data_source_label(
    data_mode: str,
    active_source: str | None = None,
    fallback_reason: str | None = None,
) -> str:
    """Human-readable data-source label for the app badge (no secrets)."""
    if fallback_reason or active_source == "json_fallback":
        return "Data source: Local sample JSON fallback after Unity Catalog load failure"
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

    Priority: most-recent session district -> Bangalore -> first available.
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
        parts: list[str] = []
        if age is not None:
            parts.append(f"child aged {age} months")
        if profile.get("immunization_need"):
            parts.append("immunization need identified")
        return ", ".join(parts).capitalize() if parts else "Child in immunization age range"
    if pathway_id == "maternal_care":
        if profile.get("pregnant"):
            return "Pregnancy mentioned"
        if profile.get("recently_delivered"):
            return "Recent delivery mentioned"
        return "Maternal care need identified"
    if pathway_id == "child_nutrition":
        if profile.get("nutrition_need"):
            return "Nutrition support requested"
        if profile.get("child_under_5"):
            return "Child under 5 — nutrition support available"
        return "Child nutrition need identified"
    if pathway_id == "health_insurance_awareness":
        if profile.get("uninsured"):
            return "Low-cost or uninsured care need mentioned"
        if profile.get("low_income"):
            return "Affordability or low-cost care need mentioned"
        return "Health coverage question identified"
    if pathway_id == "household_health_risk":
        return "Household health risk factors mentioned"
    if pathway_id == "women_preventive_screening":
        return "Adult woman profile may benefit from preventive screening guidance"
    # Safe fallback: never show raw boolean expressions
    name = pathway.get("pathway_name") or pathway_id.replace("_", " ").capitalize()
    return f"{name} criteria matched"


def facility_why_shown(
    facility: dict,
    search_pincode: str = "",
    search_state: str = "",
    trust_signal: str = "",
) -> str:
    """Return a short 'why shown' description for a facility card."""
    parts: list[str] = []
    fac_pin = str(facility.get("address_zipOrPostcode") or "").strip()
    fac_state = str(facility.get("address_stateOrRegion") or "").upper().strip()
    if search_pincode and fac_pin == str(search_pincode).strip():
        parts.append("PIN code match")
    elif search_state and fac_state == search_state.upper():
        parts.append("State location match")
    else:
        parts.append("Location data available")
    if trust_signal in ("High", "Medium"):
        parts.append("stronger available evidence")
    else:
        parts.append("evidence available")
    return " · ".join(parts)


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


_NEED_LABELS: dict[str, str] = {
    "maternal care": "Maternal care",
    "child nutrition": "Child nutrition",
    "child immunization": "Child immunization",
    "nearby facility": "Nearby facility search",
    "health insurance": "Health insurance / low-cost care",
    "preventive screening": "Preventive screening",
}


def format_needs_for_display(needs: list[str]) -> str:
    """Return a deduplicated, human-readable comma-separated string of needs.

    Normalises each need by replacing underscores with spaces and lower-casing,
    deduplicates case-insensitively, then maps to a friendly label.
    """
    seen: set[str] = set()
    labels: list[str] = []
    for raw in needs:
        normalised = raw.replace("_", " ").strip().lower()
        if normalised in seen:
            continue
        seen.add(normalised)
        labels.append(_NEED_LABELS.get(normalised, normalised.capitalize()))
    return ", ".join(labels) if labels else "-"


def limited_facilities(facilities: list[dict], limit: int = 5) -> list[dict]:
    return facilities[:limit]


def results_section_order() -> list[str]:
    return [
        "header",
        "matched_pathways",
        "action_plan",
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


def badge_data_label(
    data_mode: str,
    active_source: str | None = None,
    fallback_reason: str | None = None,
) -> str:
    """Short pill label for the data-source badge."""
    if fallback_reason or active_source == "json_fallback":
        return "Data: Local sample JSON"
    if data_mode.lower().strip() == "uc":
        return "Data: Unity Catalog"
    return "Data: Local sample JSON"


def badge_state_label(state_mode: str) -> str:
    """Short pill label for the state-store badge."""
    if state_mode.lower().strip() == "lakebase":
        return "State: Lakebase"
    return "State: SQLite"


def badge_ai_label(claude_available: bool, claude_model: str) -> str:
    """Short pill label for the AI-mode badge."""
    if not claude_available:
        return "AI: Deterministic"
    return "AI: Claude Sonnet"


_SOURCE_LABEL_MAP: dict[str, str] = {
    "kie": "Provided facility record",
    "overture": "Provided facility record",
    "dynamic": "Provided facility record",
    "constant": "Provided facility record",
}

_EMAIL_VALID_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_EMAIL_BAD_RE = re.compile(r'[\xc2\xa0\x00-\x1f]|protected', re.IGNORECASE)


def _clean_data_source(raw_source: str | None) -> str:
    """Map raw source field value to a human-readable label."""
    if not raw_source:
        return ""
    s = str(raw_source).strip().lower()
    if s in ("", "na", "null", "none"):
        return ""
    return _SOURCE_LABEL_MAP.get(s, "Provided facility record")


def _clean_email(raw_email: str | None) -> str:
    """Return email if it looks valid, otherwise empty string."""
    if not raw_email:
        return ""
    e = str(raw_email).strip()
    if not e or len(e) > 120:
        return ""
    if _EMAIL_BAD_RE.search(e):
        return ""
    if not _EMAIL_VALID_RE.match(e):
        return ""
    return e


def compute_proxy_trust_signal(facility: dict) -> dict:
    """Derive a trust signal from available facility record fields (score out of 10).

    Returns {"signal": "High|Medium|Limited|Unknown", "score": int, "max_score": int,
             "score_display": "8/10", "evidence": [str], "why": str}.
    Does NOT overclaim — signal reflects data completeness, not care quality.

    Thresholds (per spec): >= 8 High, >= 5 Medium, > 0 Limited, 0 Unknown.
    """
    score = 0
    evidence: list[str] = []
    max_score = 10

    if facility.get("officialPhone"):
        score += 1
        evidence.append("Contact phone on record")
    if _clean_email(facility.get("email")):
        score += 1
        evidence.append("Email contact on record")

    addr_parts = [
        facility.get("address_line1"),
        facility.get("address_city"),
        facility.get("address_stateOrRegion"),
        facility.get("address_zipOrPostcode"),
    ]
    filled_addr = sum(1 for p in addr_parts if p and str(p).strip() not in ("", "NA"))
    if filled_addr >= 3:
        score += 2
        evidence.append("Full address recorded")
    elif filled_addr >= 2:
        score += 1
        evidence.append("Partial address recorded")

    specs = facility.get("specialties") or ""
    if str(specs).strip() not in ("", "NA", "[]", "null"):
        score += 1
        evidence.append("Specialties recorded")

    cap_type = facility.get("capability") or facility.get("organization_type") or ""
    if str(cap_type).strip() not in ("", "NA", "null", "None"):
        score += 1
        evidence.append("Service capability recorded")

    if str(facility.get("affiliated_staff_presence", "")).lower() == "true":
        score += 1
        evidence.append("Staff affiliation confirmed")

    desc = facility.get("description") or ""
    if desc and str(desc).strip() not in ("", "NA", "null"):
        score += 1
        evidence.append("Facility description available")

    if facility.get("source"):
        score += 1
        evidence.append(f"Source: {_clean_data_source(facility['source']) or facility['source']}")

    _lat = safe_float(facility.get("latitude"))
    _lon = safe_float(facility.get("longitude"))
    if _lat is not None and _lon is not None:
        score += 1
        evidence.append("Coordinates recorded")

    score = min(score, max_score)
    signal = trust_signal_from_score(score if score > 0 else None)

    return {
        "signal": signal,
        "score": score,
        "max_score": max_score,
        "score_display": f"{score}/{max_score}",
        "evidence": evidence,
        "why": "; ".join(evidence) if evidence else "No facility record data available",
    }


def facility_evidence_summary(facility: dict, trust_score_row: dict | None = None) -> dict:
    """Return structured evidence block data for a facility card.

    Used to cite the underlying facility record for every recommendation.
    """
    fd = format_facility(facility)
    evidence_items: list[tuple[str, str]] = []

    # Location
    loc_parts = [
        facility.get("address_city"),
        facility.get("address_stateOrRegion"),
        facility.get("address_zipOrPostcode"),
    ]
    loc_str = ", ".join(str(p) for p in loc_parts if p and str(p) not in ("", "NA"))
    if loc_str:
        evidence_items.append(("Location", loc_str))

    # Facility type
    ftype = facility.get("facilityTypeId") or facility.get("organization_type") or ""
    otype = facility.get("operatorTypeId") or ""
    type_str = ftype.capitalize() if ftype else ""
    if otype and otype.lower() not in ("null", ""):
        type_str += f" ({otype})"
    if type_str:
        evidence_items.append(("Facility type", type_str))

    # Services / specialties
    if fd["service_tags"]:
        evidence_items.append(("Services / specialties", ", ".join(fd["service_tags"])))
    elif str(facility.get("specialties", "")).strip() not in ("", "NA", "[]", "null"):
        evidence_items.append(("Specialties (raw)", str(facility["specialties"])[:120]))

    # Capacity and year
    cap = facility.get("capacity") or ""
    if cap and str(cap).strip() not in ("", "NA", "null"):
        evidence_items.append(("Bed capacity", str(cap)))
    year = facility.get("yearEstablished") or ""
    if year and str(year).strip() not in ("", "NA", "null"):
        evidence_items.append(("Year established", str(year)))

    # Contact evidence
    contact_parts = []
    if fd["phone"]:
        contact_parts.append(f"phone {fd['phone']}")
    if fd["email"]:
        contact_parts.append(f"email {fd['email']}")
    evidence_items.append((
        "Contact evidence",
        ", ".join(contact_parts) if contact_parts else "No contact details on record — verify before visiting",
    ))

    # Data source and freshness
    raw_src = facility.get("source") or ""
    clean_src = _clean_data_source(raw_src)
    if clean_src:
        evidence_items.append(("Data source", clean_src))
    recency = facility.get("recency_of_page_update") or ""
    if recency and str(recency).strip() not in ("", "NA", "null"):
        evidence_items.append(("Record last updated", str(recency)[:10]))

    # Short description snippet
    desc = str(facility.get("description") or "").strip()
    if desc and desc.lower() not in ("na", "null", "none"):
        evidence_items.append(("Record snippet", desc[:200]))

    # Trust signal
    if trust_score_row:
        ts_signal_raw = str(
            trust_score_row.get("trust_signal")
            or trust_score_row.get("signal")
            or ""
        )
        ts_why = str(
            trust_score_row.get("reason")
            or trust_score_row.get("why")
            or trust_score_row.get("evidence")
            or "Based on UC trusted facility evidence"
        )
        # Extract and normalize numeric score from trust_scores row
        ts_numeric: float | None = None
        for _ts_field in ("trust_score", "score", "confidence", "rating", "evidence_score"):
            _tv = trust_score_row.get(_ts_field)
            if _tv is not None:
                try:
                    ts_numeric = float(str(_tv).replace("%", "").strip())
                    break
                except (ValueError, TypeError):
                    pass
        ts_normalized = normalize_trust_score(ts_numeric)
        # Derive signal: prefer explicit label, fall back to normalized score mapping
        if ts_signal_raw and ts_signal_raw.lower() not in ("", "unknown", "none"):
            ts_signal = ts_signal_raw
        elif ts_normalized is not None:
            ts_signal = trust_signal_from_score(ts_normalized)
        else:
            ts_signal = "Unknown"
        # If no numeric score but named signal, synthesize a representative score
        if ts_normalized is None and ts_signal_raw:
            ts_normalized = score_from_signal(ts_signal_raw)
        ts_score_display = f"{ts_normalized:.1f}/10" if ts_normalized is not None else ""
        trust_info = {
            "signal": ts_signal,
            "why": ts_why,
            "source": "facility_trust_scores",
            "score_display": ts_score_display,
            "score_source": "Unity Catalog facility trust score table",
            "matched_by": "Trust score lookup",
        }
    else:
        proxy = compute_proxy_trust_signal(facility)
        trust_info = {
            "signal": proxy["signal"],
            "why": proxy["why"],
            "source": "facility record completeness",
            "score_display": proxy["score_display"],
            "score_source": "Facility record completeness (proxy estimate)",
            "matched_by": "Proxy scoring",
        }

    return {
        "evidence_items": evidence_items,
        "trust_info": trust_info,
    }


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
