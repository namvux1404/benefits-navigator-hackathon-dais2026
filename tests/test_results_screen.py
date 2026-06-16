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
    assert "Thanks - your feedback was saved." in app_text


def test_app_title_text_is_plain():
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert 'st.title("TrustRoute AI")' in app_text
    assert "st.title(\"ð" not in app_text


def test_tab_labels_are_plain_text():
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert '["Referral Navigator", "Program Leader Dashboard", "Data Trust / Debug"]' in app_text


def test_user_facing_ui_text_has_no_mojibake_patterns():
    app_text = Path("app.py").read_text(encoding="utf-8")
    mojibake_patterns = (
        chr(0x00F0) + chr(0x0178),
        chr(0x00E2),
        chr(0xFFFD),
    )
    for pattern in mojibake_patterns:
        assert pattern not in app_text


def test_feedback_labels_do_not_include_emojis():
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert '["Helpful", "Somewhat helpful", "Not helpful"]' in app_text
    assert f"{chr(0x2705)} Helpful" not in app_text
    assert chr(0x00F0) not in app_text


def test_screen1_custom_scenario_entry_comes_before_samples():
    app_text = Path("app.py").read_text(encoding="utf-8")
    text_area_idx = app_text.index("st.text_area(")
    sample_expander_idx = app_text.index('st.expander("Try a sample referral scenario"')
    assert text_area_idx < sample_expander_idx
    assert "Quick-start demo scenarios" not in app_text


def test_screen1_sample_scenarios_are_in_expander():
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert 'st.expander("Try a sample referral scenario", expanded=False)' in app_text
    assert "Pregnant mother with young child" in app_text
    assert "Parent with child needing vaccination" in app_text
    assert "Field worker reviewing district health risk" in app_text


def test_screen1_main_button_label_and_empty_guard():
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert '"Analyze care need"' in app_text
    assert '"Analyse My Family Profile"' not in app_text
    assert "disabled=not raw.strip()" in app_text


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


def test_screen3_no_static_next_steps_call():
    """App must not call next_steps_for_profile (removed static Next Steps section)."""
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert "next_steps_for_profile" not in app_text


def test_screen3_pathway_card_why_matched():
    """Pathway cards must use 'Why matched:' label, not 'Reason:'."""
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert "**Why matched:**" in app_text


def test_screen3_facility_badge_is_trust_signal():
    """Facility badge text must say 'Trust signal:' not 'Evidence strength:'."""
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert "Trust signal:" in app_text
    assert "Evidence strength:" not in app_text


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
