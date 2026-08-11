import asyncio
from core.secrets import get_gemini_key
import re
import threading
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path


if sys.platform == "win32":
    import subprocess as _sp

    _orig_popen_init = _sp.Popen.__init__

    def _no_window_popen_init(self, *p_args, **p_kwargs):
        flags = p_kwargs.get("creationflags", 0)
        if not (flags & _sp.CREATE_NEW_CONSOLE):
            p_kwargs["creationflags"] = flags | _sp.CREATE_NO_WINDOW
        _orig_popen_init(self, *p_args, **p_kwargs)

    _sp.Popen.__init__ = _no_window_popen_init


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--guard-check":
    from core.guard_selftest import run as _guard_selftest_run

    raise SystemExit(_guard_selftest_run(sys.argv[2:]))


if sys.stdout is None or sys.stderr is None:
    import io

    class _NullStream(io.TextIOBase):
        def write(self, s):  # noqa: D102
            return len(s)
        def flush(self):  # noqa: D102
            pass
        def isatty(self):  # noqa: D102
            return False

    if sys.stdout is None:
        sys.stdout = _NullStream()
    if sys.stderr is None:
        sys.stderr = _NullStream()

from core.logging_config import setup_logging, get_logger
setup_logging()
log = get_logger(__name__)

from core import policy

from database.db import init_db
init_db()

import sounddevice as sd
from google import genai
from google.genai import types
from ui import BasiUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    load_people, format_people_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.whatsapp_import   import import_whatsapp_chat, recall_person_chat


try:
    from actions.calendar_mail import calendar_mail
except Exception:
    calendar_mail = None

from actions.task_planner  import agent_task
from actions.system_monitor import SystemMonitor, get_system_status
from actions.second_brain  import second_brain_save, second_brain_recall


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    return get_gemini_key()


def _ensure_config() -> None:
    if API_CONFIG_PATH.exists():
        return
    template = BASE_DIR / "config_example" / "api_keys.json"
    try:
        API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if template.exists():
            API_CONFIG_PATH.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass


_ensure_config()


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are RENCORA AI, the personal assistant of Renker Industries. "
            "Be concise, direct, honest, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


def _load_lore() -> str:
    try:
        return (BASE_DIR / "core" / "lore.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return ""

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

from tools.declarations import TOOL_DECLARATIONS


class BasiLive:

    def __init__(self, ui: BasiUI):
        self.ui             = ui
        self.confirm_action = getattr(ui, "confirm_action", None)
        from agents.router import AgentRouter
        self.agent_router    = AgentRouter(self)
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._phone_active  = False
        self.ui.on_text_command  = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui.on_get_tunnel_status = self._get_tunnel_status
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._discord_bridge = None


        try:
            from core.hologram_bridge import hologram_bridge
            hologram_bridge.on_command(self._on_hologram_command)
        except Exception:
            pass


        from core.proactive_engine import ProactiveEngine

        def _hologram_notify(message: str, channel: str) -> None:
            try:
                from core.hologram_bridge import hologram_bridge as hb
                hb.send_notification(message, level="info")
            except Exception:
                pass

        self._proactive_engine = ProactiveEngine(
            speak_fn=self.speak,
            is_busy_fn=lambda: self._is_speaking or self.ui.muted,
            hologram_notify_fn=_hologram_notify,
        )


        self._sys_monitor = SystemMonitor()

    async def _run_system_monitor(self) -> None:
        """Hintergrund-Task: Sprachwarnung bei ueberschrittenen Systemwerten (RAM/Temp/GPU)."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if alert and self.session:
                try:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": alert}]},
                        turn_complete=True,
                    )
                except Exception as e:
                    print(f"[Monitor]  Could not send alert: {e}")

    def _on_hologram_command(self, command: dict) -> None:
        """
        Wird aufgerufen, wenn ein Gesten- oder Sprachbefehl im Neural
        Hologram OS erkannt wurde (siehe CommandRouter.broadcast() in
        Neural Hologram OS). Nutzt bevorzugt raw_text (die tatsaechlich
        gesprochenen Worte), damit RENCORA denselben natuerlichsprachigen
        Kontext bekommt wie bei einer normalen Spracheingabe.
        """
        text = command.get("raw_text")
        if not text:
            gesture = command.get("gesture")
            if gesture:
                text = f"[Geste erkannt: {gesture}]"
            else:
                return
        self._on_text_command(text)

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None:
            self.ui.write_log(
                "SYS: Dashboard unavailable. "
                "Run: pip install fastapi \"uvicorn[standard]\" cryptography"
            )
            return None
        key    = self._dashboard.new_key()
        url    = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        tunnel_url = self._tunnel.url if self._tunnel else None
        auto_login = f"{url}/auto-login?key={key}"
        tunnel_auto_login = f"{tunnel_url}/auto-login?key={key}" if tunnel_url else ""
        return url, key, auto_login, manual, tunnel_url, tunnel_auto_login

    def _get_tunnel_status(self):
        """Called (repeatedly, e.g. every second) from the Remote-Access overlay
        so it can switch from 'starting…' to the real QR once cloudflared is ready."""
        if not self._tunnel:
            return "disabled", None, ""
        key = getattr(self._dashboard, "_last_key", None) if self._dashboard else None
        url = self._tunnel.url
        auto = f"{url}/auto-login?key={key}" if (url and key) else ""
        return self._tunnel.status, url, auto

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"{tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        people_str = format_people_for_prompt(load_people())
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        lore_str = _load_lore()

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        if people_str:
            parts.append(people_str)
        if lore_str:
            parts.append(lore_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[RENCORA]  {name}  {args}")
        self.ui.set_state("THINKING")


        try:
            from core.hologram_bridge import hologram_bridge
            hologram_bridge.send_agent_event(agent_id=name, name=name, status="running")
        except Exception:
            pass

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory]  save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        try:
            result = await self.agent_router.dispatch(name, args)
        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

            try:
                from core.hologram_bridge import hologram_bridge
                hologram_bridge.send_warning(f"Tool '{name}' failed: {e}", level="error")
            except Exception:
                pass

        if not self.ui.muted:
            self.ui.set_state("LISTENING")


        try:
            from core.hologram_bridge import hologram_bridge
            hologram_bridge.send_agent_removed(agent_id=name)
        except Exception:
            pass

        print(f"[RENCORA]  {name} → {str(result)[:80]}")
        result = policy.wrap_external(name, result)
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[RENCORA]  Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                basi_speaking = self._is_speaking
            if not basi_speaking and not self.ui.muted and not self._phone_active:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[RENCORA]  Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[RENCORA]  Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[RENCORA]  Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)


                        if self._discord_bridge:
                            asyncio.create_task(
                                self._discord_bridge.broadcast_audio(response.data)
                            )

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"RENCORA: {full_out}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "rencora",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                                if self._discord_bridge:
                                    asyncio.create_task(
                                        self._discord_bridge.broadcast_text(full_out)
                                    )
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[RENCORA]  {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[RENCORA]  Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[RENCORA]  Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[RENCORA]  Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:

                self._phone_active = False
                continue
            self._phone_active = True
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()


    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                text = await asyncio.wait_for(
                    self._dashboard._command_queue.get(), timeout=0.5
                )
                if not text:
                    continue

                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": text}]},
                        turn_complete=True,
                    )
                    self.ui.write_log(f"[Web]: {text}")
                else:
                    print(f"[Dashboard] Dropped command (no session): {text}")
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)


    async def run(self):
        self._loop = asyncio.get_event_loop()

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )


        try:
            from dashboard.server import DashboardServer
            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)

            async def _dashboard_supervised():
                """Frueher: create_task(serve()) - stuerzte serve() ab, verschwand
                der Fehler lautlos (Task nie ausgewertet, print in fensterloser
                exe unsichtbar). Jetzt: Fehler landen in dashboard_error.log
                neben der exe UND im Activity Log der Oberflaeche."""
                try:
                    await self._dashboard.serve()
                except Exception:
                    err = traceback.format_exc()
                    try:
                        with open(BASE_DIR / "dashboard_error.log", "a", encoding="utf-8") as f:
                            f.write(err + "\n")
                    except Exception:
                        pass
                    try:
                        self.ui.write_log("SYS: Dashboard-Server abgestuerzt - Details in dashboard_error.log")
                    except Exception:
                        pass

            asyncio.create_task(_dashboard_supervised())

            asyncio.create_task(self._process_dashboard_commands())


            try:
                from actions.screen_processor import register_broadcast
                register_broadcast(self._dashboard.broadcast)
            except Exception as e:
                print(f"[Dashboard] Vision-Broadcast nicht verdrahtet: {e}")
        except Exception as e:
            print(f"[Dashboard] Disabled: {e}")
            try:
                with open(BASE_DIR / "dashboard_error.log", "a", encoding="utf-8") as f:
                    f.write(f"Dashboard konnte nicht erstellt werden: {e}\n{traceback.format_exc()}\n")
            except Exception:
                pass
            self._dashboard = None


        try:
            from core.discord_bridge import DiscordBridge
            self._discord_bridge = DiscordBridge(self)
            asyncio.create_task(self._discord_bridge.serve())
        except Exception as e:
            print(f"[DiscordBridge] Disabled: {e}")
            self._discord_bridge = None


        self._tunnel = None
        if self._dashboard is not None:
            try:
                from core.tunnel import CloudflareTunnel
                from dashboard.server import PORT as _DASH_PORT
                self._tunnel = CloudflareTunnel(
                    local_port=_DASH_PORT,
                    use_ssl=self._dashboard._ssl_enabled(),
                )
                asyncio.create_task(self._tunnel.run_forever())
            except Exception as e:
                print(f"[Tunnel] Disabled: {e}")
                self._tunnel = None

        while True:
            try:
                print("[RENCORA] Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    print("[RENCORA] Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: RENCORA online.")

                    if self._dashboard:
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    if self._dashboard:
                        tg.create_task(self._relay_phone_audio())
                    tg.create_task(self._proactive_engine.run_forever())
                    tg.create_task(self._run_system_monitor())

            except Exception as e:
                print(f"[RENCORA] Error: {e}")
                traceback.print_exc()
            finally:
                self.session = None

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            print("[RENCORA] Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    ui = BasiUI(str(BASE_DIR / "face.png"))


    try:
        from core.hologram_bridge import hologram_bridge
        hologram_bridge.start()
    except Exception:
        pass


    try:
        from actions.notification_watcher import notification_watcher
        notification_watcher.start()
    except Exception:
        pass

    def runner():
        ui.wait_for_api_key()
        basi = BasiLive(ui)
        try:
            asyncio.run(basi.run())
        except KeyboardInterrupt:
            print("\n Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":


    try:
        main()
    except Exception:
        import traceback as _tb

        _txt = _tb.format_exc()
        try:
            (BASE_DIR / "startup_crash.log").write_text(_txt, encoding="utf-8")
        except Exception:
            pass
        print(_txt, file=sys.stderr)
        raise