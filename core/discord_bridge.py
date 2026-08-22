"""
core/discord_bridge.py — Anbindung des externen discord_action-Moduls an den
RENCORA-Kern (die laufende Gemini-Live-Session in main.py).

Folgt demselben Muster wie core/hologram_bridge.py und die
Dashboard-Phone-Relay-Anbindung (dashboard/server.py + main.py):

  Eingehend  (discord_action -> RENCORA):
    POST /inbound  {"speaker": "...", "text": "...", "is_owner": bool}
    Der Text wird — mit Sprecher-Praefix, damit RENCORA weiss, WER im
    Discord-Call/-Chat gerade spricht — ganz normal als Text-Turn in die
    laufende Session eingespeist (gleicher Pfad wie _on_text_command).
    Die eigentliche Consent-Pruefung (darf dieser Discord-Nutzer ueberhaupt
    transkribiert/weitergeleitet werden) passiert VOR diesem Aufruf im
    discord_action-Modul selbst (permissions/consent.py) — der Kern hier
    vertraut darauf und nimmt keine eigene Consent-Logik vor.

  Ausgehend (RENCORA -> discord_action):
    WS /events
      - Text-Frames: {"type": "assistant_text", "text": "..."} bei jedem
        abgeschlossenen Antwort-Turn (siehe main.py _receive_audio).
      - Binaer-Frames: rohe TTS-Audio-Chunks (24kHz, mono, 16-bit PCM), so
        wie sie auch an die lokalen Lautsprecher gehen. discord_action
        resampled diese auf 48kHz/Stereo und spielt sie live in den
        Voice-Channel.

Laeuft nur auf 127.0.0.1 (kein Remote-Zugriff) auf einem eigenen Port,
getrennt vom Dashboard, damit das Discord-Modul unabhaengig von dessen
SSL/Tunnel-Konfiguration angebunden werden kann. Ist optional — laeuft
discord_action nicht, hat dieses Modul keine sichtbare Auswirkung.
"""
import asyncio
import json

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import JSONResponse
    import uvicorn
    _DEPS_OK = True
except ImportError:
    pass

DISCORD_BRIDGE_PORT = 8765


class DiscordBridge:
    def __init__(self, basi):
        """basi: die laufende BasiLive-Instanz aus main.py (fuer Session-Zugriff)."""
        self.basi = basi
        self._ws_clients: set = set()

        if not _DEPS_OK:
            self._app = None
            return

        app = FastAPI()

        @app.get("/health")
        async def health():
            return JSONResponse({"status": "ok", "session_active": self.basi.session is not None})

        @app.post("/inbound")
        async def inbound(request: Request):
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse({"error": "invalid json"}, status_code=400)

            speaker  = str(payload.get("speaker", "Unbekannt"))[:80]
            text     = str(payload.get("text", "")).strip()
            is_owner = bool(payload.get("is_owner", False))

            if not text:
                return JSONResponse({"error": "empty text"}, status_code=400)
            if not self.basi.session:
                return JSONResponse({"error": "RENCORA session not active"}, status_code=503)

            tag = "Owner" if is_owner else "Gast"
            attributed = f"[Discord-Call – {speaker} ({tag})]: {text}"
            self.basi._on_text_command(attributed)
            return JSONResponse({"status": "queued"})

        @app.websocket("/events")
        async def events(ws: WebSocket):
            await ws.accept()
            self._ws_clients.add(ws)
            try:
                while True:


                    await ws.receive_text()
            except WebSocketDisconnect:
                pass
            except Exception:
                pass
            finally:
                self._ws_clients.discard(ws)

        self._app = app
        self._server: "uvicorn.Server | None" = None

    async def broadcast_text(self, text: str) -> None:
        if not self._ws_clients:
            return
        payload = json.dumps({"type": "assistant_text", "text": text})
        dead = []
        for ws in list(self._ws_clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    async def broadcast_audio(self, pcm_bytes: bytes) -> None:
        if not self._ws_clients:
            return
        dead = []
        for ws in list(self._ws_clients):
            try:
                await ws.send_bytes(pcm_bytes)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    async def serve(self) -> None:
        if not _DEPS_OK or self._app is None:
            print("[DiscordBridge] Disabled: fastapi/uvicorn not installed.")
            return
        config = uvicorn.Config(
            self._app, host="127.0.0.1", port=DISCORD_BRIDGE_PORT,
            log_level="warning", loop="asyncio",
        )
        self._server = uvicorn.Server(config)
        print(f"[DiscordBridge] listening on 127.0.0.1:{DISCORD_BRIDGE_PORT}")
        await self._server.serve()
