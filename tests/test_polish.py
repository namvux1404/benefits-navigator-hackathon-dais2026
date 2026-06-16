"""Tests for Gate A polish pass: model default, grounding, insurance wording,
pathway priority, dashboard district preference, and data-source badge."""
import pytest


# -- 1. Default Claude model is Sonnet --------------------------------------

def test_default_claude_model_is_sonnet():
    """The fallback model ID (when CLAUDE_MODEL env var is unset) must be Sonnet."""
    from src.config import DEFAULT_CLAUDE_MODEL
    assert DEFAULT_CLAUDE_MODEL == "claude-sonnet-4-5-20250929"


def test_default_model_is_expected_sonnet_only():
    from src.config import DEFAULT_CLAUDE_MODEL
    assert DEFAULT_CLAUDE_MODEL == "claude-sonnet-4-5-20250929"


def test_config_uses_sonnet_when_model_env_missing(monkeypatch):
    import importlib
    import src.config as config

    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    config = importlib.reload(config)
    assert config.CLAUDE_MODEL == "claude-sonnet-4-5-20250929"


def test_config_uses_sonnet_when_model_env_empty(monkeypatch):
    import importlib
    import src.config as config

    monkeypatch.setenv("CLAUDE_MODEL", "   ")
    config = importlib.reload(config)
    assert config.CLAUDE_MODEL == "claude-sonnet-4-5-20250929"


def test_config_uses_sonnet_when_model_env_is_legacy_non_sonnet(monkeypatch):
    import importlib
    import src.config as config

    monkeypatch.setenv("CLAUDE_MODEL", "claude-o" + "pus-4-8")
    config = importlib.reload(config)
    assert config.CLAUDE_MODEL == "claude-sonnet-4-5-20250929"
# -- 2. Action plan system prompt has grounding rules -----------------------

def test_action_plan_prompt_forbids_scheme_names():
    """System prompt must explicitly prohibit inventing government scheme names."""
    from src.action_plan import _PLAN_SYSTEM
    p = _PLAN_SYSTEM.lower()
    assert "ayushman" in p, "Prompt should explicitly forbid Ayushman Bharat by name"
    assert "icds" in p, "Prompt should explicitly forbid ICDS by name"
    assert "do not" in p or "not name" in p


def test_action_plan_prompt_no_free_food_promise():
    from src.action_plan import _PLAN_SYSTEM
    p = _PLAN_SYSTEM.lower()
    assert "free food" not in p or "do not" in p


def test_deterministic_plan_no_invented_scheme_names():
    """Deterministic fallback must not contain ungrounded scheme names."""
    from src.action_plan import _deterministic_plan
    from src.data_loader import load_pathways

    profile = {"pregnant": True, "child_under_5": True, "nutrition_need": True}
    matched = [pw for pw in load_pathways() if pw["pathway_id"] in ("maternal_care", "child_nutrition")]
    plan = _deterministic_plan(profile, matched, [], [])

    for forbidden in ["ayushman", "icds", "pm matru", "pmmvy", "janani suraksha", "free food"]:
        assert forbidden not in plan.lower(), f"Unexpected scheme reference: '{forbidden}'"


# -- 3. Insurance wording is conditional -----------------------------------

def test_action_plan_prompt_conditional_insurance():
    """System prompt must use the conditional insurance phrasing."""
    from src.action_plan import _PLAN_SYSTEM
    p = _PLAN_SYSTEM.lower()
    assert "if you have insurance" in p
    assert "if you do not" in p or "if you don" in p


def test_deterministic_plan_no_definitive_insurance_claim():
    """Deterministic plan must not assert the user is insured."""
    from src.action_plan import _deterministic_plan
    from src.data_loader import load_pathways

    profile = {"uninsured": False}  # not explicitly uninsured, but not clearly insured either
    insurance_pw = next(pw for pw in load_pathways() if pw["pathway_id"] == "health_insurance_awareness")
    plan = _deterministic_plan(profile, [insurance_pw], [], [])

    assert "even though you are insured" not in plan.lower()
    assert "you are insured" not in plan.lower()


def test_deterministic_plan_does_not_embed_facility_section_or_names():
    from src.action_plan import _deterministic_plan

    profile = {"child_age_months": 12, "immunization_need": True}
    matched = [{"pathway_id": "immunization", "pathway_name": "Child Immunization Support"}]
    facilities = [
        {"name": "St. Martha's Hospital"},
        {"name": "Agastya Speciality Clinics"},
    ]
    plan = _deterministic_plan(profile, matched, [], facilities)

    assert "Nearest Health Facilities" not in plan
    assert "St. Martha's Hospital" not in plan
    assert "Agastya Speciality Clinics" not in plan
    assert "nearby facilities listed below" in plan


# -- 4. Pathway priority ordering ------------------------------------------

def test_maternal_care_before_screening():
    """maternal_care must appear before women_preventive_screening in matched output."""
    from src.rules_engine import match_pathways
    from src.data_loader import load_pathways

    profile = {
        "pregnant": True,
        "adult_woman": True,
        "child_under_5": True,
        "child_age_months": 36,
        "nutrition_need": True,
        "recently_delivered": False,
        "uninsured": False,
        "low_income": False,
        "water_sanitation_need": False,
        "child_diarrhea_risk": False,
        "screening_need": False,
    }
    matched = match_pathways(profile, load_pathways())
    ids = [pw["pathway_id"] for pw in matched]

    assert "maternal_care" in ids
    assert "women_preventive_screening" in ids
    assert ids.index("maternal_care") < ids.index("women_preventive_screening"), (
        f"Expected maternal_care before women_preventive_screening, got order: {ids}"
    )


def test_child_nutrition_before_screening():
    from src.rules_engine import match_pathways
    from src.data_loader import load_pathways

    profile = {
        "pregnant": False,
        "adult_woman": True,
        "child_under_5": True,
        "child_age_months": 24,
        "nutrition_need": True,
        "recently_delivered": False,
        "uninsured": False,
        "low_income": False,
        "water_sanitation_need": False,
        "child_diarrhea_risk": False,
        "screening_need": False,
    }
    matched = match_pathways(profile, load_pathways())
    ids = [pw["pathway_id"] for pw in matched]

    assert "child_nutrition" in ids
    assert ids.index("child_nutrition") < ids.index("women_preventive_screening")


def test_demo_scenario_pathway_order():
    """Demo: pregnant + 3yo - maternal first, screening last."""
    from src.rules_engine import match_pathways, _PATHWAY_PRIORITY
    from src.data_loader import load_pathways

    profile = {
        "pregnant": True,
        "recently_delivered": False,
        "child_under_5": True,
        "child_age_months": 36,
        "nutrition_need": True,
        "uninsured": False,
        "low_income": False,
        "water_sanitation_need": False,
        "child_diarrhea_risk": False,
        "adult_woman": True,
        "screening_need": False,
    }
    matched = match_pathways(profile, load_pathways())
    ids = [pw["pathway_id"] for pw in matched]

    # First pathway must be maternal_care
    assert ids[0] == "maternal_care", f"Expected maternal_care first, got: {ids}"
    # Screening must be last if present
    if "women_preventive_screening" in ids:
        assert ids[-1] == "women_preventive_screening", f"Expected screening last, got: {ids}"


# -- 5. Dashboard district preference --------------------------------------

def test_preferred_district_favours_bangalore():
    from src.ui_helpers import preferred_district_index
    districts = ["Anjaw", "Bangalore", "Delhi", "Mysore"]
    idx = preferred_district_index(districts, "")
    assert districts[idx] == "Bangalore"


def test_preferred_district_recent_session_wins():
    from src.ui_helpers import preferred_district_index
    districts = ["Anjaw", "Bangalore", "Delhi", "Mysore"]
    # MYSURU in pincode_district_lookup aliases to MYSORE in NFHS
    idx = preferred_district_index(districts, "MYSURU")
    assert districts[idx] == "Mysore", f"Expected Mysore via alias, got: {districts[idx]}"


def test_preferred_district_recent_exact_match():
    from src.ui_helpers import preferred_district_index
    districts = ["Anjaw", "Bangalore", "Delhi", "Mysore"]
    idx = preferred_district_index(districts, "BENGALURU URBAN")
    # BENGALURU URBAN -> alias BANGALORE -> matches "Bangalore"
    assert districts[idx] == "Bangalore"


def test_preferred_district_fallback_first():
    from src.ui_helpers import preferred_district_index
    districts = ["Anjaw", "Delhi", "Kolkata"]
    idx = preferred_district_index(districts, "")
    assert idx == 0  # no Bangalore -> first item


def test_preferred_district_none_recent():
    from src.ui_helpers import preferred_district_index
    districts = ["Anjaw", "Bangalore", "Delhi"]
    # Empty recent - Bangalore should win
    idx = preferred_district_index(districts, "")
    assert districts[idx] == "Bangalore"


# -- 6. Data-source badge ---------------------------------------------------

def test_data_source_label_gate_a():
    from src.ui_helpers import data_source_label
    assert data_source_label("json_only") == "Data source: Local sample JSON (Gate A)"


def test_data_source_label_case_insensitive():
    from src.ui_helpers import data_source_label
    assert data_source_label("JSON_ONLY") == "Data source: Local sample JSON (Gate A)"
    assert data_source_label("Json_Only") == "Data source: Local sample JSON (Gate A)"


def test_data_source_label_uc():
    from src.ui_helpers import data_source_label
    assert data_source_label("uc") == "Data source: Unity Catalog trusted tables"
    assert data_source_label("UC") == "Data source: Unity Catalog trusted tables"


def test_state_store_label_sqlite():
    from src.ui_helpers import state_store_label
    assert state_store_label("sqlite") == "State: Local SQLite fallback"
    assert state_store_label("SQLITE") == "State: Local SQLite fallback"


def test_state_store_label_lakebase():
    from src.ui_helpers import state_store_label
    assert state_store_label("lakebase") == "State: Lakebase"
    assert state_store_label("LAKEBASE") == "State: Lakebase"


def test_ai_mode_label_no_key():
    from src.ui_helpers import ai_mode_label
    assert ai_mode_label(False, "claude-sonnet-4-5-20250929") == "AI: Deterministic fallback (no API key)"


def test_ai_mode_label_sonnet():
    from src.ui_helpers import ai_mode_label
    assert ai_mode_label(True, "claude-sonnet-4-5-20250929") == "AI: Claude Sonnet"


def test_ai_mode_label_any_keyed_model_reports_sonnet():
    from src.ui_helpers import ai_mode_label
    assert ai_mode_label(True, "legacy-model") == "AI: Claude Sonnet"
def test_config_exposes_data_mode():
    from src.config import DATA_MODE
    assert DATA_MODE in ("json_only", "uc", ""), f"Unexpected DATA_MODE: {DATA_MODE!r}"


def test_config_exposes_state_store_mode():
    from src.config import STATE_STORE_MODE
    assert STATE_STORE_MODE in ("sqlite", "lakebase", ""), f"Unexpected STATE_STORE_MODE: {STATE_STORE_MODE!r}"


def test_gate_a_full_badge():
    """Gate A defaults produce the expected badge string."""
    from src.ui_helpers import ai_mode_label, data_source_label, state_store_label
    badge = (
        f"{data_source_label('json_only')}  ·  "
        f"{state_store_label('sqlite')}  ·  "
        f"{ai_mode_label(True, 'claude-sonnet-4-5-20250929')}"
    )
    assert "Local sample JSON (Gate A)" in badge
    assert "Local SQLite fallback" in badge
    assert "Claude Sonnet" in badge


def test_gate_bc_full_badge():
    """Gate B/C values produce the Unity Catalog / Lakebase badge string."""
    from src.ui_helpers import ai_mode_label, data_source_label, state_store_label
    badge = (
        f"{data_source_label('uc')}  ·  "
        f"{state_store_label('lakebase')}  ·  "
        f"{ai_mode_label(True, 'claude-sonnet-4-5-20250929')}"
    )
    assert "Unity Catalog trusted tables" in badge
    assert "Lakebase" in badge
    assert "Claude Sonnet" in badge


# -- 8. Action-plan Claude context cap -----------------------------------------

def test_build_facility_lines_shows_5():
    """_build_facility_lines must include facility names from the provided list."""
    from src.action_plan import _build_facility_lines
    facs = [{"name": f"Facility {i}", "address_city": "Bangalore", "officialPhone": "080-999"} for i in range(5)]
    result = _build_facility_lines(facs)
    assert "Top 5 nearby facilities" in result
    for i in range(5):
        assert f"Facility {i}" in result


def test_build_facility_lines_empty_returns_no_data():
    from src.action_plan import _build_facility_lines
    assert "No facilities" in _build_facility_lines([])


def test_action_plan_no_thinking_parameter():
    """generate_action_plan_with_trace must not use thinking=adaptive (unsupported on Sonnet 4.5)."""
    import inspect
    from src.action_plan import generate_action_plan_with_trace
    src = inspect.getsource(generate_action_plan_with_trace)
    assert "thinking" not in src, "thinking parameter must be removed (BadRequestError on Sonnet 4.5)"


# -- 9. UI label cleanup -------------------------------------------------------

def test_app_no_sample_data_preview_label():
    """'Sample Data Preview' section header must be renamed to 'Trusted Data Preview'."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "#### Trusted Data Preview" in src
    assert "#### Sample Data Preview" not in src


def test_app_no_sample_data_sources_label():
    """'Sample Data Sources' header must be renamed (Trusted Data Sources already exists)."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "#### Sample Data Sources" not in src


def test_app_facility_coverage_label_is_dynamic():
    """Facility Coverage label in Program Leader Dashboard must not hard-code 'sample_data'."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "Facility Coverage (sample_data)" not in src


# -- 10. Facility evidence and trust signal ------------------------------------

def test_facility_evidence_includes_location():
    """facility_evidence_summary must include a location evidence item."""
    from src.ui_helpers import facility_evidence_summary
    f = {
        "name": "Test Hospital",
        "address_city": "Bangalore",
        "address_stateOrRegion": "Karnataka",
        "address_zipOrPostcode": "560001",
        "officialPhone": "+9180-12345",
    }
    ev = facility_evidence_summary(f)
    labels = [item[0] for item in ev["evidence_items"]]
    assert "Location" in labels


def test_facility_evidence_includes_contact_field():
    """facility_evidence_summary must include a contact evidence item."""
    from src.ui_helpers import facility_evidence_summary
    f = {
        "name": "Test Hospital",
        "officialPhone": "+9180-99999",
    }
    ev = facility_evidence_summary(f)
    labels = [item[0] for item in ev["evidence_items"]]
    assert "Contact evidence" in labels


def test_facility_evidence_has_uncertainty_note():
    """Evidence block must include an uncertainty / incomplete-data note."""
    from src.ui_helpers import facility_evidence_summary
    from pathlib import Path
    # The uncertainty note lives in app.py's expander; check it contains the key phrase
    src = Path("app.py").read_text(encoding="utf-8")
    assert "may be incomplete or noisy" in src


def test_proxy_trust_high_for_complete_record():
    """compute_proxy_trust_signal returns 'High' for a well-documented facility."""
    from src.ui_helpers import compute_proxy_trust_signal
    f = {
        "officialPhone": "+9180-999",
        "email": "test@test.com",
        "address_line1": "5 Main Rd",
        "address_city": "Bangalore",
        "address_stateOrRegion": "Karnataka",
        "address_zipOrPostcode": "560001",
        "specialties": '["internalMedicine","gynecology"]',
        "affiliated_staff_presence": "true",
        "description": "A large multi-speciality hospital.",
        "source": "kie",
    }
    result = compute_proxy_trust_signal(f)
    assert result["signal"] == "High"
    assert result["score"] >= 6


def test_proxy_trust_limited_for_sparse_record():
    """compute_proxy_trust_signal returns 'Unknown' or 'Limited' for a minimal record."""
    from src.ui_helpers import compute_proxy_trust_signal
    f = {"name": "Unknown Clinic"}
    result = compute_proxy_trust_signal(f)
    assert result["signal"] in ("Limited", "Unknown")


def test_no_overclaiming_language_in_evidence():
    """Evidence block must not contain overclaiming phrases like 'best' or 'safest'."""
    from src.ui_helpers import facility_evidence_summary, compute_proxy_trust_signal
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    forbidden = ["best facility", "safest facility", "guaranteed trusted", "most trusted"]
    for phrase in forbidden:
        assert phrase not in src.lower(), f"Overclaiming phrase found in app.py: '{phrase}'"


def test_trust_score_row_used_when_matched():
    """When a trust_score_row is provided, it should override the proxy signal."""
    from src.ui_helpers import facility_evidence_summary
    f = {"name": "Test Hospital", "address_city": "Bangalore"}
    trust_row = {"facility_name": "Test Hospital", "trust_signal": "High", "reason": "UC verified"}
    ev = facility_evidence_summary(f, trust_row)
    assert ev["trust_info"]["signal"] == "High"
    assert "UC verified" in ev["trust_info"]["why"]
    assert ev["trust_info"].get("score_source") or ev["trust_info"].get("source")


def test_facility_evidence_graceful_without_trust_scores():
    """facility_evidence_summary works when no trust score is available."""
    from src.ui_helpers import facility_evidence_summary
    f = {"name": "Test Hospital", "officialPhone": "+9180-111"}
    ev = facility_evidence_summary(f, trust_score_row=None)
    assert ev["trust_info"]["signal"] in ("High", "Medium", "Limited")
    assert "evidence_items" in ev


# -- 11. Shortlist persistence -------------------------------------------------

def test_shortlist_save_and_retrieve(tmp_path):
    """save_shortlist_item must persist and get_shortlist must return the row."""
    from src.state_store import StateStore
    store = StateStore(path=tmp_path / "test_shortlist.db")
    sid = "session-abc"
    item_id = store.save_shortlist_item(sid, "Test Hospital", {"name": "Test Hospital"}, "Follow up Monday")
    assert item_id
    rows = store.get_shortlist(sid)
    assert len(rows) == 1
    assert rows[0]["facility_name"] == "Test Hospital"
    assert rows[0]["session_id"] == sid
    assert rows[0]["user_note"] == "Follow up Monday"


def test_shortlist_handles_none_session_id(tmp_path):
    """save_shortlist_item must accept None session_id."""
    from src.state_store import StateStore
    store = StateStore(path=tmp_path / "test_shortlist2.db")
    item_id = store.save_shortlist_item(None, "Another Hospital")
    assert item_id
    rows = store.get_shortlist()
    assert len(rows) == 1
    assert rows[0]["facility_name"] == "Another Hospital"
    assert rows[0]["session_id"] is None


def test_get_facility_trust_score_matches_by_name():
    """get_facility_trust_score must match trust rows by facility name."""
    from src.data_loader import get_facility_trust_score
    trust_scores = [
        {"facility_name": "City Hospital", "trust_signal": "High"},
        {"facility_name": "Rural Clinic", "trust_signal": "Limited"},
    ]
    facility = {"name": "City Hospital"}
    result = get_facility_trust_score(facility, trust_scores)
    assert result is not None
    assert result["trust_signal"] == "High"


def test_get_facility_trust_score_returns_none_when_no_match():
    """get_facility_trust_score returns None when facility name is not in trust_scores."""
    from src.data_loader import get_facility_trust_score
    trust_scores = [{"facility_name": "Other Hospital", "trust_signal": "High"}]
    result = get_facility_trust_score({"name": "Unknown Clinic"}, trust_scores)
    assert result is None


def test_load_facility_trust_scores_returns_list():
    """load_facility_trust_scores must always return a list (empty if table absent)."""
    from src.data_loader import load_facility_trust_scores, _OPTIONAL_CACHE
    _OPTIONAL_CACHE.pop("facility_trust_scores", None)
    result = load_facility_trust_scores()
    assert isinstance(result, list)


# -- 12. App positioning and tab name ------------------------------------------

def test_app_hero_subtitle_is_field_worker():
    """Hero card subtitle must mention community health workers."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "community health worker" in src.lower()


def test_app_tab_name_includes_referral_navigator():
    """First tab must be 'Referral Navigator' (TrustRoute AI rebrand)."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "Referral Navigator" in src


def test_app_shortlist_in_state_defaults():
    """shortlisted_facilities must be in _STATE_DEFAULTS for session reset."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "shortlisted_facilities" in src


# -- 13. Phase 3: strip facility section from action plan ----------------------

def test_strip_facility_section_removes_pipe_list():
    """_strip_facility_section must remove a numbered pipe-delimited facility list."""
    from src.action_plan import _strip_facility_section
    text = (
        "Step 1: Visit a health centre.\n\n"
        "Nearby Health Facilities\n"
        "1. City Hospital | Bangalore | 080-9999\n"
        "2. Rural Clinic | Mysore | 0821-1111\n"
        "\nPlease call ahead to confirm services."
    )
    result = _strip_facility_section(text)
    assert "City Hospital" not in result
    assert "Rural Clinic" not in result
    assert "Step 1" in result
    assert "Please call ahead" in result


def test_strip_facility_section_preserves_step_headers():
    """_strip_facility_section must NOT remove a step header that mentions 'Facility'."""
    from src.action_plan import _strip_facility_section
    text = (
        "Step 1: Confirm vaccination need.\n\n"
        "Step 2: Find a Nearby Facility — call ahead.\n\n"
        "Step 3: Bring your records."
    )
    result = _strip_facility_section(text)
    assert "Step 2" in result
    assert "Find a Nearby Facility" in result


def test_action_plan_prompt_no_facility_list_instruction():
    """_PLAN_SYSTEM must contain the explicit DO NOT LIST FACILITIES instruction."""
    from src.action_plan import _PLAN_SYSTEM
    assert "DO NOT LIST FACILITIES" in _PLAN_SYSTEM


# -- 14. Phase 3: trust score matching by ID fields ----------------------------

def test_trust_score_match_by_unique_id():
    """get_facility_trust_score must match by unique_id first."""
    from src.data_loader import get_facility_trust_score
    trust_scores = [
        {"unique_id": "uid-001", "facility_name": "City Hospital", "trust_signal": "High"},
        {"unique_id": "uid-002", "facility_name": "Other Place", "trust_signal": "Limited"},
    ]
    facility = {"unique_id": "uid-001", "name": "Anything"}
    result = get_facility_trust_score(facility, trust_scores)
    assert result is not None
    assert result["trust_signal"] == "High"


def test_trust_score_match_by_source_content_id():
    """get_facility_trust_score must match by source_content_id when unique_id absent."""
    from src.data_loader import get_facility_trust_score
    trust_scores = [
        {"source_content_id": "src-777", "facility_name": "Target Clinic", "trust_signal": "Medium"},
    ]
    facility = {"source_content_id": "src-777", "name": "Target Clinic"}
    result = get_facility_trust_score(facility, trust_scores)
    assert result is not None
    assert result["trust_signal"] == "Medium"


# -- 15. Phase 3: proxy trust score_display field ------------------------------

def test_trust_score_score_display_in_proxy():
    """compute_proxy_trust_signal must include a score_display field (e.g. '6/8')."""
    from src.ui_helpers import compute_proxy_trust_signal
    f = {
        "officialPhone": "+9180-999",
        "address_line1": "5 Main Rd",
        "address_city": "Bangalore",
        "address_stateOrRegion": "Karnataka",
        "address_zipOrPostcode": "560001",
        "source": "kie",
    }
    result = compute_proxy_trust_signal(f)
    assert "score_display" in result
    assert "/" in result["score_display"]


def test_trust_info_has_score_source():
    """facility_evidence_summary trust_info must include a score_source field."""
    from src.ui_helpers import facility_evidence_summary
    f = {"name": "Test Hospital", "officialPhone": "+9180-111"}
    ev = facility_evidence_summary(f, trust_score_row=None)
    assert "score_source" in ev["trust_info"]
    assert "proxy" in ev["trust_info"]["score_source"] or "Unity Catalog" in ev["trust_info"]["score_source"]


# -- 16. Phase 3: clean email and data source helpers --------------------------

def test_clean_email_removes_mojibake():
    """_clean_email must return empty string for a malformed / mojibake email."""
    from src.ui_helpers import _clean_email
    assert _clean_email("kie protected") == ""
    assert _clean_email("not-an-email") == ""
    assert _clean_email("bad\x01chars@foo.com") == ""


def test_clean_email_valid_passes():
    """_clean_email must return a valid email address unchanged."""
    from src.ui_helpers import _clean_email
    assert _clean_email("info@hospital.org") == "info@hospital.org"
    assert _clean_email("contact.us+tag@sub.domain.co.in") == "contact.us+tag@sub.domain.co.in"


def test_clean_data_source_maps_kie():
    """_clean_data_source must map 'kie' → 'Provided facility record'."""
    from src.ui_helpers import _clean_data_source
    assert _clean_data_source("kie") == "Provided facility record"
    assert _clean_data_source("KIE") == "Provided facility record"
    assert _clean_data_source("overture") == "Provided facility record"
    assert _clean_data_source("dynamic") == "Provided facility record"


# -- 17. Phase 3: Screen 2 live preview parse ----------------------------------

def test_screen2_parses_insurance_from_form():
    """parse_followup_answers must extract uninsured=True from plain English answers."""
    from src.followup import parse_followup_answers
    questions = [{"id": "insurance", "question": "Do you have health insurance?"}]
    form_answers = {"insurance": "No, I have no insurance and need low-cost care."}
    updates = parse_followup_answers(questions, form_answers)
    assert updates.get("uninsured") is True


# ============================================================
# Part 8 — comprehensive tests for final polish
# ============================================================

# -- 18. Score normalization ---------------------------------------------------

def test_normalize_trust_score_0_to_1():
    """Score in [0,1] range must be multiplied by 10."""
    from src.ui_helpers import normalize_trust_score
    assert normalize_trust_score(0.85) == 8.5
    assert normalize_trust_score(0.5) == 5.0
    assert normalize_trust_score(0.0) == 0.0
    assert normalize_trust_score(1.0) == 10.0


def test_normalize_trust_score_0_to_10():
    """Score in (1,10] must be returned as-is (rounded)."""
    from src.ui_helpers import normalize_trust_score
    assert normalize_trust_score(8.0) == 8.0
    assert normalize_trust_score(5.5) == 5.5
    assert normalize_trust_score(10.0) == 10.0


def test_normalize_trust_score_0_to_100():
    """Score in (10,100] must be divided by 10."""
    from src.ui_helpers import normalize_trust_score
    assert normalize_trust_score(85.0) == 8.5
    assert normalize_trust_score(50.0) == 5.0


def test_normalize_trust_score_none():
    """None input returns None."""
    from src.ui_helpers import normalize_trust_score
    assert normalize_trust_score(None) is None


def test_trust_signal_from_score():
    """trust_signal_from_score maps correctly to thresholds."""
    from src.ui_helpers import trust_signal_from_score
    assert trust_signal_from_score(9.0) == "High"
    assert trust_signal_from_score(8.0) == "High"
    assert trust_signal_from_score(7.9) == "Medium"
    assert trust_signal_from_score(5.0) == "Medium"
    assert trust_signal_from_score(4.9) == "Limited"
    assert trust_signal_from_score(0.1) == "Limited"
    assert trust_signal_from_score(0.0) == "Unknown"
    assert trust_signal_from_score(None) == "Unknown"


def test_score_from_signal_high():
    """score_from_signal maps High -> 8.5."""
    from src.ui_helpers import score_from_signal
    assert score_from_signal("High") == 8.5
    assert score_from_signal("high") == 8.5


def test_score_from_signal_unknown():
    """score_from_signal returns None for unknown or empty signals."""
    from src.ui_helpers import score_from_signal
    assert score_from_signal("Unknown") is None
    assert score_from_signal("") is None


# -- 19. Facility trust matching improvements ----------------------------------

def test_trust_score_match_by_content_table_id():
    """get_facility_trust_score matches by content_table_id."""
    from src.data_loader import get_facility_trust_score
    ts = [{"content_table_id": "ct-99", "trust_signal": "Medium"}]
    fac = {"content_table_id": "ct-99"}
    assert get_facility_trust_score(fac, ts) is not None


def test_trust_score_match_by_name_city_state():
    """get_facility_trust_score matches by normalized name + city + state."""
    from src.data_loader import get_facility_trust_score
    ts = [
        {
            "facility_name": "City General Hospital",
            "address_city": "Bangalore",
            "address_stateOrRegion": "Karnataka",
            "trust_signal": "High",
        }
    ]
    fac = {
        "name": "City General Hospital",
        "address_city": "Bangalore",
        "address_stateOrRegion": "Karnataka",
    }
    result = get_facility_trust_score(fac, ts)
    assert result is not None
    assert result["trust_signal"] == "High"


def test_trust_score_bengaluru_bangalore_alias():
    """City alias Bengaluru→Bangalore must not block a name+city match."""
    from src.data_loader import get_facility_trust_score
    ts = [
        {
            "facility_name": "Apollo Clinic",
            "address_city": "Bengaluru",
            "trust_signal": "Medium",
        }
    ]
    fac = {"name": "Apollo Clinic", "address_city": "Bangalore"}
    result = get_facility_trust_score(fac, ts)
    assert result is not None


# -- 20. Proxy signal "Unknown" for zero-evidence facilities -------------------

def test_proxy_trust_unknown_for_zero_evidence():
    """Proxy returns Unknown when no fields contribute any evidence score."""
    from src.ui_helpers import compute_proxy_trust_signal
    result = compute_proxy_trust_signal({})
    assert result["signal"] == "Unknown"
    assert result["score"] == 0


def test_proxy_trust_non_unknown_when_phone_present():
    """A facility with just a phone number should get a non-Unknown signal."""
    from src.ui_helpers import compute_proxy_trust_signal
    result = compute_proxy_trust_signal({"officialPhone": "+91-999"})
    assert result["signal"] != "Unknown"
    assert result["score"] >= 1


def test_proxy_trust_high_threshold_is_8_or_10():
    """High signal must require score >= 8 on the current max_score scale."""
    from src.ui_helpers import compute_proxy_trust_signal
    # Full record should be High
    f = {
        "officialPhone": "+9180-999",
        "email": "test@test.com",
        "address_line1": "5 Main Rd",
        "address_city": "Bangalore",
        "address_stateOrRegion": "Karnataka",
        "address_zipOrPostcode": "560001",
        "specialties": '["internalMedicine"]',
        "affiliated_staff_presence": "true",
        "description": "A hospital.",
        "source": "kie",
    }
    r = compute_proxy_trust_signal(f)
    assert r["signal"] == "High"
    assert r["score"] >= 8


def test_facility_evidence_score_source_from_proxy():
    """facility_evidence_summary returns score_source=proxy when no UC row."""
    from src.ui_helpers import facility_evidence_summary
    ev = facility_evidence_summary({"name": "Test", "officialPhone": "+91-111"})
    assert "proxy" in ev["trust_info"]["score_source"].lower()


def test_facility_evidence_score_source_from_uc_row():
    """facility_evidence_summary returns score_source=Unity Catalog when UC row matched."""
    from src.ui_helpers import facility_evidence_summary
    ev = facility_evidence_summary(
        {"name": "Test"},
        trust_score_row={"trust_signal": "High", "trust_score": 8.5},
    )
    assert "Unity Catalog" in ev["trust_info"]["score_source"]


def test_facility_evidence_uc_row_with_numeric_score_normalized():
    """facility_evidence_summary normalizes UC numeric score correctly."""
    from src.ui_helpers import facility_evidence_summary
    # Simulate a 0-100 scale score
    ev = facility_evidence_summary(
        {"name": "Test"},
        trust_score_row={"trust_signal": "High", "trust_score": 85.0},
    )
    ti = ev["trust_info"]
    assert ti["signal"] == "High"
    # Score should normalize to 8.5/10
    assert "8.5" in ti["score_display"]


def test_facility_evidence_uc_row_signal_only_no_numeric():
    """facility_evidence_summary derives score from named signal when no numeric score given."""
    from src.ui_helpers import facility_evidence_summary
    ev = facility_evidence_summary(
        {"name": "Test"},
        trust_score_row={"trust_signal": "Medium"},
    )
    ti = ev["trust_info"]
    assert ti["signal"] == "Medium"
    # Representative score for Medium=6.5 should appear in display
    assert "6.5" in ti["score_display"] or ti["score_display"] == ""


# -- 21. Screen 3 structural tests ---------------------------------------------

def test_screen3_no_static_next_steps():
    """Screen 3 must not render the static vaccination-only Next Steps section."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    # The static block is gone: no call to next_steps_for_profile in Screen 3
    # (function still exists in ui_helpers but must not be called in app.py)
    assert "next_steps_for_profile" not in src


def test_screen3_has_trust_signal_badge():
    """Screen 3 facility card badge must say 'Trust signal:' not 'Evidence strength:'."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "Trust signal:" in src
    assert "Evidence strength:" not in src


def test_screen3_pathway_card_shows_why_matched():
    """Pathway cards must show 'Why matched:' not just 'Reason:'."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "**Why matched:**" in src


def test_screen3_pathway_trigger_in_expander():
    """Technical trigger must be inside a collapsible expander, not top-level."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert 'st.expander("Technical match rule"' in src


def test_screen3_uncertainty_note_present():
    """Facility card must include the uncertainty note."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "Trust signal reflects available evidence" in src
    assert "not a guarantee of service quality" in src


# -- 22. Data Trust Facility Scoring Trace tests -------------------------------

def test_data_trust_has_facility_scoring_trace_section():
    """Data Trust tab must include a Facility Scoring Trace heading."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "Facility Scoring Trace" in src


def test_data_trust_shows_facility_trust_scores_status():
    """Data Trust tab must show facility_trust_scores row count."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "facility_trust_scores" in src


# -- 23. Shortlist trust field persistence ------------------------------------

def test_shortlist_saves_trust_signal(tmp_path):
    """save_shortlist_item must persist trust fields included in facility_data."""
    from src.state_store import StateStore
    import json as _json
    store = StateStore(path=tmp_path / "trust_shortlist.db")
    facility_data = {
        "name": "Apollo Hospital",
        "_trust_signal": "High",
        "_trust_score_display": "8.5/10",
        "_score_source": "facility_trust_scores (Unity Catalog)",
        "_matched_by": "trust_table",
    }
    item_id = store.save_shortlist_item("sess-1", "Apollo Hospital", facility_data)
    assert item_id
    rows = store.get_shortlist("sess-1")
    assert len(rows) == 1
    saved_data = _json.loads(rows[0]["facility_data"])
    assert saved_data["_trust_signal"] == "High"
    assert saved_data["_score_source"] == "facility_trust_scores (Unity Catalog)"
    assert saved_data["_matched_by"] == "trust_table"


def test_shortlist_saves_proxy_trust_fields(tmp_path):
    """save_shortlist_item must also persist proxy trust fields."""
    from src.state_store import StateStore
    import json as _json
    store = StateStore(path=tmp_path / "proxy_shortlist.db")
    facility_data = {
        "name": "Rural Clinic",
        "_trust_signal": "Medium",
        "_trust_score_display": "6/10",
        "_score_source": "facility record completeness (proxy)",
        "_matched_by": "proxy",
    }
    store.save_shortlist_item(None, "Rural Clinic", facility_data)
    rows = store.get_shortlist()
    saved = _json.loads(rows[0]["facility_data"])
    assert saved["_matched_by"] == "proxy"
    assert "proxy" in saved["_score_source"]


# -- 24. Facility scoring trace in session state ------------------------------

def test_facility_scoring_trace_in_state_defaults():
    """facility_scoring_trace must be in _STATE_DEFAULTS."""
    from pathlib import Path
    src = Path("app.py").read_text(encoding="utf-8")
    assert "facility_scoring_trace" in src


# -- 25. Action plan conciseness ----------------------------------------------

def test_action_plan_max_tokens_reduced():
    """Action plan generation must use max_tokens <= 700."""
    import inspect
    from src.action_plan import generate_action_plan_with_trace
    src = inspect.getsource(generate_action_plan_with_trace)
    # Extract max_tokens value
    import re
    m = re.search(r"max_tokens\s*=\s*(\d+)", src)
    assert m, "max_tokens not found in generate_action_plan_with_trace source"
    assert int(m.group(1)) <= 700, f"max_tokens={m.group(1)} exceeds 700"


# -- 26. Facility why_shown helper -------------------------------------------

def test_facility_why_shown_pin_match():
    """facility_why_shown returns 'PIN code match' when pincodes align."""
    from src.ui_helpers import facility_why_shown
    f = {"address_zipOrPostcode": "560001"}
    why = facility_why_shown(f, search_pincode="560001", search_state="KARNATAKA")
    assert "PIN code match" in why


def test_facility_why_shown_state_match():
    """facility_why_shown returns state match when only state aligns."""
    from src.ui_helpers import facility_why_shown
    f = {"address_stateOrRegion": "Karnataka", "address_zipOrPostcode": "999999"}
    why = facility_why_shown(f, search_pincode="560001", search_state="KARNATAKA")
    assert "State" in why or "location" in why.lower()


# -- 27. results_section_order no longer has next_steps -----------------------

def test_results_section_order_no_next_steps():
    """results_section_order must not contain 'next_steps'."""
    from src.ui_helpers import results_section_order
    assert "next_steps" not in results_section_order()


def test_results_section_order_correct_sequence():
    """results_section_order: matched_pathways → action_plan → facilities."""
    from src.ui_helpers import results_section_order
    o = results_section_order()
    assert o.index("matched_pathways") < o.index("action_plan")
    assert o.index("action_plan") < o.index("facilities")
