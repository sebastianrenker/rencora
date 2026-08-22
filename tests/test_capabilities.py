"""Tests fuer Berechtigungs-Taxonomie, Tool-Registry und Allowlist."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import policy


def test_permission_sets():
    assert policy.capabilities("web_search") == frozenset({policy.READ, policy.NETWORK})
    assert policy.NETWORK in policy.capabilities("send_message")
    assert policy.EXECUTE in policy.capabilities("dev_agent")
    # Unbekanntes Tool: maximal wirkmaechtig (sicherer Default)
    assert policy.capabilities("does_not_exist") == policy.DEFAULT_CAPS


def test_every_known_tool_has_spec():
    reg = policy.registry()
    names = {s["name"] for s in reg}
    for expected in ("task_manager", "dev_agent", "web_search", "send_message"):
        assert expected in names
    # nach Risiko absteigend sortiert
    risks = [s["risk"] for s in reg]
    assert risks == sorted(risks, reverse=True)


def test_spec_fields_consistent():
    spec = policy.tool_spec("dev_agent")
    assert spec["requires_confirmation"] is True
    assert "EXECUTE" in spec["permissions"]
    assert spec["enabled"] is True
    low = policy.tool_spec("system_status")
    assert low["requires_confirmation"] is False


def test_tool_allowed_respects_disabled(monkeypatch):
    monkeypatch.setattr(policy, "disabled_tools", lambda: frozenset({"browser_control"}))
    assert not policy.tool_allowed("browser_control")
    assert policy.tool_allowed("web_search")
    assert policy.tool_spec("browser_control")["enabled"] is False
