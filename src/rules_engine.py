from __future__ import annotations
import re

_BETWEEN_RE = re.compile(r'^(\w+)\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)$', re.I)
_BOOL_RE = re.compile(r'^(\w+)\s*=\s*(true|false)$', re.I)

# Lower number = shown first.  Women's screening is "also consider" — placed last.
_PATHWAY_PRIORITY: dict[str, int] = {
    "maternal_care": 0,
    "child_nutrition": 1,
    "immunization": 2,
    "health_insurance_awareness": 3,
    "household_health_risk": 4,
    "women_preventive_screening": 5,
}


def _eval_atom(atom: str, profile: dict) -> bool:
    atom = atom.strip()

    m = _BETWEEN_RE.match(atom)
    if m:
        key, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
        val = profile.get(key)
        if val is None:
            return False
        try:
            return lo <= int(val) <= hi
        except (ValueError, TypeError):
            return False

    m = _BOOL_RE.match(atom)
    if m:
        key = m.group(1)
        expected = m.group(2).lower() == "true"
        return bool(profile.get(key)) == expected

    return False


def _eval_condition(condition: str, profile: dict) -> bool:
    """Evaluate a trigger_condition DSL string against a profile dict.

    Supported forms:
        key=true | key=false
        key BETWEEN n AND m
        expr OR expr [OR expr ...]
    """
    stripped = condition.strip()
    # BETWEEN takes priority so we don't misparse its embedded AND keyword
    if _BETWEEN_RE.match(stripped):
        return _eval_atom(stripped, profile)
    parts = re.split(r'\bOR\b', stripped, flags=re.I)
    return any(_eval_atom(p, profile) for p in parts)


def match_pathways(profile: dict, pathways: list[dict]) -> list[dict]:
    """Return matched pathways sorted by clinical priority (maternal/child first, screening last)."""
    matched = []
    for pw in pathways:
        flag = str(pw.get("active_flag", "true")).strip().lower()
        if flag in ("false", "0", "no"):
            continue
        cond = pw.get("trigger_condition", "")
        if cond and _eval_condition(cond, profile):
            matched.append(pw)
    matched.sort(key=lambda pw: _PATHWAY_PRIORITY.get(pw.get("pathway_id", ""), 99))
    return matched
