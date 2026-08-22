"""actions/task_manager.py — nutzerseitige Aufgaben-/Automatisierungsverwaltung
(Teil 9). Duenner Handler ueber den persistenten todos-Funktionen in
database/db.py. Aktionen: create | list | update | complete | delete.

Rueckgabe ist stets ein kurzer, sprechbarer Text (wie die uebrigen Tools).
"""

from __future__ import annotations

from database.db import (
    create_todo, list_todos, get_todo, update_todo, complete_todo, delete_todo,
)

_PRIO = {0: "niedrig", 1: "normal", 2: "hoch", 3: "dringend"}


def _fmt(t: dict) -> str:
    prio = _PRIO.get(t.get("priority", 1), "normal")
    line = f"#{t['id']} [{t['status']}/{prio}] {t['title']}"
    dep = t.get("depends_on")
    if dep:
        d = get_todo(dep)
        if d and d["status"] != "done":
            line += f" (blockiert durch #{dep})"
    if t.get("due_at"):
        line += f" — faellig {t['due_at']}"
    if t.get("recurrence"):
        line += f" — wiederkehrend ({t['recurrence']})"
    return line


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def task_manager(parameters=None, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "list")).strip().lower()

    if action == "create":
        title = (p.get("title") or "").strip()
        if not title:
            return "Zum Anlegen fehlt der Titel der Aufgabe."
        try:
            tid = create_todo(
                title=title,
                details=p.get("details"),
                priority=_as_int(p.get("priority")) if p.get("priority") is not None else 1,
                parent_id=_as_int(p.get("parent_id")),
                depends_on=_as_int(p.get("depends_on")),
                due_at=p.get("due_at"),
                recurrence=p.get("recurrence"),
            )
        except ValueError as e:
            return f"Aufgabe konnte nicht angelegt werden: {e}"
        kind = "Subtask" if p.get("parent_id") else "Aufgabe"
        return f"{kind} #{tid} angelegt: {title}"

    if action == "list":
        status = p.get("status")
        parent = _as_int(p.get("parent_id"))
        todos = list_todos(
            status=status,
            include_done=bool(p.get("include_done")),
            parent_id=parent,
        )
        if not todos:
            return "Keine passenden Aufgaben."
        head = f"{len(todos)} Aufgabe(n):"
        return head + "\n" + "\n".join(_fmt(t) for t in todos)

    if action in ("update", "complete", "delete"):
        tid = _as_int(p.get("id"))
        if tid is None:
            return "Dafuer wird die Aufgaben-id benoetigt."
        if not get_todo(tid):
            return f"Keine Aufgabe mit id {tid} gefunden."

        if action == "delete":
            return f"Aufgabe #{tid} geloescht." if delete_todo(tid) else \
                   f"Aufgabe #{tid} konnte nicht geloescht werden."

        if action == "complete":
            complete_todo(tid)
            done = get_todo(tid)
            msg = f"Aufgabe #{tid} als erledigt markiert."
            rec = (done or {}).get("recurrence")
            if rec:
                new_id = create_todo(
                    title=done["title"], details=done.get("details"),
                    priority=done.get("priority", 1), recurrence=rec,
                    due_at=done.get("due_at"),
                )
                msg += f" Naechste Wiederholung als #{new_id} angelegt."
            return msg

        # update
        fields = {k: p[k] for k in
                  ("title", "details", "status", "priority", "parent_id",
                   "depends_on", "due_at", "recurrence") if k in p}
        if not fields:
            return "Keine aenderbaren Felder angegeben."
        try:
            update_todo(tid, **fields)
        except ValueError as e:
            return f"Aktualisierung fehlgeschlagen: {e}"
        return f"Aufgabe #{tid} aktualisiert."

    return ("Unbekannte Aktion. Erlaubt: create, list, update, complete, delete.")
