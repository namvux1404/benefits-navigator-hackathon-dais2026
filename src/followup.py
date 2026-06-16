"""Follow-up question generation, answer parsing, and profile merging for the Family Navigator."""
from __future__ import annotations
import json
import re

from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_AVAILABLE
from .agent_trace import deterministic_trace

_FOLLOWUP_SYSTEM = """\
You are a benefits navigator assistant for families in India.
Given a family's extracted profile, generate 2-3 short follow-up questions to gather missing context.

Return ONLY a valid JSON array — no markdown fences, no preamble, no explanation.
Each element must be a JSON object with exactly these keys:
  "id"          — short snake_case identifier (e.g. "insurance", "urgency", "travel_distance")
  "question"    — question text (plain English, simple enough to read aloud)
  "type"        — always "text"
  "options"     — always []
  "placeholder" — a short example answer in plain English

Rules:
- Return EXACTLY 2-3 question objects.
- All questions must use type "text". Do NOT use radio or select.
- If pincode is null or missing, make the first question ask for it.
  Example placeholder: "560001" or "Bangalore area".
- Ask about health insurance or cost situation if not clearly stated.
  Example question: "Tell us about your current health insurance or cost situation."
  Example placeholder: "I do not have insurance and need low-cost care."
- Ask about travel distance if a pincode is available.
  Example question: "How far can you travel to reach a health facility?"
  Example placeholder: "Up to 5 km."
- Ask about urgency.
  Example question: "Is this urgent today, or are you planning ahead?"
  Example placeholder: "It is urgent today, but not an emergency."
- Do NOT mention any government scheme names (no Ayushman Bharat, ICDS, JSY, PMMVY, etc.).
- Keep all question text simple and plain.
"""

# ── Signal keyword lists ──────────────────────────────────────────────────────

_UNINSURED_SIGNALS = (
    "no insurance",
    "do not have insurance",
    "don't have insurance",
    "uninsured",
    "without insurance",
    "not insured",
    "no health insurance",
    "no coverage",
    "without coverage",
    "no medical insurance",
)

_INSURED_SIGNALS = (
    "have insurance",
    "i have insurance",
    "am insured",
    "with insurance",
    "i'm insured",
    "yes insurance",
    "have coverage",
    "have health insurance",
)

_AFFORDABILITY_SIGNALS = (
    "low-cost",
    "low cost",
    "affordable",
    "afford",
    "cannot afford",
    "can't afford",
    "free care",
    "free services",
    "cost",
    "insurance",
    "uninsured",
    "coverage",
    "covered",
)

# Routine signals — checked first because they are more specific
_ROUTINE_SIGNALS = (
    "not urgent",
    "routine",
    "planning ahead",
    "plan ahead",
    "no rush",
    "not in a hurry",
    "planning",
)

# Urgent signals — checked after routine
_URGENT_SIGNALS = (
    "urgent",
    "need help now",
    "immediately",
    "right now",
    "asap",
    "need today",
    "help today",
    "today",   # per spec: "today" → urgent
    "soon",    # per spec: "soon" → urgent
)


# ── Question generation ───────────────────────────────────────────────────────

def _deterministic_questions(profile: dict, raw_text: str = "") -> list[dict]:
    """Return 2-3 deterministic text-input follow-up questions based on scenario signals.

    Broad scenarios (2+ distinct clinical needs, or 1 need + affordability) always ask
    cost/travel/urgency regardless of whether vaccination is mentioned.  Focused
    scenarios (single need, no affordability) use need-specific questions.
    """
    questions: list[dict] = []
    raw_lower = (raw_text or "").lower()

    def add(qid: str, question: str, placeholder: str) -> None:
        if len(questions) >= 3:
            return
        if any(q["id"] == qid for q in questions):
            return
        questions.append({
            "id": qid,
            "question": question,
            "type": "text",
            "options": [],
            "placeholder": placeholder,
        })

    # Pincode always takes slot 1 when missing
    if not profile.get("pincode"):
        add("pincode", "What is your PIN code or district?", "E.g. 560001 or Bangalore area")

    # Count distinct clinical signals (child_under_5 alone is demographic, not a clinical need)
    affordability_mentioned = any(kw in raw_lower for kw in _AFFORDABILITY_SIGNALS)
    _clinical_count = sum([
        bool(profile.get("pregnant") or profile.get("recently_delivered")),
        bool(profile.get("nutrition_need")),
        bool(profile.get("immunization_need")),
    ])
    # Broad: 2+ clinical needs, OR 1 clinical need + affordability signal
    is_broad = _clinical_count >= 2 or (_clinical_count >= 1 and affordability_mentioned)

    if is_broad:
        # Broad family scenario: always ask cost situation, travel, and urgency
        add(
            "insurance",
            "Tell us about your current health insurance or cost situation.",
            "I do not have insurance and need low-cost care.",
        )
        add(
            "travel_distance",
            "How far can you travel to reach a health facility?",
            "Up to 5 km.",
        )
        add(
            "urgency",
            "Is this urgent today, or are you planning ahead?",
            "It is urgent today, but not an emergency.",
        )
    else:
        # Focused scenario: use signal-specific questions
        if profile.get("immunization_need"):
            add(
                "immunization_timing",
                "Is this a routine vaccination visit, or do you think a vaccine dose was missed or delayed?",
                "Routine visit, or one dose may be delayed.",
            )
            add(
                "vaccination_record",
                "Do you have the child's vaccination card or previous vaccine record?",
                "Yes, I have the card, or no, I do not have it.",
            )

        if profile.get("pregnant"):
            add(
                "urgency",
                "Is this urgent today, or are you planning ahead?",
                "It is urgent today, or I am planning ahead.",
            )
            add(
                "travel_distance",
                "How far can you travel for a pregnancy or maternal health facility?",
                "Up to 5 km.",
            )

        if affordability_mentioned:
            add(
                "insurance",
                "Tell us about your current health insurance or cost situation.",
                "I do not have insurance and need low-cost care.",
            )

        if profile.get("facility_search"):
            add(
                "travel_distance",
                "How far can you travel for a health facility?",
                "Up to 5 km.",
            )

        if profile.get("nutrition_need"):
            add(
                "nutrition_support_type",
                "Is this for growth monitoring, feeding support, or general nutrition advice?",
                "Growth monitoring and feeding support.",
            )

        # Ensure minimum 2 questions
        if len(questions) < 2:
            add(
                "urgency",
                "Is this urgent today, or are you planning ahead?",
                "It is urgent today, but not an emergency.",
            )
        if len(questions) < 2 and profile.get("pincode"):
            add(
                "travel_distance",
                "How far can you travel for a health facility?",
                "Up to 5 km.",
            )

    return questions[:3]


def generate_followup_questions(profile: dict, raw_text: str = "") -> list[dict]:
    """Return 2-3 scenario-specific text-input follow-up question dicts."""
    questions, _trace = generate_followup_questions_with_trace(profile, raw_text)
    return questions


def generate_followup_questions_with_trace(profile: dict, raw_text: str = "") -> tuple[list[dict], dict]:
    """Return scenario-specific follow-up questions and agent trace metadata."""
    return _deterministic_questions(profile, raw_text), deterministic_trace()


def _generate_followup_questions_with_claude(profile: dict, raw_text: str = "") -> list[dict]:
    """Claude-backed follow-up generation kept available but not used for Gate A."""
    if CLAUDE_AVAILABLE:
        try:
            import anthropic

            user_msg = (
                f"Family profile extracted from their description:\n"
                f"{json.dumps(profile, default=str, indent=2)}\n\n"
                f"Original description: {raw_text[:500]}\n\n"
                "Generate 2-3 follow-up questions as a JSON array."
            )

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=500,
                system=_FOLLOWUP_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            raw_resp = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

            raw_resp = re.sub(r"^```[a-z]*\n?", "", raw_resp, flags=re.MULTILINE)
            raw_resp = re.sub(r"\n?```$", "", raw_resp.rstrip()).strip()

            parsed = json.loads(raw_resp)
            if isinstance(parsed, list) and 1 <= len(parsed) <= 5:
                validated: list[dict] = []
                for item in parsed[:3]:
                    if isinstance(item, dict) and "id" in item and "question" in item:
                        validated.append({
                            "id": str(item.get("id", "q")),
                            "question": str(item.get("question", "")),
                            "type": "text",
                            "options": [],
                            "placeholder": str(item.get("placeholder", "")),
                        })
                if validated:
                    return validated
        except Exception:
            pass

    return _deterministic_questions(profile, raw_text)


# ── Answer parsing and profile merging ───────────────────────────────────────

def parse_followup_answers(
    questions: list[dict],
    answers: dict[str, str],
) -> dict:
    """Parse free-text follow-up answers into a structured followup_updates dict.

    Returns only the fields that could be extracted from the answers.
    Pincode and child-age are question-specific; everything else is holistic.
    """
    updates: dict = {}

    # Question-specific parsing
    for q in questions:
        qid = q.get("id", "")
        ans = (answers.get(qid) or "").strip()
        if not ans:
            continue

        if "pincode" in qid or "location" in qid:
            if re.fullmatch(r"\d{6}", ans):
                updates["pincode"] = ans

        elif "child" in qid and "age" in qid:
            ans_lower = ans.lower()
            m = re.search(r"(\d+)\s*(?:month|mo)", ans_lower)
            if m:
                months = int(m.group(1))
                updates["child_age_months"] = months
                updates["child_under_5"] = months < 60
            else:
                m2 = re.search(r"(\d+)\s*(?:year|yr)", ans_lower)
                if m2:
                    months = int(m2.group(1)) * 12
                    updates["child_age_months"] = months
                    updates["child_under_5"] = months < 60

    # Holistic scan across all answer text
    all_text = " ".join(str(v).lower() for v in answers.values() if v).strip()
    if not all_text:
        return updates

    # Insurance status
    if any(kw in all_text for kw in _UNINSURED_SIGNALS):
        updates["uninsured"] = True
        updates["insurance_status"] = "no_insurance"
    elif any(kw in all_text for kw in _INSURED_SIGNALS):
        updates["uninsured"] = False
        updates["insurance_status"] = "insured"

    # Affordability / low-cost need
    if any(kw in all_text for kw in _AFFORDABILITY_SIGNALS):
        updates["low_cost_need"] = True

    # Travel distance — digit forms first (catches "up to 5 km", "within 10 km", etc.)
    km_found: int | None = None
    m_km = re.search(r"\b(\d+)\s*(?:km|kilometer|kilometre)s?\b", all_text)
    if m_km:
        km_found = int(m_km.group(1))
    else:
        # Word-number forms as fallback
        _word_map = {r"twenty.?five": 25, r"\bten\b": 10, r"\bfive\b": 5}
        for pattern, val in _word_map.items():
            if re.search(pattern, all_text) and "km" in all_text:
                km_found = val
                break
    if km_found is not None:
        updates["travel_km"] = km_found

    # Urgency — routine first (more specific phrase), then urgent
    if any(kw in all_text for kw in _ROUTINE_SIGNALS):
        updates["urgency"] = "routine"
    elif any(kw in all_text for kw in _URGENT_SIGNALS):
        updates["urgency"] = "urgent"

    return updates


def merge_profile(base_profile: dict, followup_updates: dict) -> dict:
    """Create final_profile by applying followup_updates onto base_profile.

    Maps low_cost_need → low_income so the rules engine can match
    health_insurance_awareness without knowing about the display-layer key.
    """
    final = base_profile.copy()
    for key, value in followup_updates.items():
        if key == "low_cost_need":
            final["low_cost_need"] = value
            if value:
                final["low_income"] = True
        else:
            final[key] = value
    return final


def apply_followup_answers(
    profile: dict,
    questions: list[dict],
    answers: dict[str, str],
) -> dict:
    """Convenience wrapper: parse answers then merge into profile copy."""
    updates = parse_followup_answers(questions, answers)
    return merge_profile(profile, updates)
