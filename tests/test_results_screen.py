from pathlib import Path

from src.state_store import StateStore
from src.ui_helpers import (
    facility_card_public_text,
    limited_facilities,
    plan_method_label,
    results_section_order,
    safe_nfhs_value,
    service_tags_for_facility,
)


def test_nearby_facilities_section_limits_to_five():
    facilities = [{"name": f"Facility {i}"} for i in range(8)]
    assert len(limited_facilities(facilities)) == 5


def test_results_page_orders_pathways_before_action_plan():
    order = results_section_order()
    assert order.index("matched_pathways") < order.index("action_plan")


def test_action_plan_label_matches_actual_generator():
    assert plan_method_label("claude") == "Claude Sonnet"
    assert plan_method_label("deterministic") == "Deterministic fallback"


def test_claude_generated_plan_shows_claude_sonnet():
    assert plan_method_label("claude") == "Claude Sonnet"


def test_deterministic_fallback_plan_label():
    assert plan_method_label("deterministic") == "Deterministic fallback"


def test_district_indicator_formatting_removes_double_parentheses():
    value, quality = safe_nfhs_value("(78.2)")
    assert value == "78.2%"
    assert quality == "uncertain"
    assert "(" not in value
    assert ")" not in value


def test_suppressed_indicator_formatting_is_compact():
    value, quality = safe_nfhs_value("*")
    assert value == "Not available - suppressed"
    assert quality == "suppressed"


def test_feedback_section_text_exists_on_screen3():
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert "How helpful was this plan?" in app_text
    assert "Submit feedback" in app_text
    assert "Thanks — your feedback was saved." in app_text


def test_facility_card_public_text_hides_raw_list_strings_and_metadata():
    facility = {
        "name": "Demo Clinic",
        "address_line1": "123 Main Road",
        "address_city": "Bengaluru",
        "address_stateOrRegion": "Karnataka",
        "officialPhone": "12345",
        "email": "hello@example.org",
        "specialties": '["pediatrics","gynecologyAndObstetrics","internalMedicine"]',
        "source_ids": '["abc"]',
        "source_content_id": "raw-id",
        "latitude": "12.9",
        "longitude": "77.6",
    }
    public = facility_card_public_text(facility)
    assert "[" not in public
    assert "]" not in public
    assert "source_ids" not in public
    assert "source_content_id" not in public
    assert "Coordinates" not in public
    assert "Pediatrics" in public


def test_facility_card_service_tags_max_three():
    facility = {
        "specialties": (
            '["pediatrics","gynecologyAndObstetrics","internalMedicine",'
            '"dentistry","cardiology"]'
        )
    }
    assert len(service_tags_for_facility(facility)) <= 3


def test_district_context_title_exists_on_screen3():
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert "Relevant District Health Context" in app_text


def test_feedback_save_works_with_sqlite(tmp_path):
    store = StateStore(tmp_path / "feedback.db")
    feedback_id = store.save_feedback(
        session_id="session-1",
        rating="Helpful",
        comment="Clear and useful.",
    )

    rows = store.get_recent_feedback()
    assert feedback_id
    assert len(rows) == 1
    assert rows[0]["session_id"] == "session-1"
    assert rows[0]["rating"] == "Helpful"
    assert rows[0]["comment"] == "Clear and useful."
