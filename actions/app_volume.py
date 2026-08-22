"""
actions/app_volume.py — Lautstaerkemixer auf Anwendungsebene (Windows).

Wunsch 1.1: "Feinjustierung des Lautstaerkemixers auf Anwendungsebene."
Nutzt pycaw (bereits in requirements.txt), um die Lautstaerke einzelner
Programme zu setzen/lesen/muten - wie der Windows-Lautstaerkemixer, nur
per Sprachbefehl: "Setz Spotify auf 30 Prozent", "Mute Chrome",
"Welche Apps spielen gerade Ton?".
"""
from __future__ import annotations

import sys


def _sessions():
    from pycaw.pycaw import AudioUtilities
    return [s for s in AudioUtilities.GetAllSessions() if s.Process]


def _match(sessions, app_name: str):
    needle = app_name.lower().replace(".exe", "").strip()
    hits = []
    for s in sessions:
        pname = (s.Process.name() or "").lower().replace(".exe", "")
        if needle == pname or needle in pname or pname in needle:
            hits.append(s)
    return hits


def app_volume(parameters: dict, player=None) -> str:
    """Tool-Entry-Point. actions: list | set | mute | unmute."""
    if sys.platform != "win32":
        return "App-Lautstaerkesteuerung ist nur unter Windows verfuegbar."

    action = (parameters.get("action") or "list").lower()
    app    = parameters.get("app_name") or ""
    level  = parameters.get("level")

    try:
        sessions = _sessions()
    except Exception as e:
        return f"Konnte Audio-Sessions nicht lesen: {e}"

    if action == "list":
        if not sessions:
            return "Aktuell spielt keine Anwendung Ton."
        lines = []
        for s in sessions:
            try:
                vol = s.SimpleAudioVolume
                pct = round(vol.GetMasterVolume() * 100)
                muted = " (stumm)" if vol.GetMute() else ""
                lines.append(f"{s.Process.name()}: {pct}%{muted}")
            except Exception:
                continue
        return "Aktive Audio-Anwendungen: " + "; ".join(lines)

    if not app:
        return "Bitte gib an, welche Anwendung gemeint ist (z.B. Spotify, Chrome)."

    hits = _match(sessions, app)
    if not hits:
        names = ", ".join(sorted({s.Process.name() for s in sessions})) or "keine"
        return (f"'{app}' spielt gerade keinen Ton oder laeuft nicht. "
                f"Aktive Audio-Apps: {names}.")

    changed = []
    for s in hits:
        try:
            vol = s.SimpleAudioVolume
            if action == "set":
                if level is None:
                    return "Bitte gib eine Ziel-Lautstaerke in Prozent an (0-100)."
                pct = max(0.0, min(100.0, float(level)))
                vol.SetMasterVolume(pct / 100.0, None)
                changed.append(f"{s.Process.name()} auf {round(pct)}%")
            elif action == "mute":
                vol.SetMute(1, None)
                changed.append(f"{s.Process.name()} stummgeschaltet")
            elif action == "unmute":
                vol.SetMute(0, None)
                changed.append(f"{s.Process.name()} laut geschaltet")
            else:
                return f"Unbekannte Aktion '{action}'. Erlaubt: list, set, mute, unmute."
        except Exception as e:
            changed.append(f"{s.Process.name()}: Fehler ({e})")

    return "Erledigt: " + "; ".join(changed)
