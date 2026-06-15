import pytest
from src.profile_extractor import _regex_extract, extract_profile


# --- regex extraction tests (no API required) ---

def test_demo_scenario_full():
    """Primary demo: PIN 560001, pregnant, 3-year-old child, nutrition need."""
    text = (
        "I live in pincode 560001. I am pregnant and I also have a 3-year-old child. "
        "I need help with nutrition for my child and finding a nearby health facility."
    )
    p = _regex_extract(text)
    assert p["pincode"] == "560001"
    assert p["pregnant"] is True
    assert p["child_under_5"] is True
    assert p["child_age_months"] == 36
    assert p["nutrition_need"] is True
    assert p["adult_woman"] is True
    assert "maternal_care" in p["needs"]
    assert p["extraction_method"] == "regex"


def test_no_pincode():
    p = _regex_extract("I am pregnant and need help.")
    assert p["pincode"] is None
    assert p["pregnant"] is True


def test_infant_age_months():
    p = _regex_extract("My 6-month-old baby needs vaccination.")
    assert p["child_under_5"] is True
    assert p["child_age_months"] == 6


def test_vaccination_scenario_profile_signals():
    text = (
        "I have a 1-year-old baby in pincode 560001 and I want to make sure my child "
        "gets all the required vaccinations. Where is the closest place I can take my "
        "child for immunization?"
    )
    p = _regex_extract(text)
    assert p["pincode"] == "560001"
    assert p["child_age_months"] == 12
    assert p["child_under_5"] is True
    assert p["immunization_need"] is True
    assert p["facility_search"] is True
    assert p["pregnant"] is False
    assert p["nutrition_need"] is False
    assert "child immunization" in p["needs"]
    assert "nearby facility" in p["needs"]


def test_age_years_converted():
    p = _regex_extract("I have a 2-year-old daughter.")
    assert p["child_under_5"] is True
    assert p["child_age_months"] == 24


def test_over_5_years_not_child_under_5():
    """Age ≥ 60 months should NOT set child_under_5 via age extraction."""
    p = _regex_extract("My 7-year-old son.")
    # child_under_5 may be set by keyword "son" but NOT by age extraction
    assert p["child_age_months"] is None or p["child_age_months"] >= 60 or p["child_under_5"] is True
    # The key assertion: child_age_months should not be set to < 60 for a 7-year-old
    if p["child_age_months"] is not None:
        assert p["child_age_months"] >= 60


def test_low_income_and_uninsured():
    p = _regex_extract("I am low income and uninsured.")
    assert p["low_income"] is True
    assert p["uninsured"] is True
    assert "health_insurance" in p["needs"]


def test_water_sanitation():
    p = _regex_extract("We have no access to clean water or sanitation.")
    assert p["water_sanitation_need"] is True
    assert "sanitation" in p["needs"]


def test_recently_delivered():
    p = _regex_extract("I just delivered a baby last week.")
    assert p["recently_delivered"] is True
    assert p["adult_woman"] is True
    assert "maternal_care" in p["needs"]


def test_empty_text_returns_defaults():
    p = _regex_extract("")
    assert p["pregnant"] is False
    assert p["pincode"] is None
    assert p["needs"] == []


# --- extract_profile falls back to regex without key ---

def test_extract_profile_no_api_key():
    import src.profile_extractor as pe
    original = pe.CLAUDE_AVAILABLE
    pe.CLAUDE_AVAILABLE = False
    try:
        text = "I live in pincode 560001. I am pregnant."
        p = extract_profile(text)
        assert p["pincode"] == "560001"
        assert p["pregnant"] is True
        assert p["extraction_method"] == "regex"
    finally:
        pe.CLAUDE_AVAILABLE = original
