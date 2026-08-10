"""
actions/adaptive_brightness.py — Adaptive Helligkeit per Webcam (Wunsch 1.2).

Misst alle 10 Sekunden die Umgebungshelligkeit ueber die Webcam (mittlere
Bildhelligkeit) und passt die Bildschirmhelligkeit sanft an: dunkler Raum
-> Bildschirm dunkler (augenschonend), heller Raum -> heller.

Ehrlicher Hinweis: Das Setzen der Helligkeit funktioniert zuverlaessig bei
Laptops/internen Displays (WMI). Viele externe Desktop-Monitore lassen
sich unter Windows NICHT per Software regeln - dann meldet das Tool das
sauber, statt so zu tun als ob.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time

_state = {"running": False, "thread": None, "error": None, "last": None}

_MIN_BRIGHT, _MAX_BRIGHT = 25, 100
_INTERVAL = 10.0
_STEP_LIMIT = 15


def _ambient_to_target(mean_pixel: float) -> int:
    """Mittlere Webcam-Helligkeit (0-255) -> Ziel-Bildschirmhelligkeit (%)."""
    ratio = max(0.0, min(1.0, mean_pixel / 180.0))
    return int(_MIN_BRIGHT + ratio * (_MAX_BRIGHT - _MIN_BRIGHT))


def _set_brightness(percent: int) -> bool:
    """Setzt Helligkeit via WMI (Laptops/interne Displays)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
             f".WmiSetBrightness(1,{percent})"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _loop():
    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        _state["error"] = "Webcam nicht verfuegbar."
        _state["running"] = False
        return
    current = None
    try:
        while _state["running"]:
            ok, frame = cap.read()
            if ok:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                target = _ambient_to_target(float(gray.mean()))
                if current is None:
                    current = target
                else:

                    delta = max(-_STEP_LIMIT, min(_STEP_LIMIT, target - current))
                    current += delta
                if not _set_brightness(int(current)):
                    _state["error"] = ("Display laesst sich nicht per Software regeln "
                                       "(typisch bei externen Desktop-Monitoren).")
                    _state["running"] = False
                    return
                _state["last"] = int(current)

            for _ in range(int(_INTERVAL * 4)):
                if not _state["running"]:
                    break
                time.sleep(0.25)
    finally:
        cap.release()


def adaptive_brightness(parameters: dict, player=None) -> str:
    """Tool-Entry-Point. action: start | stop | status."""
    if sys.platform != "win32":
        return "Adaptive Helligkeit ist nur unter Windows verfuegbar."
    action = (parameters.get("action") or "start").lower()

    if action == "status":
        if _state["running"]:
            return f"Adaptive Helligkeit aktiv (aktuell {_state['last']}%)."
        if _state["error"]:
            return f"Inaktiv. Letzter Fehler: {_state['error']}"
        return "Adaptive Helligkeit ist inaktiv."

    if action == "stop":
        if not _state["running"]:
            return "Adaptive Helligkeit war bereits aus."
        _state["running"] = False
        t = _state["thread"]
        if t:
            t.join(timeout=3)
        return "Adaptive Helligkeit gestoppt."

    if _state["running"]:
        return "Adaptive Helligkeit laeuft bereits."
    try:
        import cv2  # noqa: F401
    except ImportError:
        return "opencv-python fehlt. Installiere es mit: pip install opencv-python"

    _state["error"] = None
    _state["running"] = True
    t = threading.Thread(target=_loop, daemon=True, name="AdaptiveBrightness")
    _state["thread"] = t
    t.start()
    time.sleep(1.2)
    if _state["error"]:
        _state["running"] = False
        return f"Konnte nicht starten: {_state['error']}"
    return ("Adaptive Helligkeit aktiv - der Bildschirm passt sich jetzt alle "
            "10 Sekunden sanft an das Umgebungslicht an. "
            "'Stopp adaptive Helligkeit' zum Beenden.")
