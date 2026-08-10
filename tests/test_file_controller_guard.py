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


def _config_verbs(tmp_path, verbs, scope):
    cfg = tmp_path / "renker_capabilities.json"
    cfg.write_text(
        json.dumps(
            {
                "enforce": True,
                "session_id": "rencora",
                "grants": [
                    {"capability": verb, "scope": str(scope), "granted_to": "agent:rencora"}
                    for verb in verbs
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


def test_malformed_config_fails_closed(tmp_path, monkeypatch):
    cfg = tmp_path / "renker_capabilities.json"
    cfg.write_text("{ this is not valid json", encoding="utf-8")
    monkeypatch.setattr(rg, "default_config_path", lambda: cfg)
    out = file_controller.write_file(str(tmp_path / "drafts"), "e.txt", "no")
    assert "Access denied" in out
    assert not (tmp_path / "drafts" / "e.txt").exists()


def test_enforced_read_allows_in_scope_denies_outside(tmp_path, monkeypatch):
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "r.txt").write_text("secret notes", encoding="utf-8")
    (tmp_path / "vault").mkdir()
    (tmp_path / "vault" / "keys.txt").write_text("do not read", encoding="utf-8")
    cfg = _config_verbs(tmp_path, ["filesystem.read"], tmp_path / "drafts")
    monkeypatch.setattr(rg, "default_config_path", lambda: cfg)

    ok = file_controller.read_file(str(tmp_path / "drafts"), "r.txt")
    assert "secret notes" in ok
    denied = file_controller.read_file(str(tmp_path / "vault"), "keys.txt")
    assert "Access denied by capability policy" in denied


def test_enforced_delete_denies_outside_scope(tmp_path, monkeypatch):
    (tmp_path / "vault").mkdir()
    victim = tmp_path / "vault" / "records.txt"
    victim.write_text("patient records", encoding="utf-8")
    cfg = _config_verbs(tmp_path, ["filesystem.delete"], tmp_path / "drafts")
    monkeypatch.setattr(rg, "default_config_path", lambda: cfg)

    out = file_controller.delete_file(str(tmp_path / "vault"), "records.txt")
    assert "Access denied by capability policy" in out
    assert victim.exists()


def test_enforced_delete_allows_in_scope(tmp_path, monkeypatch):
    (tmp_path / "drafts").mkdir()
    doomed = tmp_path / "drafts" / "temp.txt"
    doomed.write_text("scratch", encoding="utf-8")
    cfg = _config_verbs(tmp_path, ["filesystem.delete"], tmp_path / "drafts")
    monkeypatch.setattr(rg, "default_config_path", lambda: cfg)

    out = file_controller.delete_file(str(tmp_path / "drafts"), "temp.txt")
    assert "Access denied" not in out
