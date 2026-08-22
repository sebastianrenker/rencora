"""
actions/window_manager.py — Fenster-Management per Sprachbefehl (Wunsch 1.3).

"Fokussiere Chrome", "Minimiere alles", "Maximiere Spotify",
"Zeig Chrome und Word nebeneinander", "Welche Fenster sind offen?"

Basis-Version des gewuenschten Fenstermanagements - bewusst ohne
"praediktives" Verhalten (das braucht erst Nutzungsdaten), dafuer
sofort nutzbar und zuverlaessig. Nutzt pygetwindow (bereits in
requirements.txt).
"""
from __future__ import annotations

import sys


def _windows():
    import pygetwindow as gw
    return [w for w in gw.getAllWindows() if w.title.strip() and w.visible]


def _find(title_part: str):
    needle = title_part.lower().strip()
    return [w for w in _windows() if needle in w.title.lower()]


def window_manager(parameters: dict, player=None) -> str:
    """Tool-Entry-Point. actions: list|focus|minimize|maximize|close|minimize_all|side_by_side."""
    if sys.platform != "win32":
        return "Fenster-Management ist nur unter Windows verfuegbar."

    action = (parameters.get("action") or "list").lower()
    title  = parameters.get("window_title") or ""
    title2 = parameters.get("second_window") or ""

    try:
        import pygetwindow as gw  # noqa: F401
    except ImportError:
        return "pygetwindow fehlt. Installiere es mit: pip install pygetwindow"

    if action == "list":
        wins = _windows()
        if not wins:
            return "Keine offenen Fenster gefunden."
        titles = [w.title[:60] for w in wins[:15]]
        return f"{len(wins)} offene Fenster: " + "; ".join(titles)

    if action == "minimize_all":
        count = 0
        for w in _windows():
            try:
                w.minimize(); count += 1
            except Exception:
                pass
        return f"{count} Fenster minimiert - freier Desktop."

    if action == "side_by_side":
        if not title or not title2:
            return "Bitte zwei Fensternamen angeben (window_title und second_window)."
        a, b = _find(title), _find(title2)
        if not a or not b:
            missing = title if not a else title2
            return f"Fenster '{missing}' nicht gefunden. Sag 'welche Fenster sind offen' fuer die Liste."
        try:
            import pyautogui
            sw, sh = pyautogui.size()
            for win, x in ((a[0], 0), (b[0], sw // 2)):
                win.restore()
                win.resizeTo(sw // 2, sh)
                win.moveTo(x, 0)
                win.activate()
            return f"'{a[0].title[:40]}' links, '{b[0].title[:40]}' rechts angeordnet."
        except Exception as e:
            return f"Anordnen fehlgeschlagen: {e}"


    if not title:
        return "Bitte gib an, welches Fenster gemeint ist."
    hits = _find(title)
    if not hits:
        return f"Kein Fenster mit '{title}' im Titel gefunden. Sag 'welche Fenster sind offen'."
    w = hits[0]
    try:
        if action == "focus":
            w.restore(); w.activate()
            return f"'{w.title[:50]}' ist jetzt im Vordergrund."
        if action == "minimize":
            w.minimize()
            return f"'{w.title[:50]}' minimiert."
        if action == "maximize":
            w.restore(); w.maximize()
            return f"'{w.title[:50]}' maximiert."
        if action == "close":
            w.close()
            return f"'{w.title[:50]}' geschlossen."
        return f"Unbekannte Aktion '{action}'."
    except Exception as e:
        return f"Aktion fehlgeschlagen: {e}"
