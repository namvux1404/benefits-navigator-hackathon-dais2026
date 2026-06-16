"""Structured debug logging for BenefitBridge AI.

Set SHOW_LOCAL_STATE_DEBUG=true (env var) to enable detailed server-side logs.
All log output is redacted: secret keys are replaced with <REDACTED>.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("benefitbridge")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s [benefitbridge] %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)

# Keys whose values are always redacted regardless of position in dict
_SECRET_KEYS: frozenset[str] = frozenset({
    "anthropic_api_key",
    "databricks_token",
    "access_token",
    "api_key",
    "password",
    "token",
    "secret",
})


def _is_debug() -> bool:
    """Re-read env var at call time so tests can toggle it with monkeypatch."""
    return os.environ.get("SHOW_LOCAL_STATE_DEBUG", "").lower() in ("true", "1", "yes")


def _redact(obj: dict) -> dict:
    """Return a copy of obj with secret key values replaced by <REDACTED>."""
    out: dict = {}
    for k, v in obj.items():
        if k.lower() in _SECRET_KEYS:
            out[k] = "<REDACTED>"
        elif isinstance(v, dict):
            out[k] = _redact(v)
        elif isinstance(v, list):
            out[k] = [_redact(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def log_base_profile(profile: dict, pincode_source: str = "") -> None:
    """Log BASE_PROFILE_AFTER_PINCODE_LOOKUP — emitted after Screen 1 extraction + lookup."""
    if not _is_debug():
        return
    logger.info(
        "BASE_PROFILE_AFTER_PINCODE_LOOKUP pincode=%s district=%s state=%s"
        " pregnant=%s child_age_months=%s needs=%s facility_search=%s pincode_source=%s",
        profile.get("pincode"),
        profile.get("district_norm", ""),
        profile.get("state_norm", ""),
        profile.get("pregnant"),
        profile.get("child_age_months"),
        profile.get("needs"),
        profile.get("facility_search"),
        pincode_source or "unknown",
    )
    logger.debug("BASE_PROFILE_JSON %s", json.dumps(_redact(profile), default=str))


def log_final_profile(profile: dict) -> None:
    """Log FINAL_PROFILE_FOR_MATCHING — emitted after Screen 2 merge."""
    if not _is_debug():
        return
    logger.info(
        "FINAL_PROFILE_FOR_MATCHING pincode=%s uninsured=%s low_income=%s"
        " travel_km=%s urgency=%s",
        profile.get("pincode"),
        profile.get("uninsured"),
        profile.get("low_income"),
        profile.get("travel_km"),
        profile.get("urgency"),
    )
    logger.debug("FINAL_PROFILE_JSON %s", json.dumps(_redact(profile), default=str))


def log_matched_pathways(pathways: list[dict]) -> None:
    """Log MATCHED_PATHWAYS — emitted after rules engine returns matches."""
    if not _is_debug():
        return
    for pw in pathways:
        logger.info(
            "MATCHED_PATHWAYS id=%s name=%s category=%s trigger=%s",
            pw.get("pathway_id"),
            pw.get("pathway_name"),
            pw.get("category", ""),
            pw.get("trigger_condition", ""),
        )


def log_facilities_selected(facilities: list[dict]) -> None:
    """Log NEARBY_FACILITIES_SELECTED — top 5, ranked order."""
    if not _is_debug():
        return
    for rank, f in enumerate(facilities[:5], 1):
        logger.info(
            "NEARBY_FACILITIES_SELECTED rank=%d name=%s city=%s phone_present=%s",
            rank,
            f.get("name", "?"),
            f.get("address_city", ""),
            bool(f.get("officialPhone")),
        )


def log_district_context(trace: dict) -> None:
    """Log DISTRICT_CONTEXT_SELECTED — NFHS lookup result."""
    if not _is_debug():
        return
    logger.info(
        "DISTRICT_CONTEXT_SELECTED requested=%s/%s match_type=%s matched=%s/%s"
        " candidates=%s row_count=%d",
        trace.get("requested_district"),
        trace.get("requested_state"),
        trace.get("match_type"),
        trace.get("matched_district"),
        trace.get("matched_state"),
        trace.get("alias_candidates_tried"),
        trace.get("candidate_row_count", 0),
    )


def log_action_plan_input(
    final_profile: dict,
    matched_pathways: list[dict],
    nfhs_rows: list[dict],
    facilities: list[dict],
    followup_answers: dict | None = None,
) -> None:
    """Log ACTION_PLAN_INPUT_CONTEXT — called before Claude action-plan generation."""
    if not _is_debug():
        return
    logger.info(
        "ACTION_PLAN_INPUT_CONTEXT pincode=%s pathways=%d nfhs_rows=%d"
        " facilities=%d followup_count=%d",
        final_profile.get("pincode"),
        len(matched_pathways),
        len(nfhs_rows),
        len(facilities),
        len(followup_answers) if followup_answers else 0,
    )
    logger.debug("ACTION_PLAN_PROFILE %s", json.dumps(_redact(final_profile), default=str))
    logger.debug(
        "ACTION_PLAN_PATHWAYS %s",
        json.dumps([p.get("pathway_id") for p in matched_pathways]),
    )
    if followup_answers:
        logger.debug(
            "ACTION_PLAN_FOLLOWUP_ANSWERS %s", json.dumps(followup_answers, default=str)
        )


def log_nfhs_lookup_trace(trace: dict) -> None:
    """Log DISTRICT_CONTEXT_LOOKUP_TRACE — NFHS alias/state resolution details."""
    if not _is_debug():
        return
    logger.info(
        "DISTRICT_CONTEXT_LOOKUP_TRACE requested=%s/%s match_type=%s"
        " matched=%s/%s candidates=%s row_count=%d",
        trace.get("requested_district"),
        trace.get("requested_state"),
        trace.get("match_type"),
        trace.get("matched_district"),
        trace.get("matched_state"),
        trace.get("alias_candidates_tried"),
        trace.get("candidate_row_count", 0),
    )
