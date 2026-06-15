from __future__ import annotations
import json
import re

from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_AVAILABLE

_PINCODE_RE = re.compile(r'\b([1-9]\d{5})\b')
_AGE_MONTHS_RE = re.compile(r'(\d+)\s*[-\s]?month', re.I)
_AGE_YEARS_RE = re.compile(r'(\d+)\s*[-\s]?year', re.I)

_EXTRACT_SYSTEM = """\
You are a health benefits intake assistant for families in India.
Extract a structured profile from the user's description.
Return ONLY a valid JSON object — no markdown, no explanation, no code fences.
Use exactly these fields:
{
  "pincode": "string or null",
  "pregnant": false,
  "recently_delivered": false,
  "child_under_5": false,
  "child_age_months": null,
  "nutrition_need": false,
  "uninsured": false,
  "low_income": false,
  "water_sanitation_need": false,
  "child_diarrhea_risk": false,
  "adult_woman": false,
  "screening_need": false,
  "immunization_need": false,
  "facility_search": false,
  "needs": []
}
Rules:
- adult_woman: true whenever person is female (including pregnant/recently-delivered mothers)
- child_age_months: integer months (convert: 1 year = 12 months); null if not mentioned
- child_under_5: true if any child under 60 months / 5 years mentioned
- needs: subset of ["maternal_care","child_nutrition","child immunization","health_insurance","sanitation","screening","nearby facility"]
"""


def _default_profile(raw_text: str) -> dict:
    return {
        "pincode": None,
        "pregnant": False,
        "recently_delivered": False,
        "child_under_5": False,
        "child_age_months": None,
        "nutrition_need": False,
        "uninsured": False,
        "low_income": False,
        "water_sanitation_need": False,
        "child_diarrhea_risk": False,
        "adult_woman": False,
        "screening_need": False,
        "immunization_need": False,
        "facility_search": False,
        "needs": [],
        "raw_text": raw_text,
        "extraction_method": "default",
    }


def _regex_extract(text: str) -> dict:
    profile = _default_profile(text)
    profile["extraction_method"] = "regex"
    t = text.lower()

    m = _PINCODE_RE.search(text)
    if m:
        profile["pincode"] = m.group(1)

    profile["pregnant"] = bool(re.search(r'\bpregnant\b', t))
    profile["recently_delivered"] = bool(
        re.search(r'(just delivered|recently delivered|newborn|postnatal|post.?natal)', t)
    )
    profile["adult_woman"] = bool(
        re.search(r'\b(pregnant|woman|mother|wife|she\b|her\b|girl)\b', t)
    )
    profile["nutrition_need"] = bool(
        re.search(r'\b(nutrition|malnourish|undernourish|stunted|hungry|food)\b', t)
    )
    profile["uninsured"] = bool(re.search(r'\b(no insurance|uninsured|without insurance)\b', t))
    profile["low_income"] = bool(re.search(r'\b(low.?income|poor|poverty|bpl|below poverty)\b', t))
    profile["water_sanitation_need"] = bool(
        re.search(r'\b(water|sanitation|toilet|hygiene|open defecation)\b', t)
    )
    profile["child_diarrhea_risk"] = bool(re.search(r'\b(diarr?ho?ea)\b', t))
    profile["screening_need"] = bool(
        re.search(r'\b(screening|cervical|breast exam|cancer check)\b', t)
    )
    profile["immunization_need"] = bool(
        re.search(r'\b(vaccin(?:e|es|ation|ations)?|immuni[sz](?:e|ation|ations)?|dose|doses)\b', t)
    )
    profile["facility_search"] = bool(
        re.search(
            r'\b(closest|nearby|nearest|where (?:can|should)|place|facility|hospital|clinic|doctor|health.?cent(?:er|re))\b',
            t,
        )
    )

    # Derive child age in months (month mention takes priority over year)
    age_months: int | None = None
    m_mo = _AGE_MONTHS_RE.search(t)
    if m_mo:
        age_months = int(m_mo.group(1))
    else:
        m_yr = _AGE_YEARS_RE.search(t)
        if m_yr:
            years = int(m_yr.group(1))
            if years < 15:  # guard against adult age mentions
                age_months = years * 12

    if age_months is not None and age_months < 60:
        profile["child_under_5"] = True
        profile["child_age_months"] = age_months

    # Also flag child_under_5 from keyword mentions even without age
    if re.search(r'\b(child|baby|infant|toddler|son|daughter|kids?)\b', t):
        profile["child_under_5"] = True

    # Infer adult_woman from pregnancy
    if profile["pregnant"] or profile["recently_delivered"]:
        profile["adult_woman"] = True

    # Build needs list
    needs: list[str] = []
    if profile["pregnant"] or profile["recently_delivered"]:
        needs.append("maternal_care")
    if profile["child_under_5"] and profile["nutrition_need"]:
        needs.append("child_nutrition")
    if profile["immunization_need"]:
        needs.append("child immunization")
    if profile["uninsured"] or profile["low_income"]:
        needs.append("health_insurance")
    if profile["water_sanitation_need"]:
        needs.append("sanitation")
    if profile["facility_search"]:
        needs.append("nearby facility")
    profile["needs"] = list(dict.fromkeys(needs))

    return profile


def extract_profile(text: str) -> dict:
    """Extract family profile from free text. Uses Claude if available, else regex."""
    profile, _trace = extract_profile_with_trace(text)
    return profile


def extract_profile_with_trace(text: str) -> tuple[dict, dict]:
    """Extract family profile and return agent trace metadata."""
    trace = {
        "provider": "deterministic",
        "model": None,
        "fallback_used": False,
        "fallback_reason": None,
    }
    if not text.strip():
        trace["fallback_reason"] = "empty input"
        return _default_profile(text), trace

    if CLAUDE_AVAILABLE:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                system=_EXTRACT_SYSTEM,
                messages=[{"role": "user", "content": text}],
            )
            raw_json = ""
            for block in response.content:
                if block.type == "text":
                    raw_json = block.text.strip()
                    break

            # Strip any accidental markdown code fences
            raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json)
            raw_json = re.sub(r'\s*```$', '', raw_json).strip()

            if raw_json:
                parsed = json.loads(raw_json)
                parsed["raw_text"] = text
                parsed["extraction_method"] = "claude"
                # Fill in any missing keys with defaults
                defaults = _default_profile(text)
                for k, v in defaults.items():
                    if k not in parsed:
                        parsed[k] = v
                # Guarantee adult_woman inference
                if parsed.get("pregnant") or parsed.get("recently_delivered"):
                    parsed["adult_woman"] = True
                parsed = _enrich_profile_signals(parsed, text)
                trace.update({
                    "provider": "claude",
                    "model": CLAUDE_MODEL,
                    "fallback_used": False,
                    "fallback_reason": None,
                })
                return parsed, trace
        except Exception as exc:
            trace.update({
                "provider": "deterministic",
                "model": None,
                "fallback_used": True,
                "fallback_reason": f"Claude profile extraction failed: {type(exc).__name__}",
            })
            return _regex_extract(text), trace

    trace["fallback_reason"] = "ANTHROPIC_API_KEY not set"
    return _regex_extract(text), trace


def _enrich_profile_signals(profile: dict, text: str) -> dict:
    """Fill deterministic signal fields that Claude may omit."""
    regex_profile = _regex_extract(text)
    for key in ("immunization_need", "facility_search"):
        if key not in profile or profile.get(key) in (None, False):
            profile[key] = regex_profile.get(key, False)

    needs = list(profile.get("needs") or [])
    for need in regex_profile.get("needs", []):
        if need not in needs:
            needs.append(need)
    profile["needs"] = needs
    return profile
