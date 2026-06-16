from __future__ import annotations

import re

from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_AVAILABLE
from .bb_logging import log_action_plan_input

_PLAN_SYSTEM = """\
You are a health benefits navigator AI for families in India, assisting a community health worker.
Generate a concise, actionable support plan in plain English (max 300 words, 4-6 numbered steps).

FAMILY INTRODUCTION:
Begin with 1-2 sentences naming this family's specific situation (pregnancy status, child age,
insurance/cost situation), noting that the guidance is based on trusted NFHS-5 district health data.
Remind the reader this supplements but does not replace a qualified health worker or PHC.

Then list EXACTLY 4-6 numbered action steps. Keep each step to one sentence.
Use language simple enough for a community health worker to read aloud.
Spell "Anganwadi" correctly (not "angawadi" or "Anganwadi worker").

CRITICAL — DO NOT LIST FACILITIES:
The application displays facility cards with full evidence below the plan — do NOT repeat them.
You MUST NOT include any of the following in your response:
  - A heading such as "Nearby Health Facilities", "Facilities", "Recommended Facilities", or similar
  - Any numbered or bulleted list of facility names, addresses, or phone numbers
  - Any table or formatted block of facility data
For facility referral, write exactly one sentence such as:
  "Review the facility cards below and call the first suitable option to confirm services."

GROUNDING RULES - follow strictly:
- Use ONLY the support pathways and facility information explicitly provided in this prompt.
- Do NOT name specific government schemes (Ayushman Bharat, ICDS, PM Matru Vandana Yojana,
  Janani Suraksha Yojana, PMMVY, or any other) unless the pathway text below explicitly names them.
- Do NOT promise free food, free medicines, or free services unless the pathway text says so.
- For nutrition needs always say: "Ask the nearest public health facility or local health worker
  about nutrition support options available in your area."
- For health insurance always say: "If you have insurance, confirm whether pregnancy and child care
  are covered. If you do not, ask the facility what public coverage or low-cost options may be available."
- Never assume the family has insurance unless the profile explicitly states uninsured=False.
- When uncertain about a specific service say: "Ask your local health worker or facility."
"""

# Compiled pattern to strip any facility-list section Claude may have included despite instructions.
# Matches: a line containing "Facilit..." followed by pipe-delimited numbered items.
_FACILITY_LIST_RE = re.compile(
    r'\n[^\n]*Facilit(?:ies|y)[^\n]*\n(?:(?:[ \t]*\d+\.[^\n]*\|[^\n]*\n?))+',
    re.IGNORECASE,
)
# Broader fallback: bold/heading "Facilities" line followed by any numbered items
_FACILITY_HEADING_RE = re.compile(
    r'\n(?:(?:\*{1,2})|(?:#{1,3}\s+))(?:Nearby\s+)?(?:Health\s+)?Facilit(?:ies|y)[^\n]*\n'
    r'(?:(?:[ \t]*\d+\.[^\n]+\n?))+',
    re.IGNORECASE,
)


def _strip_facility_section(text: str) -> str:
    """Remove any standalone facility list that Claude included despite the prompt instruction."""
    result = _FACILITY_LIST_RE.sub('\n', text)
    result = _FACILITY_HEADING_RE.sub('\n', result)
    return result.strip()

_MAX_CLAUDE_FACILITIES = 5


def _build_facility_lines(facilities: list[dict]) -> str:
    """Return a compact facility summary string for the Claude prompt."""
    if not facilities:
        return "No facilities in local dataset\n"
    lines = f"Top {len(facilities)} nearby facilities:\n"
    for i, f in enumerate(facilities, 1):
        name = f.get("name", "Unknown facility")
        parts: list[str] = [name]
        addr = ", ".join(x for x in [
            f.get("address_line1", ""),
            f.get("address_city", ""),
            f.get("address_stateOrRegion", ""),
            f.get("address_zipOrPostcode", ""),
        ] if x)
        if addr:
            parts.append(addr)
        phone = f.get("officialPhone", "")
        if phone:
            parts.append(f"Phone: {phone}")
        lines += f"  {i}. {' | '.join(parts)}\n"
    return lines


_NFHS_DISPLAY_COLS = [
    ("institutional_birth_5y_pct", "Institutional births"),
    ("mothers_who_had_at_least_4_anc_visits_lb5y_pct", "4+ ANC visits"),
    ("child_u5_who_are_stunted_height_for_age_18_pct", "Child stunting"),
    ("hh_member_covered_health_insurance_pct", "Health insurance coverage"),
    ("non_pregnant_w15_49_who_are_anaemic_lt_12_0_g_dl_22_pct", "Women anaemia"),
]


def _deterministic_plan(
    profile: dict,
    matched_pathways: list[dict],
    nfhs_rows: list[dict],
    facilities: list[dict],
) -> str:
    if not matched_pathways:
        return (
            "No specific support pathways matched your profile at this time.\n\n"
            "Please speak with a local Anganwadi worker or visit your nearest "
            "Primary Health Centre (PHC) for personalised guidance."
        )

    ids = {pw.get("pathway_id", "") for pw in matched_pathways}
    if "immunization" in ids or profile.get("immunization_need"):
        return "\n".join([
            "**Step 1 - Confirm vaccination need**",
            "",
            "Review your child's vaccination card or previous vaccine record.",
            "",
            "**Step 2 - Contact a nearby child-health facility**",
            "",
            "Use the nearby facilities listed below and call the first available facility.",
            "",
            "**Step 3 - Ask these questions**",
            "",
            "- Which vaccines are due for a 1-year-old child?",
            "- Do I need to bring my child's vaccination card?",
            "- Can I come today or should I book an appointment?",
        ])

    return "\n".join([
        "**Step 1 - Review the matched support pathways**",
        "",
        "Use the support pathways above to understand which kind of help is most relevant.",
        "",
        "**Step 2 - Contact a nearby facility**",
        "",
        "Use the nearby facilities listed below and ask which services are available today.",
        "",
        "**Step 3 - Bring available records**",
        "",
        "Bring any pregnancy, child health, vaccination, or referral records you already have.",
    ])


def generate_action_plan(
    profile: dict,
    matched_pathways: list[dict],
    nfhs_rows: list[dict],
    facilities: list[dict],
    followup_answers: dict | None = None,
) -> tuple[str, str]:
    """Return (plan_text, method), where method is 'claude' or 'deterministic'."""
    plan_text, method, _trace = generate_action_plan_with_trace(
        profile, matched_pathways, nfhs_rows, facilities, followup_answers
    )
    return plan_text, method


def generate_action_plan_with_trace(
    profile: dict,
    matched_pathways: list[dict],
    nfhs_rows: list[dict],
    facilities: list[dict],
    followup_answers: dict | None = None,
) -> tuple[str, str, dict]:
    """Return (plan_text, method, trace)."""
    # Cap facilities before logging and before sending to Claude
    top_facilities = facilities[:_MAX_CLAUDE_FACILITIES]
    log_action_plan_input(profile, matched_pathways, nfhs_rows, top_facilities, followup_answers)
    trace = {
        "provider": "deterministic",
        "model": None,
        "fallback_used": False,
        "fallback_reason": None,
    }
    if CLAUDE_AVAILABLE:
        try:
            import anthropic

            pin = profile.get("pincode", "unknown")
            district = profile.get("district_norm", "")
            state = profile.get("state_norm", "")
            location = f"PIN {pin}"
            if district:
                location += f" ({district}, {state})"

            pathway_lines = "".join(
                f"- {pw.get('pathway_name')}: {pw.get('recommended_action', '')}\n"
                for pw in matched_pathways
            ) or "None matched\n"

            nfhs_lines = ""
            if nfhs_rows:
                r = nfhs_rows[0]
                nfhs_lines = f"District: {r.get('district_name','').strip()}, {r.get('state_ut','').strip()}\n"
                for col, label in _NFHS_DISPLAY_COLS:
                    v = str(r.get(col, "")).strip()
                    if v and v not in ("NA", "*", "nan", ""):
                        nfhs_lines += f"  {label}: {v}%\n"

            fac_lines = _build_facility_lines(top_facilities)

            followup_lines = ""
            if followup_answers:
                followup_lines = "Family follow-up answers:\n" + "".join(
                    f"  {k}: {v}\n" for k, v in followup_answers.items() if v
                )

            user_msg = (
                f"Family location: {location}\n"
                f"Profile: pregnant={profile.get('pregnant')}, "
                f"child_under_5={profile.get('child_under_5')}, "
                f"child_age_months={profile.get('child_age_months')}, "
                f"nutrition_need={profile.get('nutrition_need')}, "
                f"uninsured={profile.get('uninsured')}\n\n"
                f"Matched support pathways:\n{pathway_lines}\n"
                f"District health context (NFHS-5):\n{nfhs_lines or 'No data available'}\n"
                f"Nearby facilities:\n{fac_lines}\n"
                f"{followup_lines}"
                "Generate a numbered action plan for this family."
            )

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=700,
                system=_PLAN_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            plan_text = ""
            for block in response.content:
                if block.type == "text":
                    plan_text += block.text

            plan_text = _strip_facility_section(plan_text)

            if plan_text.strip():
                trace.update({
                    "provider": "claude",
                    "model": CLAUDE_MODEL,
                    "fallback_used": False,
                    "fallback_reason": None,
                })
                return plan_text.strip(), "claude", trace
            raise ValueError("empty Claude response")
        except Exception as exc:
            trace.update({
                "provider": "deterministic",
                "model": None,
                "fallback_used": True,
                "fallback_reason": f"Claude action plan generation failed: {type(exc).__name__}",
            })
            return (
                _deterministic_plan(profile, matched_pathways, nfhs_rows, facilities),
                "deterministic",
                trace,
            )

    trace["fallback_reason"] = "ANTHROPIC_API_KEY not set"
    return (
        _deterministic_plan(profile, matched_pathways, nfhs_rows, facilities),
        "deterministic",
        trace,
    )
