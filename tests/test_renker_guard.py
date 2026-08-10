from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if (
    importlib.util.find_spec("renker_core_authz") is None
    and importlib.util.find_spec("renker_core") is None
):
    pytest.skip("renker-core-authz / renker_core not installed", allow_module_level=True)

from core.renker_guard import RencoraFileGuard, is_available


def _guard(tmp_path):
    grants = [
        {
            "capability": "filesystem.write",
            "scope": str(tmp_path / "drafts"),
            "granted_to": "agent:sess-1",
        }
    ]
    return RencoraFileGuard(tmp_path / "audit.log", grants)


def test_available():
    assert is_available() is True


def test_allowed_write_executes(tmp_path):
    guard = _guard(tmp_path)
    target = tmp_path / "drafts" / "note.txt"
    result = guard.write("sess-1", str(target), "hello")
    assert result.decision.value == "ALLOW"
    assert target.read_text(encoding="utf-8") == "hello"


def test_denied_write_outside_scope(tmp_path):
    guard = _guard(tmp_path)
    target = tmp_path / "secret.txt"
    result = guard.write("sess-1", str(target), "nope")
    assert result.decision.value == "DENY"
    assert not target.exists()


def test_denied_traversal(tmp_path):
    guard = _guard(tmp_path)
    target = str(tmp_path / "drafts" / ".." / "secret.txt")
    result = guard.write("sess-1", target, "nope")
    assert result.decision.value == "DENY"
