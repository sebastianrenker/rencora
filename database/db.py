"""
database/db.py — sqlite3-Connection-Helper fuer RENCORA (Teil 11/12 des
Architektur-Reviews). Ein einzelnes lokales .db-File, kein Server-Betrieb
noetig. Laeuft im Dual-Write-Verfahren parallel zu den bestehenden JSON-
Dateien (memory/long_term.json, memory/second_brain.json) - die JSON-
Dateien bleiben die primaere Quelle, SQLite ergaenzt sie um strukturierte,
abfragbare Historie (Projekte/Aufgaben/Entscheidungen/Agent-Laeufe).

Verwendung:

    from database.db import get_connection, init_db, record_agent_run

    init_db()  # einmalig beim Start aufrufen (main.py), idempotent
    with get_connection() as conn:
        conn.execute("INSERT INTO memories (...) VALUES (...)")
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR    = _get_base_dir()
DB_PATH     = BASE_DIR / "database" / "rencora.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_lock = threading.Lock()
_initialized = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection():
    """Context-manager liefert eine sqlite3-Connection mit Row-Factory und
    committet/schliesst automatisch. Ein Lock schuetzt vor gleichzeitigen
    Schreibzugriffen aus mehreren Threads (main.py nutzt threading/asyncio
    parallel)."""
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    """Legt die DB-Datei + alle Tabellen an, falls noch nicht vorhanden.
    Idempotent - kann bei jedem main.py-Start gefahrlos erneut aufgerufen
    werden."""
    global _initialized
    if _initialized:
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema)
    _initialized = True


# ── Convenience-Funktionen fuer die haeufigsten Schreibzugriffe ────────────

def upsert_memory(category: str, key: str, value: str) -> None:
    """Spiegelt einen save_memory()-Aufruf zusaetzlich in die memories-
    Tabelle (Dual-Write neben long_term.json, siehe Teil 6)."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO memories (category, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(category, key) DO UPDATE SET
                   value = excluded.value, updated_at = excluded.updated_at""",
            (category, key, value, _now_iso()),
        )


def insert_knowledge(source_type: str, source_ref: str, summary: str, tags: list[str] | None = None) -> int:
    """Spiegelt einen second_brain_save()-Aufruf zusaetzlich in die
    knowledge-Tabelle (Dual-Write neben second_brain.json, siehe Teil 6)."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO knowledge (source_type, source_ref, summary, tags, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (source_type, source_ref, summary, json.dumps(tags or [], ensure_ascii=False), _now_iso()),
        )
        return cur.lastrowid


_TODO_STATUS = ("pending", "active", "blocked", "done", "cancelled")


def create_todo(title: str, details: str | None = None, priority: int = 1,
                parent_id: int | None = None, depends_on: int | None = None,
                due_at: str | None = None, recurrence: str | None = None) -> int:
    """Legt eine Aufgabe/Subtask an (Teil 9). Gibt die neue id zurueck."""
    init_db()
    title = (title or "").strip()
    if not title:
        raise ValueError("title darf nicht leer sein")
    priority = max(0, min(3, int(priority)))
    now = _now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO todos
                 (title, details, status, priority, parent_id, depends_on,
                  due_at, recurrence, created_at, updated_at)
               VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (title, details, priority, parent_id, depends_on, due_at,
             recurrence, now, now),
        )
        return cur.lastrowid


def get_todo(todo_id: int) -> dict | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return dict(row) if row else None


def list_todos(status: str | None = None, include_done: bool = False,
               parent_id: int | None = None) -> list[dict]:
    """Listet Aufgaben. Ohne Filter: alle offenen (nicht done/cancelled),
    nach Prioritaet absteigend, dann Alter."""
    init_db()
    clauses, params = [], []
    if status:
        clauses.append("status = ?"); params.append(status)
    elif not include_done:
        clauses.append("status NOT IN ('done','cancelled')")
    if parent_id is not None:
        clauses.append("parent_id = ?"); params.append(parent_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM todos {where} ORDER BY priority DESC, id ASC", params
        ).fetchall()
        return [dict(r) for r in rows]


def update_todo(todo_id: int, **fields) -> bool:
    """Aktualisiert erlaubte Felder (title, details, status, priority,
    parent_id, depends_on, due_at, recurrence). Setzt done_at bei status=done."""
    allowed = {"title", "details", "status", "priority", "parent_id",
               "depends_on", "due_at", "recurrence"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if "status" in sets and sets["status"] not in _TODO_STATUS:
        raise ValueError(f"ungueltiger Status: {sets['status']}")
    if "priority" in sets:
        sets["priority"] = max(0, min(3, int(sets["priority"])))
    if not sets:
        return False
    init_db()
    cols = ", ".join(f"{k} = ?" for k in sets)
    params = list(sets.values())
    done_at_sql = ""
    if sets.get("status") == "done":
        done_at_sql = ", done_at = ?"
        params.append(_now_iso())
    params.append(_now_iso())   # updated_at
    params.append(todo_id)
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE todos SET {cols}{done_at_sql}, updated_at = ? WHERE id = ?",
            params,
        )
        return cur.rowcount > 0


def complete_todo(todo_id: int) -> bool:
    return update_todo(todo_id, status="done")


def delete_todo(todo_id: int) -> bool:
    init_db()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        return cur.rowcount > 0


def record_agent_run(agent: str, tool_name: str, params: dict, result: str,
                      status: str, started_at: float, finished_at: float | None = None) -> None:
    """Protokolliert einen AgentRouter.dispatch()-Aufruf (Aufgabenhistorie,
    siehe Teil 6/11). status muss 'success' oder 'failed' sein."""
    init_db()
    try:
        params_json = json.dumps(params, ensure_ascii=False, default=str)
    except Exception:
        params_json = str(params)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO agent_runs (agent, tool_name, params, result, status, started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                agent, tool_name, params_json, str(result)[:2000], status,
                datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat(),
                datetime.fromtimestamp(finished_at, tz=timezone.utc).isoformat() if finished_at else None,
            ),
        )
