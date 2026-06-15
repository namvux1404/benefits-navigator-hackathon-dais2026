import json
import sys
from pathlib import Path
from types import SimpleNamespace


SONNET = "claude-sonnet-4-5-20250929"


def _install_fake_anthropic(monkeypatch, create_func):
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return create_func(**kwargs)

    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeClient))
    return calls


def test_profile_extraction_attempts_claude_when_key_present(monkeypatch):
    import src.profile_extractor as pe

    def create_response(**kwargs):
        payload = {
            "pincode": "560001",
            "pregnant": False,
            "child_under_5": True,
            "child_age_months": 12,
            "immunization_need": True,
            "facility_search": True,
            "needs": ["child immunization", "nearby facility"],
        }
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(payload))]
        )

    calls = _install_fake_anthropic(monkeypatch, create_response)
    monkeypatch.setattr(pe, "ANTHROPIC_API_KEY", "test-secret-key")
    monkeypatch.setattr(pe, "CLAUDE_AVAILABLE", True)
    monkeypatch.setattr(pe, "CLAUDE_MODEL", SONNET)

    profile, trace = pe.extract_profile_with_trace("1-year-old baby in pincode 560001 needs vaccines")

    assert calls
    assert calls[0]["model"] == SONNET
    assert profile["extraction_method"] == "claude"
    assert trace["provider"] == "claude"
    assert trace["model"] == SONNET
    assert trace["fallback_used"] is False


def test_profile_extraction_failure_uses_deterministic_fallback(monkeypatch):
    import src.profile_extractor as pe

    def create_response(**kwargs):
        raise RuntimeError("network unavailable")

    _install_fake_anthropic(monkeypatch, create_response)
    monkeypatch.setattr(pe, "ANTHROPIC_API_KEY", "test-secret-key")
    monkeypatch.setattr(pe, "CLAUDE_AVAILABLE", True)
    monkeypatch.setattr(pe, "CLAUDE_MODEL", SONNET)

    profile, trace = pe.extract_profile_with_trace("I live in pincode 560001. I am pregnant.")

    assert profile["extraction_method"] == "regex"
    assert trace["provider"] == "deterministic"
    assert trace["fallback_used"] is True
    assert "RuntimeError" in trace["fallback_reason"]
    assert "test-secret-key" not in trace["fallback_reason"]


def test_action_plan_attempts_claude_when_key_present(monkeypatch):
    import src.action_plan as ap

    def create_response(**kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="1. Call a nearby facility.")]
        )

    calls = _install_fake_anthropic(monkeypatch, create_response)
    monkeypatch.setattr(ap, "ANTHROPIC_API_KEY", "test-secret-key")
    monkeypatch.setattr(ap, "CLAUDE_AVAILABLE", True)
    monkeypatch.setattr(ap, "CLAUDE_MODEL", SONNET)

    plan, method, trace = ap.generate_action_plan_with_trace(
        {"pincode": "560001", "immunization_need": True},
        [{"pathway_id": "immunization", "pathway_name": "Child Immunization Support"}],
        [],
        [],
    )

    assert calls
    assert calls[0]["model"] == SONNET
    assert "Call a nearby facility" in plan
    assert method == "claude"
    assert trace["provider"] == "claude"


def test_action_plan_label_for_claude_success():
    from src.ui_helpers import plan_method_label

    assert plan_method_label("claude") == "Claude Sonnet"


def test_action_plan_failure_uses_fallback_with_reason(monkeypatch):
    import src.action_plan as ap

    def create_response(**kwargs):
        raise RuntimeError("timeout")

    _install_fake_anthropic(monkeypatch, create_response)
    monkeypatch.setattr(ap, "ANTHROPIC_API_KEY", "test-secret-key")
    monkeypatch.setattr(ap, "CLAUDE_AVAILABLE", True)
    monkeypatch.setattr(ap, "CLAUDE_MODEL", SONNET)

    _plan, method, trace = ap.generate_action_plan_with_trace(
        {"pincode": "560001", "immunization_need": True},
        [{"pathway_id": "immunization", "pathway_name": "Child Immunization Support"}],
        [],
        [],
    )

    assert method == "deterministic"
    assert trace["provider"] == "deterministic"
    assert trace["fallback_used"] is True
    assert "RuntimeError" in trace["fallback_reason"]
    assert "test-secret-key" not in trace["fallback_reason"]


def test_rules_engine_trace_remains_deterministic():
    from src.agent_trace import rules_engine_trace

    trace = rules_engine_trace()
    assert trace["provider"] == "deterministic"
    assert trace["model"] is None
    assert trace["fallback_used"] is False


def test_debug_ui_contains_agent_trace_without_secret_value():
    app_text = Path("app.py").read_text(encoding="utf-8")

    assert "Claude Agent Trace" in app_text
    assert "Profile extraction" in app_text
    assert "Follow-up questions" in app_text
    assert "Action plan" in app_text
    assert "Rules engine" in app_text
    assert "test-secret-key" not in app_text
