from __future__ import annotations

from .config import CLAUDE_MODEL


def trace_entry(
    provider: str,
    model: str | None = None,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
) -> dict:
    return {
        "provider": provider,
        "model": model,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }


def deterministic_trace(
    fallback_used: bool = False,
    fallback_reason: str | None = None,
) -> dict:
    return trace_entry("deterministic", None, fallback_used, fallback_reason)


def claude_trace() -> dict:
    return trace_entry("claude", CLAUDE_MODEL, False, None)


def rules_engine_trace() -> dict:
    return trace_entry("deterministic", None, False, None)


def empty_agent_trace() -> dict:
    return {
        "profile_extraction": deterministic_trace(),
        "followup_questions": deterministic_trace(),
        "action_plan": deterministic_trace(),
        "rules_engine": rules_engine_trace(),
    }


def step_display_label(step_trace: dict | None, *, rules_engine: bool = False) -> str:
    step_trace = step_trace or {}
    provider = step_trace.get("provider")
    if provider == "claude":
        return "Claude Sonnet"
    if rules_engine:
        return "deterministic"
    return "Deterministic fallback"
