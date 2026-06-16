"""Tests for bb_logging (secret redaction, enable/disable) and NFHS alias/state-first fix."""
from __future__ import annotations

import inspect
import logging

import pytest

import src.data_loader as dl
from src.bb_logging import _redact, log_base_profile
from src.data_loader import get_nfhs_for_district, get_nfhs_lookup_trace

# ---------------------------------------------------------------------------
# Controlled NFHS dataset: includes a cross-state "Bangalore" row in
# Arunachal Pradesh to prove state-first filtering works.
# ---------------------------------------------------------------------------
_MOCK_NFHS = [
    {"district_name": "Bangalore", "state_ut": "KARNATAKA", "hh_member_covered_health_insurance_pct": "80"},
    {"district_name": "Bangalore Rural", "state_ut": "KARNATAKA", "hh_member_covered_health_insurance_pct": "70"},
    {"district_name": "Mysore", "state_ut": "KARNATAKA", "hh_member_covered_health_insurance_pct": "75"},
    # Tricky cross-state row: same district_name, different state
    {"district_name": "Bangalore", "state_ut": "ARUNACHAL PRADESH", "hh_member_covered_health_insurance_pct": "60"},
    {"district_name": "Dibang Valley", "state_ut": "ARUNACHAL PRADESH", "hh_member_covered_health_insurance_pct": "30"},
]


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

def test_redact_anthropic_api_key():
    obj = {"anthropic_api_key": "sk-supersecret", "district": "Bangalore"}
    result = _redact(obj)
    assert result["anthropic_api_key"] == "<REDACTED>"
    assert result["district"] == "Bangalore"


def test_redact_databricks_token():
    obj = {"databricks_token": "dapi123abc", "pincode": "560001"}
    result = _redact(obj)
    assert result["databricks_token"] == "<REDACTED>"
    assert result["pincode"] == "560001"


def test_redact_nested_dict():
    obj = {"config": {"anthropic_api_key": "sk-x", "district": "Mysore"}}
    result = _redact(obj)
    assert result["config"]["anthropic_api_key"] == "<REDACTED>"
    assert result["config"]["district"] == "Mysore"


def test_redact_preserves_non_secret_keys():
    obj = {"name": "Alice", "district_norm": "BENGALURU URBAN", "state_norm": "KARNATAKA"}
    result = _redact(obj)
    assert result == obj


# ---------------------------------------------------------------------------
# Logging enable / disable via SHOW_LOCAL_STATE_DEBUG
# ---------------------------------------------------------------------------

def test_logging_disabled_by_default(monkeypatch, caplog):
    monkeypatch.delenv("SHOW_LOCAL_STATE_DEBUG", raising=False)
    with caplog.at_level(logging.INFO, logger="benefitbridge"):
        log_base_profile({"pincode": "560001", "district_norm": "BENGALURU URBAN"})
    event_messages = [r.message for r in caplog.records]
    assert not any("BASE_PROFILE_AFTER_PINCODE_LOOKUP" in m for m in event_messages)


def test_logging_enabled_when_env_true(monkeypatch, caplog):
    monkeypatch.setenv("SHOW_LOCAL_STATE_DEBUG", "true")
    with caplog.at_level(logging.INFO, logger="benefitbridge"):
        log_base_profile({"pincode": "560001", "district_norm": "BENGALURU URBAN", "state_norm": "KARNATAKA"})
    event_messages = [r.message for r in caplog.records]
    assert any("BASE_PROFILE_AFTER_PINCODE_LOOKUP" in m for m in event_messages)


def test_logging_enabled_when_env_is_1(monkeypatch, caplog):
    monkeypatch.setenv("SHOW_LOCAL_STATE_DEBUG", "1")
    with caplog.at_level(logging.INFO, logger="benefitbridge"):
        log_base_profile({"pincode": "110001", "district_norm": "CENTRAL DELHI"})
    assert any("BASE_PROFILE_AFTER_PINCODE_LOOKUP" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# NFHS alias + state-first filtering (mock data)
# ---------------------------------------------------------------------------

def test_bengaluru_urban_resolves_to_bangalore(monkeypatch):
    """BENGALURU URBAN / KARNATAKA must resolve to Bangalore (Karnataka) via alias."""
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    rows = get_nfhs_for_district("BENGALURU URBAN", "KARNATAKA")
    assert len(rows) > 0
    names = [r.get("district_name", "").upper() for r in rows]
    assert any("BANGALORE" in n for n in names)


def test_state_first_no_cross_state_match(monkeypatch):
    """Rows from Arunachal Pradesh must never appear for a KARNATAKA query."""
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    rows = get_nfhs_for_district("BENGALURU URBAN", "KARNATAKA")
    for r in rows:
        assert r.get("state_ut") == "KARNATAKA", (
            f"Cross-state row returned: {r.get('district_name')} / {r.get('state_ut')}"
        )


def test_dibang_valley_not_returned_for_karnataka(monkeypatch):
    """Dibang Valley (Arunachal Pradesh) must never appear in a Karnataka query."""
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    rows = get_nfhs_for_district("BENGALURU URBAN", "KARNATAKA")
    names = [r.get("district_name", "").upper() for r in rows]
    assert "DIBANG VALLEY" not in names


def test_state_fallback_returns_only_state_rows(monkeypatch):
    """Unknown district → state fallback must only return Karnataka rows."""
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    rows = get_nfhs_for_district("COMPLETELY UNKNOWN DISTRICT", "KARNATAKA")
    assert isinstance(rows, list)
    assert len(rows) <= 5
    for r in rows:
        assert r.get("state_ut") == "KARNATAKA"


# ---------------------------------------------------------------------------
# get_nfhs_lookup_trace
# ---------------------------------------------------------------------------

def test_lookup_trace_alias_match_type(monkeypatch):
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    trace = get_nfhs_lookup_trace("BENGALURU URBAN", "KARNATAKA")
    assert trace["match_type"] == "alias"
    assert trace["requested_district"] == "BENGALURU URBAN"
    assert trace["requested_state"] == "KARNATAKA"


def test_lookup_trace_alias_candidates_include_bangalore(monkeypatch):
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    trace = get_nfhs_lookup_trace("BENGALURU URBAN", "KARNATAKA")
    assert isinstance(trace["alias_candidates_tried"], list)
    assert "BANGALORE" in trace["alias_candidates_tried"]


def test_lookup_trace_state_fallback_type(monkeypatch):
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    trace = get_nfhs_lookup_trace("UNKNOWN DISTRICT XYZ", "KARNATAKA")
    assert trace["match_type"] == "state_fallback"
    assert trace["candidate_row_count"] <= 5


def test_lookup_trace_missing_for_unknown_state(monkeypatch):
    monkeypatch.setitem(dl._LOAD_CACHE, "nfhs_5_district_health_indicators", _MOCK_NFHS)
    trace = get_nfhs_lookup_trace("SOME DISTRICT", "NONEXISTENT STATE")
    assert trace["match_type"] == "missing"
    assert trace["candidate_row_count"] == 0


# ---------------------------------------------------------------------------
# action_plan._PLAN_SYSTEM contains family intro instruction
# ---------------------------------------------------------------------------

def test_plan_system_has_family_intro_instruction():
    from src.action_plan import _PLAN_SYSTEM
    lower = _PLAN_SYSTEM.lower()
    assert "introductory paragraph" in lower or "introduction" in lower


def test_plan_system_mentions_nfhs():
    from src.action_plan import _PLAN_SYSTEM
    assert "NFHS" in _PLAN_SYSTEM or "nfhs" in _PLAN_SYSTEM.lower()


# ---------------------------------------------------------------------------
# generate_action_plan_with_trace accepts followup_answers
# ---------------------------------------------------------------------------

def test_action_plan_signature_has_followup_answers():
    from src.action_plan import generate_action_plan_with_trace
    sig = inspect.signature(generate_action_plan_with_trace)
    assert "followup_answers" in sig.parameters


def test_action_plan_followup_answers_defaults_none():
    from src.action_plan import generate_action_plan_with_trace
    sig = inspect.signature(generate_action_plan_with_trace)
    param = sig.parameters["followup_answers"]
    assert param.default is None


# ---------------------------------------------------------------------------
# Debug tab in app.py has the new sections
# ---------------------------------------------------------------------------

def test_app_has_trusted_data_sources_section():
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "Trusted Data Sources" in src


def test_app_has_nfhs_lookup_trace_section():
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "NFHS District Lookup Trace" in src


def test_app_imports_get_nfhs_lookup_trace():
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "get_nfhs_lookup_trace" in src


def test_app_imports_log_final_profile():
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "log_final_profile" in src
