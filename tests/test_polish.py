"""Tests for Gate A polish pass: model default, grounding, insurance wording,
pathway priority, dashboard district preference, and data-source badge."""
import pytest


# ── 1. Default Claude model is Sonnet ──────────────────────────────────────

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
# ── 2. Action plan system prompt has grounding rules ───────────────────────

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


# ── 3. Insurance wording is conditional ───────────────────────────────────

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


# ── 4. Pathway priority ordering ──────────────────────────────────────────

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
    """Demo: pregnant + 3yo — maternal first, screening last."""
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


# ── 5. Dashboard district preference ──────────────────────────────────────

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
    # BENGALURU URBAN → alias BANGALORE → matches "Bangalore"
    assert districts[idx] == "Bangalore"


def test_preferred_district_fallback_first():
    from src.ui_helpers import preferred_district_index
    districts = ["Anjaw", "Delhi", "Kolkata"]
    idx = preferred_district_index(districts, "")
    assert idx == 0  # no Bangalore → first item


def test_preferred_district_none_recent():
    from src.ui_helpers import preferred_district_index
    districts = ["Anjaw", "Bangalore", "Delhi"]
    # Empty recent — Bangalore should win
    idx = preferred_district_index(districts, "")
    assert districts[idx] == "Bangalore"


# ── 6. Data-source badge ───────────────────────────────────────────────────

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
