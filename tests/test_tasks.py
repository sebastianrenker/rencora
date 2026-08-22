"""Tests fuer das persistente Aufgaben-/Automatisierungssystem (todos)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import db
from actions.task_manager import task_manager


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_initialized", False)
    db.init_db()


def test_create_list_priority_order(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    low = db.create_todo("Doku pruefen", priority=1)
    high = db.create_todo("Tests ausfuehren", priority=3)
    todos = db.list_todos()
    assert len(todos) == 2
    assert todos[0]["id"] == high      # hoehere Prioritaet zuerst
    assert todos[1]["id"] == low


def test_subtasks_and_filter(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    parent = db.create_todo("Release vorbereiten")
    sub = db.create_todo("Tests gruen", parent_id=parent)
    subs = db.list_todos(parent_id=parent)
    assert [t["id"] for t in subs] == [sub]


def test_complete_sets_done_and_hides_from_open(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    tid = db.create_todo("Build erstellen")
    assert db.complete_todo(tid) is True
    row = db.get_todo(tid)
    assert row["status"] == "done" and row["done_at"]
    assert db.list_todos() == []                    # nicht mehr offen
    assert len(db.list_todos(include_done=True)) == 1


def test_update_invalid_status_rejected(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    tid = db.create_todo("X")
    try:
        db.update_todo(tid, status="unsinn")
        assert False, "sollte ValueError werfen"
    except ValueError:
        pass


def test_delete(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    tid = db.create_todo("weg damit")
    assert db.delete_todo(tid) is True
    assert db.get_todo(tid) is None


def test_action_layer_end_to_end(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    out = task_manager({"action": "create", "title": "Doku schreiben", "priority": 2})
    assert "angelegt" in out
    listing = task_manager({"action": "list"})
    assert "Doku schreiben" in listing
    assert task_manager({"action": "create"}).startswith("Zum Anlegen fehlt")
    assert "id" in task_manager({"action": "complete"})     # ohne id
    tid = db.list_todos()[0]["id"]
    assert "erledigt" in task_manager({"action": "complete", "id": tid})


def test_recurring_task_reschedules_on_complete(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    tid = db.create_todo("Standup", recurrence="daily")
    msg = task_manager({"action": "complete", "id": tid})
    assert "Wiederholung" in msg
    # eine neue offene Instanz existiert wieder
    assert len(db.list_todos()) == 1


def test_dependency_shown_as_blocked(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    first = db.create_todo("A")
    db.create_todo("B", depends_on=first)
    listing = task_manager({"action": "list"})
    assert "blockiert durch #%d" % first in listing
