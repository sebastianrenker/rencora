from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if importlib.util.find_spec("renker_core") is None:
    pytest.skip("renker_core not installed", allow_module_level=True)

import core.renker_guard as rg
from actions import file_controller


def _config(tmp_path, enforce, scope):
    cfg = tmp_path / "renker_capabilities.json"
    cfg.write_text(
        json.dumps(
            {
                "enforce": enforce,
                "session_id": "rencora",
                "grants": [
                    {
                        "capability": "filesystem.write",
                        "scope": str(scope),
                        "granted_to": "agent:rencora",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return cfg


def test_no_config_behaves_normally(tmp_path, monkeypatch):
    monkeypatch.setattr(rg, "default_config_path", lambda: tmp_path / "absent.json")
    out = file_controller.create_file(str(tmp_path / "drafts"), "a.txt", "hi")
    assert "File created" in out
    assert (tmp_path / "drafts" / "a.txt").read_text(encoding="utf-8") == "hi"


def test_enforced_allows_in_scope(tmp_path, monkeypatch):
    cfg = _config(tmp_path, True, tmp_path / "drafts")
    monkeypatch.setattr(rg, "default_config_path", lambda: cfg)
    out = file_controller.write_file(str(tmp_path / "drafts"), "b.txt", "ok")
    assert "Written to" in out
    assert (tmp_path / "drafts" / "b.txt").exists()


def test_enforced_denies_out_of_scope(tmp_path, monkeypatch):
    cfg = _config(tmp_path, True, tmp_path / "drafts")
    monkeypatch.setattr(rg, "default_config_path", lambda: cfg)
    out = file_controller.write_file(str(tmp_path / "other"), "c.txt", "no")
    assert "capability policy" in out
    assert not (tmp_path / "other" / "c.txt").exists()


def test_enforced_denies_disabled_flag_allows(tmp_path, monkeypatch):
    cfg = _config(tmp_path, False, tmp_path / "drafts")
    monkeypatch.setattr(rg, "default_config_path", lambda: cfg)
    out = file_controller.write_file(str(tmp_path / "other"), "d.txt", "ok")
    assert "Written to" in out
    assert (tmp_path / "other" / "d.txt").exists()
