"""
core/hologram_bridge.py

NEUE DATEI - Teil der Integration mit Neural Hologram OS.

Diese Datei ist komplett eigenstaendig und ergaenzt RENCORA, ohne
bestehenden Code zu ersetzen. Sie stellt eine duenne, fehlertolerante
Bruecke zum Neural Hologram OS her:

  RENCORA (dieser Prozess)  --WebSocket-->  Neural Hologram OS
                                              (lauscht auf ws://127.0.0.1:8765,
                                               siehe brain_core/connector.py)

WICHTIG - Fehlertoleranz:
Neural Hologram OS ist OPTIONAL. Wenn es nicht laeuft (Verbindung
schlaegt fehl), darf RENCORA dadurch NIEMALS abstuerzen, haengen bleiben
oder langsamer werden. Jede send_event()-Methode ist deshalb:
  - non-blocking fuer den Aufrufer (Events werden in einer Queue
    abgelegt, ein Hintergrundthread mit eigenem asyncio-Loop sendet sie)
  - komplett still bei Verbindungsfehlern (kein Crash, kein Traceback
    im Log, da das fuer den Nutzer kein RENCORA-Fehler ist)
  - automatisch wiederverbindend, falls Neural Hologram OS spaeter
    gestartet wird

Verwendung (siehe ui.py, set_state()):
    from core.hologram_bridge import hologram_bridge
    hologram_bridge.send_thought_state("thinking")
    hologram_bridge.send_agent_event("dev_agent", status="running")
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("hologram_bridge")
logger.setLevel(logging.WARNING)


_HOLOGRAM_WS_URL = "ws://127.0.0.1:8765"


_STATE_MAP = {
    "LISTENING": "idle",
    "THINKING": "thinking",
    "SPEAKING": "answering",
    "SLEEPING": "idle",
}


class HologramBridge:
    """
    Singleton-artige Bruecke (eine Instanz pro Prozess, siehe
    `hologram_bridge` Modul-Variable unten). Haelt eine Queue fuer
    ausgehende Events und einen Hintergrundthread, der versucht, sie an
    Neural Hologram OS zu senden - ohne den Rest von RENCORA je zu
    blockieren.

    Empfaengt zusaetzlich eingehende command-Events vom Hologramm
    (z.B. von Gesten oder Sprachbefehlen erkannt) und leitet sie an
    einen registrierbaren Callback weiter (siehe on_command).
    """

    def __init__(self, ws_url: str = _HOLOGRAM_WS_URL) -> None:
        self._ws_url = ws_url
        self._queue: queue.Queue = queue.Queue(maxsize=200)
        self._thread: threading.Thread | None = None
        self._stop_requested = threading.Event()
        self._connected = False
        self._on_command_callback = None

    def start(self) -> None:
        """Startet den Hintergrund-Sendethread. Sicher mehrfach aufrufbar."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="HologramBridgeThread"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


    def send_thought_state(self, rencora_state: str) -> None:
        """
        Uebersetzt einen RENCORA-internen Zustand (LISTENING/THINKING/
        SPEAKING/SLEEPING) in einen Neural-Hologram-OS thought_state und
        legt das Event in die Sendequeue.
        """
        mapped = _STATE_MAP.get(rencora_state)
        if mapped is None:
            return
        self._enqueue("thought", {"state": mapped})

    def send_agent_event(self, agent_id: str, name: str, status: str = "running") -> None:
        """status: 'idle' | 'running' | 'error'."""
        self._enqueue(
            "agent",
            {"agent_id": agent_id, "name": name, "status": status, "started_at": _now_iso()},
        )

    def send_agent_removed(self, agent_id: str) -> None:
        self._enqueue("agent", {"agent_id": agent_id, "action": "removed"})

    def send_warning(self, message: str, level: str = "warning") -> None:
        self._enqueue("warning", {"message": message, "level": level})

    def on_command(self, callback) -> None:
        """
        Registriert eine Funktion, die aufgerufen wird, wenn ein
        Befehl vom Hologramm eintrifft (Geste oder Sprachbefehl, von
        Neural Hologram OS bereits interpretiert). callback erhaelt
        ein dict mit mindestens 'command_type' und optional 'target'.

        Beispiel (siehe main.py RencoraLive.__init__):
            hologram_bridge.on_command(lambda cmd: rencora._on_text_command(
                _hologram_command_to_text(cmd)
            ))
        """
        self._on_command_callback = callback


    def _enqueue(self, channel: str, payload: dict) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "ts": _now_iso(),
            "source": "rencora",
            "type": "event",
            "channel": channel,
            "payload": payload,
        }
        try:
            self._queue.put_nowait(event)
        except queue.Full:


            logger.debug("HologramBridge-Queue voll, Event verworfen.")

    def _run_loop(self) -> None:
        asyncio.run(self._async_main())

    async def _async_main(self) -> None:


        try:
            import websockets
        except ImportError:
            logger.info(
                "Paket 'websockets' nicht installiert - Hologramm-Bruecke deaktiviert "
                "(optional, siehe requirements.txt: websockets>=16.0)."
            )
            return

        while not self._stop_requested.is_set():
            try:
                async with websockets.connect(self._ws_url, open_timeout=2) as ws:
                    self._connected = True
                    await asyncio.gather(
                        self._drain_queue(ws),
                        self._receive_loop(ws),
                    )
            except Exception:
                self._connected = False


                await asyncio.sleep(3)

    async def _receive_loop(self, ws) -> None:
        """Empfaengt eingehende Nachrichten (Gesten-/Sprachbefehle) vom Hologramm."""
        async for raw_message in ws:
            if self._stop_requested.is_set():
                return
            try:
                event = json.loads(raw_message)
            except (json.JSONDecodeError, TypeError):
                continue

            channel = event.get("channel")
            payload = event.get("payload", {})

            if channel == "voice" and payload.get("voice_event") == "command_recognized":
                self._dispatch_command(payload)
            elif channel == "gesture" and payload.get("gesture_event") == "gesture_changed":
                self._dispatch_command(
                    {"command_type": "gesture", "gesture": payload.get("gesture"), "target": None}
                )

    def _dispatch_command(self, payload: dict) -> None:
        if self._on_command_callback is None:
            return
        try:
            self._on_command_callback(payload)
        except Exception:
            logger.exception("Fehler im on_command-Callback.")

    async def _drain_queue(self, ws) -> None:
        loop = asyncio.get_event_loop()
        while not self._stop_requested.is_set():
            try:
                event = await loop.run_in_executor(None, self._queue.get, True, 1.0)
            except queue.Empty:
                continue
            try:
                await ws.send(json.dumps(event))
            except Exception:


                self._enqueue_raw_back(event)
                raise

    def _enqueue_raw_back(self, event: dict) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


hologram_bridge = HologramBridge()
