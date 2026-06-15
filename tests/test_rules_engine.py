import pytest
from src.rules_engine import _eval_atom, _eval_condition, match_pathways
from src.data_loader import load_pathways


# --- atom-level tests ---

def test_bool_true_match():
    assert _eval_atom("pregnant=true", {"pregnant": True}) is True


def test_bool_true_no_match():
    assert _eval_atom("pregnant=true", {"pregnant": False}) is False


def test_bool_false_match():
    assert _eval_atom("uninsured=false", {"uninsured": False}) is True


def test_bool_false_no_match():
    assert _eval_atom("uninsured=false", {"uninsured": True}) is False


def test_between_lower_bound():
    assert _eval_atom("child_age_months BETWEEN 0 AND 35", {"child_age_months": 0}) is True


def test_between_upper_bound():
    assert _eval_atom("child_age_months BETWEEN 0 AND 35", {"child_age_months": 35}) is True


def test_between_just_above_upper():
    assert _eval_atom("child_age_months BETWEEN 0 AND 35", {"child_age_months": 36}) is False


def test_between_none_value():
    assert _eval_atom("child_age_months BETWEEN 0 AND 35", {"child_age_months": None}) is False


def test_between_missing_key():
    assert _eval_atom("child_age_months BETWEEN 0 AND 35", {}) is False


def test_between_case_insensitive():
    assert _eval_atom("child_age_months between 0 and 35", {"child_age_months": 12}) is True


# --- condition-level tests ---

def test_or_first_true():
    assert _eval_condition("pregnant=true OR recently_delivered=true", {"pregnant": True}) is True


def test_or_second_true():
    assert _eval_condition(
        "pregnant=true OR recently_delivered=true",
        {"pregnant": False, "recently_delivered": True},
    ) is True


def test_or_both_false():
    assert _eval_condition(
        "pregnant=true OR recently_delivered=true",
        {"pregnant": False, "recently_delivered": False},
    ) is False


def test_between_as_full_condition():
    assert _eval_condition("child_age_months BETWEEN 0 AND 35", {"child_age_months": 12}) is True
    assert _eval_condition("child_age_months BETWEEN 0 AND 35", {"child_age_months": 36}) is False


# --- pathway matching ---

def test_demo_scenario_matched_pathways():
    """PIN 560001: pregnant mother + 3-year-old → maternal_care + child_nutrition + women_preventive_screening."""
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
    matched_ids = {pw["pathway_id"] for pw in matched}
    assert "maternal_care" in matched_ids
    assert "child_nutrition" in matched_ids
    # 3-year-old is 36 months — outside the 0–35 immunization window
    assert "immunization" not in matched_ids
    assert "health_insurance_awareness" not in matched_ids


def test_immunization_matches_under_3():
    profile = {"child_age_months": 12}
    matched = match_pathways(profile, load_pathways())
    assert any(pw["pathway_id"] == "immunization" for pw in matched)


def test_vaccination_scenario_matches_immunization_not_insurance():
    profile = {
        "pincode": "560001",
        "pregnant": False,
        "recently_delivered": False,
        "child_under_5": True,
        "child_age_months": 12,
        "immunization_need": True,
        "facility_search": True,
        "nutrition_need": False,
        "uninsured": False,
        "low_income": False,
        "adult_woman": False,
    }
    matched = match_pathways(profile, load_pathways())
    ids = {pw["pathway_id"] for pw in matched}
    assert "immunization" in ids
    assert "health_insurance_awareness" not in ids


def test_active_flag_false_skips_pathway():
    profile = {"pregnant": True}
    pathways = [
        {"pathway_id": "maternal_care", "trigger_condition": "pregnant=true", "active_flag": "false"},
        {"pathway_id": "other", "trigger_condition": "pregnant=true", "active_flag": "true"},
    ]
    matched = match_pathways(profile, pathways)
    ids = {pw["pathway_id"] for pw in matched}
    assert "maternal_care" not in ids
    assert "other" in ids


def test_empty_profile_no_match():
    matched = match_pathways({}, load_pathways())
    assert matched == []
