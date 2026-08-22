"""
agents/router.py — AgentRouter, ersetzt den 28-Wege if/elif-Block in
main.py::BasiLive._execute_tool durch ein Dict {tool_name: handler}
(P1 Refactoring-Plan #5, im Architektur-Review als groesster Hebel benannt).

Reine Umstrukturierung: Jeder Handler unten ruft exakt dieselbe
actions/*.py-Funktion mit denselben Parametern auf wie zuvor der jeweilige
elif-Zweig in main.py. Kein Verhaltenswechsel, kein neues Feature.

Vorteil gegenueber dem alten Muster: ein neues Tool braucht nur noch einen
neuen _h_<name>-Handler + einen Dict-Eintrag in _build_handlers() - main.py
selbst muss dafuer nicht mehr angefasst werden (ausser TOOL_DECLARATIONS,
die weiterhin separat in tools/declarations.py liegen, und den import in
dieser Datei).

Die feste Vor-/Nachbereitung pro Tool-Aufruf (Logging, Hologram-Bridge-
Events, Exception-Handling, "save_memory"-Sonderfall mit silent-Response,
FunctionResponse-Bau) bleibt bewusst in main.py::_execute_tool - das ist
Orchestrierungs-Logik, kein Tool-Dispatch, und soll hier nicht dupliziert
werden.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time

from core import policy
from database.db import record_agent_run

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
from actions.task_planner      import agent_task
from actions.system_monitor    import get_system_status
from actions.second_brain       import second_brain_save, second_brain_recall
from actions.app_volume         import app_volume
from actions.gesture_control    import gesture_control
from actions.window_manager     import window_manager
from actions.smart_search       import smart_search
from actions.adaptive_brightness import adaptive_brightness
from actions.task_manager       import task_manager

try:
    from actions.calendar_mail import calendar_mail
except Exception:
    calendar_mail = None


class AgentRouter:
    def __init__(self, basi) -> None:

        self.basi = basi
        self._handlers = self._build_handlers()

    async def _confirm(self, name: str, args: dict, level: int) -> bool:
        fn = getattr(self.basi, "confirm_action", None)
        if fn is None:
            return not policy.confirmation_enforced()
        try:
            if inspect.iscoroutinefunction(fn):
                return bool(await fn(name, args, level))
            return bool(await asyncio.to_thread(fn, name, args, level))
        except Exception:
            return False

    async def dispatch(self, name: str, args: dict) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"Unknown tool: {name}"

        if not policy.tool_allowed(name):
            policy.audit(name, policy.risk_level(name), "blocked_disabled")
            return (f"Tool '{name}' ist in der Konfiguration deaktiviert "
                    "(disabled_tools) und wurde nicht ausgefuehrt.")

        if policy.requires_confirmation(name):
            level = policy.risk_level(name)
            approved = await self._confirm(name, args, level)
            policy.audit(name, level, "approved" if approved else "denied")
            if not approved:
                return (f"Aktion '{name}' ist als risikoreich (Stufe {level}) eingestuft "
                        "und wurde ohne Bestaetigung nicht ausgefuehrt.")

        started = time.time()
        status = "success"
        result = ""
        tmo = policy.timeout(name)
        try:
            if tmo is None:
                result = await handler(args)
            else:
                result = await asyncio.wait_for(handler(args), timeout=tmo)
            return result
        except asyncio.TimeoutError:
            status = "timeout"
            result = (f"Aktion '{name}' hat das Zeitlimit von {int(tmo)}s "
                      "ueberschritten und wurde abgebrochen.")
            return result
        except Exception:
            status = "failed"
            raise
        finally:
            try:
                record_agent_run(
                    agent="AgentRouter", tool_name=name, params=args,
                    result=result, status=status,
                    started_at=started, finished_at=time.time(),
                )
            except Exception:

                pass

    def _build_handlers(self):
        return {
            "open_app":              self._h_open_app,
            "weather_report":        self._h_weather_report,
            "browser_control":       self._h_browser_control,
            "file_controller":       self._h_file_controller,
            "send_message":          self._h_send_message,
            "reminder":              self._h_reminder,
            "youtube_video":         self._h_youtube_video,
            "screen_process":        self._h_screen_process,
            "computer_settings":     self._h_computer_settings,
            "desktop_control":       self._h_desktop_control,
            "code_helper":           self._h_code_helper,
            "dev_agent":             self._h_dev_agent,
            "web_search":            self._h_web_search,
            "file_processor":        self._h_file_processor,
            "import_whatsapp_chat":  self._h_import_whatsapp_chat,
            "recall_person_chat":    self._h_recall_person_chat,
            "computer_control":      self._h_computer_control,
            "game_updater":          self._h_game_updater,
            "flight_finder":         self._h_flight_finder,
            "second_brain_save":     self._h_second_brain_save,
            "second_brain_recall":   self._h_second_brain_recall,
            "system_status":         self._h_system_status,
            "app_volume":            self._h_app_volume,
            "gesture_control":       self._h_gesture_control,
            "window_manager":        self._h_window_manager,
            "smart_search":          self._h_smart_search,
            "adaptive_brightness":   self._h_adaptive_brightness,
            "calendar_mail":         self._h_calendar_mail,
            "agent_task":            self._h_agent_task,
            "task_manager":          self._h_task_manager,
            "shutdown_rencora":      self._h_shutdown_rencora,
        }


    async def _h_open_app(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=ui))
        return r or f"Opened {args.get('app_name')}."

    async def _h_app_volume(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: app_volume(parameters=args, player=ui))
        return r or "Lautstaerke angepasst."

    async def _h_gesture_control(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: gesture_control(parameters=args, player=ui))
        return r or "Gestensteuerung umgeschaltet."

    async def _h_window_manager(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: window_manager(parameters=args, player=ui))
        return r or "Fenster-Aktion ausgefuehrt."

    async def _h_smart_search(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: smart_search(parameters=args, player=ui))
        return r or "Suche abgeschlossen."

    async def _h_adaptive_brightness(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: adaptive_brightness(parameters=args, player=ui))
        return r or "Helligkeit umgeschaltet."

    async def _h_weather_report(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=ui))
        return r or "Weather delivered."

    async def _h_browser_control(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=ui))
        return r or "Done."

    async def _h_file_controller(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=ui))
        return r or "Done."

    async def _h_send_message(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None,
            lambda: send_message(parameters=args, response=None, player=ui, session_memory=None)
        )
        return r or f"Message sent to {args.get('receiver')}."

    async def _h_reminder(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=ui))
        return r or "Reminder set."

    async def _h_youtube_video(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=ui))
        return r or "Done."

    async def _h_screen_process(self, args):
        ui = self.basi.ui
        threading.Thread(
            target=screen_process,
            kwargs={"parameters": args, "response": None, "player": ui, "session_memory": None},
            daemon=True,
        ).start()
        return "Vision module activated. Stay completely silent — vision module will speak directly."

    async def _h_computer_settings(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=ui))
        return r or "Done."

    async def _h_desktop_control(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=ui))
        return r or "Done."

    async def _h_code_helper(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=ui, speak=speak))
        return r or "Done."

    async def _h_dev_agent(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=ui, speak=speak))
        return r or "Done."

    async def _h_web_search(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=ui))
        return r or "Done."

    async def _h_file_processor(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        if not args.get("file_path") and ui.current_file:
            args["file_path"] = ui.current_file
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None, lambda: file_processor(parameters=args, player=ui, speak=speak)
        )
        return r or "Done."

    async def _h_import_whatsapp_chat(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        if not args.get("file_path") and ui.current_file:
            args["file_path"] = ui.current_file
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None, lambda: import_whatsapp_chat(parameters=args, player=ui, speak=speak)
        )
        return r or "Done."

    async def _h_recall_person_chat(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None, lambda: recall_person_chat(parameters=args, player=ui, speak=speak)
        )
        return r or "Done."

    async def _h_computer_control(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=ui))
        return r or "Done."

    async def _h_game_updater(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=ui, speak=speak))
        return r or "Done."

    async def _h_flight_finder(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=ui))
        return r or "Done."

    async def _h_second_brain_save(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: second_brain_save(args, player=ui))

    async def _h_second_brain_recall(self, args):
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: second_brain_recall(args, player=ui))

    async def _h_system_status(self, args):
        status = await asyncio.to_thread(get_system_status)
        return (
            f"CPU {status['cpu_percent']}% | RAM {status['ram_percent']}% "
            f"({status['ram_used_gb']}/{status['ram_total_gb']} GB) | "
            f"Temp {status['cpu_temp_c']}°C | GPU {status['gpu_percent']}% | "
            f"Uptime {status['uptime']} | {status['process_count']} Prozesse"
        )

    async def _h_calendar_mail(self, args):
        if calendar_mail is None:
            return "Calendar/mail isn't set up yet — install google-auth-oauthlib and google-api-python-client first."
        ui = self.basi.ui
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: calendar_mail(parameters=args, player=ui))
        return r or "Done."

    async def _h_task_manager(self, args):
        return await asyncio.to_thread(task_manager, parameters=args, player=self.basi.ui)

    async def _h_agent_task(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: agent_task(parameters=args, player=ui, speak=speak))
        return r or "Done."

    async def _h_shutdown_rencora(self, args):
        ui, speak = self.basi.ui, self.basi.speak
        ui.write_log("SYS: Shutdown requested.")
        speak("Goodbye.")

        def _shutdown():
            import time, os
            time.sleep(1)
            os._exit(0)

        threading.Thread(target=_shutdown, daemon=True).start()


        return "Done."
