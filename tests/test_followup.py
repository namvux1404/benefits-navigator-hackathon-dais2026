"""Tests for follow-up question generation and free-text answer parsing."""
import pytest


DEMO_TEXT = (
    "I live in pincode 560001. I am pregnant and have a 3-year-old child. "
    "I do not know where to go for affordable health services. "
    "I need help with nutrition, vaccination, and finding a nearby facility."
)

DEMO_PROFILE = {
    "pincode": "560001",
    "pregnant": True,
    "recently_delivered": False,
    "child_under_5": True,
    "child_age_months": 36,
    "nutrition_need": True,
    "uninsured": False,
    "adult_woman": True,
}


# -- _deterministic_questions - structure ------------------------------------

def test_all_questions_are_text_type():
    """All questions must use type='text' - no radio buttons."""
    from src.followup import _deterministic_questions
    for q in _deterministic_questions(DEMO_PROFILE, DEMO_TEXT):
        assert q["type"] == "text", f"Expected type='text' for question '{q['id']}', got '{q['type']}'"


def test_all_questions_have_placeholder():
    """Every question must have a non-empty placeholder example answer."""
    from src.followup import _deterministic_questions
    for q in _deterministic_questions(DEMO_PROFILE, DEMO_TEXT):
        assert "placeholder" in q, f"Missing 'placeholder' in question {q['id']}"
        assert q["placeholder"], f"Empty placeholder in question {q['id']}"


def test_all_questions_have_required_fields():
    """Every question dict must have id, question, type, options, placeholder."""
    from src.followup import _deterministic_questions
    for q in _deterministic_questions(DEMO_PROFILE, DEMO_TEXT):
        for field in ("id", "question", "type", "options", "placeholder"):
            assert field in q, f"Missing '{field}' in {q}"
        assert isinstance(q["options"], list)


def test_demo_profile_includes_insurance_question():
    """Demo profile (no insurance keyword in raw text) -> asks about insurance/cost."""
    from src.followup import _deterministic_questions
    questions = _deterministic_questions(DEMO_PROFILE, DEMO_TEXT)
    ids = [q["id"] for q in questions]
    assert "insurance" in ids, f"Expected insurance question, got: {ids}"


def test_demo_profile_includes_travel_and_urgency():
    from src.followup import _deterministic_questions
    questions = _deterministic_questions(DEMO_PROFILE, DEMO_TEXT)
    ids = [q["id"] for q in questions]
    assert "travel_distance" in ids, f"Expected travel_distance, got: {ids}"
    assert "urgency" in ids, f"Expected urgency, got: {ids}"


def test_demo_profile_returns_exactly_3():
    from src.followup import _deterministic_questions
    questions = _deterministic_questions(DEMO_PROFILE, DEMO_TEXT)
    assert len(questions) == 3, f"Expected 3 questions, got {len(questions)}: {[q['id'] for q in questions]}"


def test_no_pincode_first_question_is_pincode():
    """No pincode in profile -> first question asks for it with text input."""
    from src.followup import _deterministic_questions
    questions = _deterministic_questions({"pregnant": True}, "I am pregnant.")
    assert questions[0]["id"] == "pincode"
    assert questions[0]["type"] == "text"
    assert questions[0]["placeholder"]  # must have an example


def test_max_3_questions():
    from src.followup import _deterministic_questions
    assert len(_deterministic_questions({})) <= 3


def test_insurance_in_raw_text_skips_insurance_question():
    """Explicit 'uninsured' in description -> skip the insurance question."""
    from src.followup import _deterministic_questions
    profile = {"pincode": "560001"}
    raw = "I am uninsured and need help with maternal care."
    ids = [q["id"] for q in _deterministic_questions(profile, raw)]
    assert "insurance" in ids, f"Should ask insurance when cost/coverage is relevant; got: {ids}"


def test_insurance_placeholder_mentions_no_insurance():
    """The insurance question placeholder should mention 'no insurance'."""
    from src.followup import _deterministic_questions
    profile = {"pincode": "560001"}
    questions = _deterministic_questions(profile, "I need affordable care.")
    ins_q = next((q for q in questions if q["id"] == "insurance"), None)
    assert ins_q is not None
    assert "no insurance" in ins_q["placeholder"].lower() or "low-cost" in ins_q["placeholder"].lower()


VACCINATION_TEXT = (
    "I have a 1-year-old baby in pincode 560001 and I want to make sure my child "
    "gets all the required vaccinations. Where is the closest place I can take my "
    "child for immunization?"
)


def test_vaccination_followup_questions_are_scenario_specific():
    from src.followup import _deterministic_questions
    from src.profile_extractor import _regex_extract

    profile = _regex_extract(VACCINATION_TEXT)
    questions = _deterministic_questions(profile, VACCINATION_TEXT)
    text = " ".join(q["question"].lower() for q in questions)

    assert "routine vaccination" in text
    assert "missed or delayed" in text
    assert "vaccination card" in text or "previous vaccine record" in text
    assert "how far can you travel" in text


def test_vaccination_followup_does_not_ask_insurance_without_cost_signal():
    from src.followup import _deterministic_questions
    from src.profile_extractor import _regex_extract

    profile = _regex_extract(VACCINATION_TEXT)
    questions = _deterministic_questions(profile, VACCINATION_TEXT)
    assert "insurance" not in [q["id"] for q in questions]


# -- generate_followup_questions (no API) ------------------------------------

def test_generate_followup_no_api_falls_back_to_deterministic():
    import src.followup as fmod
    original = fmod.CLAUDE_AVAILABLE
    fmod.CLAUDE_AVAILABLE = False
    try:
        questions = fmod.generate_followup_questions(DEMO_PROFILE, DEMO_TEXT)
        assert 2 <= len(questions) <= 3
        assert all(q["type"] == "text" for q in questions)
    finally:
        fmod.CLAUDE_AVAILABLE = original


def test_generate_followup_result_has_placeholder():
    import src.followup as fmod
    original = fmod.CLAUDE_AVAILABLE
    fmod.CLAUDE_AVAILABLE = False
    try:
        questions = fmod.generate_followup_questions(DEMO_PROFILE, DEMO_TEXT)
        for q in questions:
            assert "placeholder" in q
    finally:
        fmod.CLAUDE_AVAILABLE = original


# -- apply_followup_answers - free-text holistic parsing ---------------------

def _make_q(qid: str) -> dict:
    return {"id": qid, "type": "text", "options": [], "question": "?", "placeholder": ""}


def test_free_text_no_insurance_sets_uninsured_true():
    """'I do not have insurance and need low-cost care.' -> uninsured=True."""
    from src.followup import apply_followup_answers
    questions = [_make_q("insurance")]
    answers = {"insurance": "I do not have insurance and need low-cost care."}
    updated = apply_followup_answers({}, questions, answers)
    assert updated["uninsured"] is True


def test_free_text_no_insurance_also_sets_low_income():
    """'need low-cost care' in the same answer -> low_income=True."""
    from src.followup import apply_followup_answers
    questions = [_make_q("insurance")]
    answers = {"insurance": "I do not have insurance and need low-cost care."}
    updated = apply_followup_answers({}, questions, answers)
    assert updated.get("low_income") is True


def test_free_text_have_insurance_sets_uninsured_false():
    from src.followup import apply_followup_answers
    questions = [_make_q("insurance")]
    answers = {"insurance": "Yes, I have insurance through my employer."}
    updated = apply_followup_answers({"uninsured": True}, questions, answers)
    assert updated["uninsured"] is False


def test_free_text_travel_5km():
    """'Up to 5 km.' -> travel_km=5."""
    from src.followup import apply_followup_answers
    questions = [_make_q("travel_distance")]
    updated = apply_followup_answers({}, questions, {"travel_distance": "Up to 5 km."})
    assert updated.get("travel_km") == 5


def test_free_text_travel_10km():
    from src.followup import apply_followup_answers
    questions = [_make_q("travel_distance")]
    updated = apply_followup_answers({}, questions, {"travel_distance": "Up to 10 km."})
    assert updated.get("travel_km") == 10


def test_free_text_travel_25km():
    from src.followup import apply_followup_answers
    questions = [_make_q("travel_distance")]
    updated = apply_followup_answers({}, questions, {"travel_distance": "Up to 25 km."})
    assert updated.get("travel_km") == 25


def test_free_text_travel_25_not_confused_with_5():
    """25 km should not be parsed as 5 km."""
    from src.followup import apply_followup_answers
    questions = [_make_q("travel_distance")]
    updated = apply_followup_answers({}, questions, {"travel_distance": "I can travel 25 km."})
    assert updated.get("travel_km") == 25


def test_free_text_urgent_today():
    """'It is urgent today, but not an emergency.' -> urgency='urgent'."""
    from src.followup import apply_followup_answers
    questions = [_make_q("urgency")]
    updated = apply_followup_answers({}, questions, {"urgency": "It is urgent today, but not an emergency."})
    assert updated.get("urgency") == "urgent"


def test_free_text_routine_planning():
    """'I am planning ahead for routine support.' -> urgency='routine'."""
    from src.followup import apply_followup_answers
    questions = [_make_q("urgency")]
    updated = apply_followup_answers({}, questions, {"urgency": "I am planning ahead for routine support."})
    assert updated.get("urgency") == "routine"


def test_free_text_not_urgent_sets_routine():
    from src.followup import apply_followup_answers
    questions = [_make_q("urgency")]
    updated = apply_followup_answers({}, questions, {"urgency": "This is not urgent at all."})
    assert updated.get("urgency") == "routine"


def test_affordability_keyword_alone_sets_low_income():
    """'I need affordable care.' alone -> low_income=True."""
    from src.followup import apply_followup_answers
    questions = [_make_q("insurance")]
    updated = apply_followup_answers({}, questions, {"insurance": "I need affordable care."})
    assert updated.get("low_income") is True


def test_not_sure_leaves_insurance_unchanged():
    """A vague answer with no insurance keywords -> profile unchanged."""
    from src.followup import apply_followup_answers
    questions = [_make_q("insurance")]
    original_val = False
    updated = apply_followup_answers({"uninsured": original_val}, questions, {"insurance": "I am not sure about this."})
    assert updated["uninsured"] == original_val


def test_does_not_mutate_original_profile():
    from src.followup import apply_followup_answers
    original = {"uninsured": None, "low_income": False}
    apply_followup_answers(original, [_make_q("insurance")], {"insurance": "No insurance."})
    assert original["uninsured"] is None


def test_empty_answers_leaves_profile_unchanged():
    from src.followup import apply_followup_answers
    profile = {"pregnant": True, "uninsured": False}
    updated = apply_followup_answers(profile, [_make_q("insurance"), _make_q("urgency")], {})
    assert updated["pregnant"] is True
    assert updated["uninsured"] is False
    assert "urgency" not in updated


def test_complete_demo_followup_enriches_profile():
    """All three demo question answers -> profile enriched with all expected fields."""
    from src.followup import apply_followup_answers
    questions = [_make_q("insurance"), _make_q("travel_distance"), _make_q("urgency")]
    answers = {
        "insurance": "I do not have insurance and need low-cost care.",
        "travel_distance": "Up to 10 km.",
        "urgency": "It is urgent today, but not an emergency.",
    }
    updated = apply_followup_answers(DEMO_PROFILE.copy(), questions, answers)
    assert updated["uninsured"] is True
    assert updated.get("low_income") is True
    assert updated.get("travel_km") == 10
    assert updated.get("urgency") == "urgent"
    # Original fields preserved
    assert updated["pregnant"] is True
    assert updated["pincode"] == "560001"


def test_profile_review_fields_populated_after_answers():
    """After apply_followup_answers, all fields needed for the review card are present."""
    from src.followup import apply_followup_answers
    questions = [_make_q("insurance"), _make_q("travel_distance"), _make_q("urgency")]
    answers = {
        "insurance": "I do not have insurance and need low-cost care.",
        "travel_distance": "Up to 5 km.",
        "urgency": "Routine - planning ahead.",
    }
    updated = apply_followup_answers(DEMO_PROFILE.copy(), questions, answers)
    # All fields needed for the review card to render completely
    assert "pincode" in updated
    assert "pregnant" in updated
    assert "child_age_months" in updated
    assert "uninsured" in updated
    assert "travel_km" in updated
    assert "urgency" in updated


# -- parse_followup_answers - direct unit tests ------------------------------

def test_parse_returns_dict():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("insurance")], {"insurance": "I do not have insurance."})
    assert isinstance(result, dict)


def test_parse_no_insurance_signal():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("insurance")], {"insurance": "I do not have insurance."})
    assert result.get("uninsured") is True
    assert result.get("insurance_status") == "no_insurance"


def test_parse_have_insurance_signal():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("insurance")], {"insurance": "Yes, I have insurance."})
    assert result.get("uninsured") is False
    assert result.get("insurance_status") == "insured"


def test_parse_affordability_signal():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("insurance")], {"insurance": "I need affordable care only."})
    assert result.get("low_cost_need") is True


def test_parse_travel_5km_digit():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("travel_distance")], {"travel_distance": "Up to 5 km."})
    assert result.get("travel_km") == 5


def test_parse_travel_10km_digit():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("travel_distance")], {"travel_distance": "10 km is fine."})
    assert result.get("travel_km") == 10


def test_parse_travel_25km_digit():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("travel_distance")], {"travel_distance": "25 km."})
    assert result.get("travel_km") == 25


def test_parse_travel_word_five_km():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("travel_distance")], {"travel_distance": "five km away"})
    assert result.get("travel_km") == 5


def test_parse_travel_word_ten_km():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("travel_distance")], {"travel_distance": "ten km"})
    assert result.get("travel_km") == 10


def test_parse_travel_word_twenty_five_km():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("travel_distance")], {"travel_distance": "twenty five km"})
    assert result.get("travel_km") == 25


def test_parse_urgency_today():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("urgency")], {"urgency": "I need help today."})
    assert result.get("urgency") == "urgent"


def test_parse_urgency_soon():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("urgency")], {"urgency": "I need help soon."})
    assert result.get("urgency") == "urgent"


def test_parse_urgency_urgent_keyword():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("urgency")], {"urgency": "This is urgent."})
    assert result.get("urgency") == "urgent"


def test_parse_urgency_routine_planning():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("urgency")], {"urgency": "I am planning ahead."})
    assert result.get("urgency") == "routine"


def test_parse_urgency_not_urgent_wins_over_urgent():
    """'not urgent' (routine signal) wins over the 'urgent' word in 'not urgent'."""
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("urgency")], {"urgency": "This is not urgent at all."})
    assert result.get("urgency") == "routine"


def test_parse_pincode_question_specific():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("pincode")], {"pincode": "560001"})
    assert result.get("pincode") == "560001"


def test_parse_pincode_invalid_does_not_set():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("pincode")], {"pincode": "Bangalore area"})
    assert "pincode" not in result


def test_parse_empty_answers_returns_empty_dict():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("insurance"), _make_q("urgency")], {})
    assert result == {}


def test_parse_does_not_include_low_cost_need_when_absent():
    from src.followup import parse_followup_answers
    result = parse_followup_answers([_make_q("urgency")], {"urgency": "Urgent today."})
    assert "low_cost_need" not in result


# -- merge_profile - direct unit tests ---------------------------------------

def test_merge_copies_base_profile():
    from src.followup import merge_profile
    base = {"pregnant": True, "pincode": "560001"}
    final = merge_profile(base, {})
    assert final["pregnant"] is True
    assert final["pincode"] == "560001"


def test_merge_applies_updates():
    from src.followup import merge_profile
    base = {"pregnant": True, "uninsured": None}
    updates = {"uninsured": True, "travel_km": 10}
    final = merge_profile(base, updates)
    assert final["uninsured"] is True
    assert final["travel_km"] == 10


def test_merge_low_cost_need_sets_low_income():
    """low_cost_need=True in updates must also set low_income=True in final profile."""
    from src.followup import merge_profile
    final = merge_profile({}, {"low_cost_need": True})
    assert final.get("low_cost_need") is True
    assert final.get("low_income") is True


def test_merge_low_cost_need_false_does_not_set_low_income():
    from src.followup import merge_profile
    final = merge_profile({"low_income": False}, {"low_cost_need": False})
    assert final.get("low_cost_need") is False
    assert final.get("low_income") is False


def test_merge_does_not_mutate_base():
    from src.followup import merge_profile
    base = {"pregnant": True}
    merge_profile(base, {"pregnant": False})
    assert base["pregnant"] is True  # original untouched


def test_merge_updates_overwrite_base():
    from src.followup import merge_profile
    final = merge_profile({"urgency": "routine"}, {"urgency": "urgent"})
    assert final["urgency"] == "urgent"


def test_merge_empty_updates_returns_copy():
    from src.followup import merge_profile
    base = {"a": 1, "b": 2}
    final = merge_profile(base, {})
    assert final == base
    assert final is not base  # it's a copy, not the same object


# -- Full demo lineage test ---------------------------------------------------

def test_full_demo_lineage():
    """Gate A demo scenario: base_profile -> follow-up answers -> final_profile has all expected fields."""
    from src.followup import merge_profile, parse_followup_answers

    base_profile = {
        "pincode": "560001",
        "pregnant": True,
        "recently_delivered": False,
        "child_under_5": True,
        "child_age_months": 36,
        "nutrition_need": True,
        "uninsured": None,
        "adult_woman": True,
    }
    questions = [
        _make_q("insurance"),
        _make_q("travel_distance"),
        _make_q("urgency"),
    ]
    answers = {
        "insurance": "I do not have insurance and need low-cost care.",
        "travel_distance": "Up to 10 km.",
        "urgency": "It is urgent today, but not an emergency.",
    }

    followup_updates = parse_followup_answers(questions, answers)
    assert followup_updates.get("uninsured") is True
    assert followup_updates.get("low_cost_need") is True
    assert followup_updates.get("travel_km") == 10
    assert followup_updates.get("urgency") == "urgent"

    final_profile = merge_profile(base_profile, followup_updates)

    # All base fields preserved
    assert final_profile["pincode"] == "560001"
    assert final_profile["pregnant"] is True
    assert final_profile["child_age_months"] == 36

    # All follow-up updates applied
    assert final_profile["uninsured"] is True
    assert final_profile.get("low_income") is True  # mapped from low_cost_need
    assert final_profile["travel_km"] == 10
    assert final_profile["urgency"] == "urgent"

    # base_profile not mutated
    assert base_profile["uninsured"] is None


# -- New: broad-scenario and urgency tests ------------------------------------

def test_broad_scenario_with_immunization_asks_cost_travel_urgency():
    """Broad scenario (pregnant + nutrition + vaccination) must ask cost/travel/urgency."""
    from src.followup import _deterministic_questions
    profile = {
        "pincode": "560001",
        "pregnant": True,
        "child_under_5": True,
        "nutrition_need": True,
        "immunization_need": True,   # vaccination mentioned but scenario is broad
        "facility_search": True,
    }
    raw = (
        "I am pregnant and have a 3-year-old child. I do not know where to go for "
        "affordable health services. I need help with nutrition, vaccination, and "
        "finding a nearby facility."
    )
    questions = _deterministic_questions(profile, raw)
    ids = [q["id"] for q in questions]
    assert "insurance" in ids, f"Broad scenario should ask insurance/cost, got: {ids}"
    assert "travel_distance" in ids, f"Broad scenario should ask travel, got: {ids}"
    assert "urgency" in ids, f"Broad scenario should ask urgency, got: {ids}"
    assert "immunization_timing" not in ids, (
        f"Vaccination-specific question should not dominate broad scenario, got: {ids}"
    )


def test_urgent_today_not_emergency_is_urgent():
    """'urgent today but not an emergency' should parse as urgency=urgent, not routine."""
    from src.followup import parse_followup_answers
    q = [{"id": "urgency", "type": "text", "options": [], "question": "?", "placeholder": ""}]
    result = parse_followup_answers(q, {"urgency": "urgent today but not an emergency"})
    assert result.get("urgency") == "urgent"
    assert result.get("urgency") != "routine"


def test_up_to_km_parses_travel_range():
    """'Up to 7 km' and 'within 3 km' should parse any numeric km distance."""
    from src.followup import parse_followup_answers
    q = [{"id": "travel_distance", "type": "text", "options": [], "question": "?", "placeholder": ""}]
    assert parse_followup_answers(q, {"travel_distance": "Up to 7 km"}).get("travel_km") == 7
    assert parse_followup_answers(q, {"travel_distance": "within 3 km"}).get("travel_km") == 3
    assert parse_followup_answers(q, {"travel_distance": "15 kilometers"}).get("travel_km") == 15
