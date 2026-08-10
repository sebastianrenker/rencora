"""
actions/gesture_control.py — Rencora-Gestensteuerung per Webcam.

Inspiriert vom "DenkHub Virtual Desktop"-Video: Hand vor die Webcam halten
und den PC steuern, ganz ohne Maus.

Gesten:
  - Offene Hand bewegen  -> Cursor folgt dem Zeigefinger
  - Pinch (Daumen+Zeigefinger zusammen)        -> Linksklick
  - Pinch halten und bewegen                   -> Ziehen (Drag & Drop)
  - Faust                                      -> loslassen / nichts

Nutzt mediapipe (Hand-Tracking) + pyautogui (Cursor). Laeuft als
Hintergrund-Thread; Start/Stopp per Sprachbefehl ("aktiviere
Gestensteuerung" / "stopp Gestensteuerung").
"""
from __future__ import annotations

import threading
import time

_state = {"running": False, "thread": None, "error": None}


_PINCH_ON  = 0.045
_PINCH_OFF = 0.070
_SMOOTHING = 0.35


def _loop():
    import cv2
    import mediapipe as mp
    import pyautogui

    pyautogui.FAILSAFE = False
    screen_w, screen_h = pyautogui.size()

    hands = mp.solutions.hands.Hands(
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        _state["error"] = "Webcam konnte nicht geoeffnet werden."
        _state["running"] = False
        return

    prev_x, prev_y = pyautogui.position()
    pinching = False
    try:
        while _state["running"]:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)

            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                idx_tip, thumb_tip = lm[8], lm[4]


                target_x = idx_tip.x * screen_w
                target_y = idx_tip.y * screen_h
                new_x = prev_x + (target_x - prev_x) * _SMOOTHING
                new_y = prev_y + (target_y - prev_y) * _SMOOTHING
                pyautogui.moveTo(new_x, new_y, _pause=False)
                prev_x, prev_y = new_x, new_y


                dist = ((idx_tip.x - thumb_tip.x) ** 2 +
                        (idx_tip.y - thumb_tip.y) ** 2) ** 0.5
                if not pinching and dist < _PINCH_ON:
                    pinching = True
                    pyautogui.mouseDown(_pause=False)
                elif pinching and dist > _PINCH_OFF:
                    pinching = False
                    pyautogui.mouseUp(_pause=False)

            time.sleep(0.01)
    finally:
        if pinching:
            try:
                pyautogui.mouseUp(_pause=False)
            except Exception:
                pass
        cap.release()
        hands.close()


def gesture_control(parameters: dict, player=None) -> str:
    """Tool-Entry-Point. action: start | stop | status."""
    action = (parameters.get("action") or "start").lower()

    if action == "status":
        if _state["running"]:
            return "Gestensteuerung ist aktiv. Offene Hand bewegt den Cursor, Pinch klickt."
        if _state["error"]:
            return f"Gestensteuerung inaktiv. Letzter Fehler: {_state['error']}"
        return "Gestensteuerung ist inaktiv."

    if action == "stop":
        if not _state["running"]:
            return "Gestensteuerung war bereits aus."
        _state["running"] = False
        t = _state["thread"]
        if t:
            t.join(timeout=2)
        return "Gestensteuerung gestoppt."


    if _state["running"]:
        return "Gestensteuerung laeuft bereits."
    try:
        import cv2          # noqa: F401
        import mediapipe    # noqa: F401
        import pyautogui    # noqa: F401
    except ImportError as e:
        return (f"Gestensteuerung braucht ein fehlendes Paket: {e}. "
                "Installiere es mit: pip install mediapipe opencv-python pyautogui")

    _state["error"] = None
    _state["running"] = True
    t = threading.Thread(target=_loop, daemon=True, name="GestureControl")
    _state["thread"] = t
    t.start()
    time.sleep(0.8)
    if _state["error"]:
        _state["running"] = False
        return f"Gestensteuerung konnte nicht starten: {_state['error']}"
    return ("Gestensteuerung aktiv! Halte deine Hand vor die Webcam: "
            "Zeigefinger bewegt den Cursor, Daumen+Zeigefinger zusammen = Klick, "
            "zusammenhalten und bewegen = Ziehen. Sag 'stopp Gestensteuerung' zum Beenden.")
