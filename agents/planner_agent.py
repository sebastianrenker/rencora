"""
agents/planner_agent.py — PlannerAgent, generalisiert aus
actions/task_planner.py::_plan() (Teil 5 + Teil 13 Refactoring-Plan #6).

Bisher war die Tool-Allowlist fuer den Mehrschritt-Planer hart auf 5-6
Alltags-Tools begrenzt (_allowed_tools() in task_planner.py). Dieses Modul
verallgemeinert das:
  - PlannerAgent.plan(goal, tool_hints) -> list[Step]  bleibt vom Vertrag
    her identisch zur alten _plan()-Funktion (gleicher Prompt, gleiches
    JSON-Schema), ist aber kein task_planner.py-internes Detail mehr,
    sondern fuer beliebige Aufrufer wiederverwendbar.
  - build_tool_registry() ersetzt _allowed_tools() und stellt einen
    deutlich groesseren, aber weiterhin bewusst kuratierten Tool-Katalog
    bereit (siehe EXCLUDED_FROM_AUTONOMOUS_PLANNING unten fuer die
    Begruendung, welche Tools *nicht* autonom verkettet werden).

task_planner.py::agent_task() bleibt der duenne Aufrufer: baut die
Registry, ruft PlannerAgent().plan(...), fuehrt die Schritte dann genau
wie zuvor sequenziell aus (keine Verhaltensaenderung am Executor-Teil).
"""

from __future__ import annotations
from core.secrets import get_gemini_key

import json
import re
from typing import Callable

MAX_STEPS = 6
MODEL_PLANNER = "gemini-2.5-flash"


EXCLUDED_FROM_AUTONOMOUS_PLANNING = {
    "agent_task", "dev_agent", "shutdown_rencora", "computer_control",
    "desktop_control", "code_helper", "game_updater", "screen_process",
    "file_controller", "file_processor", "import_whatsapp_chat",
    "second_brain_save",
}


def _get_model():
    import json as _json
    import sys as _sys
    from pathlib import Path as _Path
    from google import genai

    def _base_dir() -> _Path:
        if getattr(_sys, "frozen", False):
            return _Path(_sys.executable).parent
        return _Path(__file__).resolve().parent.parent

    cfg_path = _base_dir() / "config" / "api_keys.json"
    api_key = get_gemini_key()
    client = genai.Client(api_key=api_key)

    class _Wrapper:
        def generate_content(self, contents):
            return client.models.generate_content(model=MODEL_PLANNER, contents=contents)

    return _Wrapper()


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def build_tool_registry() -> dict:
    """Ersetzt task_planner.py::_allowed_tools(). Liefert {tool_name:
    (callable, hint_str)} - deutlich breiter als zuvor (siehe Modul-
    Docstring), aber weiterhin ohne die in EXCLUDED_FROM_AUTONOMOUS_PLANNING
    gelisteten Tools."""
    from actions.web_search import web_search as web_search_action
    from actions.send_message import send_message
    from actions.weather_report import weather_action
    from actions.reminder import reminder
    from actions.flight_finder import flight_finder
    from actions.open_app import open_app
    from actions.browser_control import browser_control
    from actions.computer_settings import computer_settings
    from actions.youtube_video import youtube_video
    from actions.system_monitor import get_system_status
    from actions.second_brain import second_brain_recall
    try:
        from actions.calendar_mail import calendar_mail
    except Exception:
        calendar_mail = None

    tools = {
        "web_search": (
            web_search_action,
            "params: query (str), mode ('search'|'compare'), items (list), aspect (str)",
        ),
        "send_message": (
            send_message,
            "params: receiver (str), message_text (str), platform (str, e.g. WhatsApp)",
        ),
        "weather_report": (weather_action, "params: city (str)"),
        "reminder": (
            reminder,
            "params: date (YYYY-MM-DD), time (HH:MM), message (str)",
        ),
        "flight_finder": (
            flight_finder,
            "params: origin, destination, date, return_date, passengers, cabin",
        ),
        "open_app": (open_app, "params: app_name (str)"),
        "browser_control": (
            browser_control,
            "params: action ('open'|'navigate'|'search'|...), url_or_query (str)",
        ),
        "computer_settings": (
            computer_settings,
            "params: setting (e.g. 'volume'|'brightness'), value (str/number)",
        ),
        "youtube_video": (
            youtube_video,
            "params: action ('play'|'summarize'|'trends'), query (str)",
        ),
        "second_brain_recall": (
            second_brain_recall,
            "params: query (str) — durchsucht bereits gespeichertes Second-Brain-Wissen",
        ),
    }


    tools["system_status"] = (
        lambda parameters=None, player=None: (
            lambda s: (
                f"CPU {s['cpu_percent']}% | RAM {s['ram_percent']}% | "
                f"Temp {s['cpu_temp_c']}°C | Uptime {s['uptime']}"
            )
        )(get_system_status()),
        "params: keine - liefert aktuellen Systemstatus",
    )

    if calendar_mail:
        tools["calendar_mail"] = (
            calendar_mail,
            "params: action ('agenda_today'|'agenda_range'|'create_event'|"
            "'move_event'|'cancel_event'|'list_unread_mail'|'search_mail'), "
            "title, date, time, duration_min, days_ahead, event_id, max_results",
        )
    return tools


class PlannerAgent:
    """Verallgemeinerung von task_planner.py::_plan(). Zerlegt ein
    Freitext-Ziel in eine Liste von Tool-Schritten, basierend auf einem
    beliebig grossen tool_hints-Katalog (siehe build_tool_registry())."""

    def __init__(self, max_steps: int = MAX_STEPS):
        self.max_steps = max_steps

    def plan(self, goal: str, tool_hints: dict) -> list[dict]:
        model = _get_model()
        tool_list = "\n".join(f"- {name}: {hint}" for name, (_, hint) in tool_hints.items())

        prompt = f"""You are a task planner for a personal assistant. Break the user's goal into
the minimum sequence of tool calls needed, using ONLY the tools listed below.

Available tools:
{tool_list}

Goal: {goal}

Rules:
1. Use the FEWEST steps possible. If one tool call fully achieves the goal, return one step.
2. Only use tools from the list above — never invent a tool name.
3. Each step's "params" must match that tool's documented params exactly.
4. If a later step needs information from an earlier step's result (e.g. a
   restaurant name found via web_search before messaging someone about it),
   set "needs_previous_result": true on that step instead of guessing the value.
5. Maximum {self.max_steps} steps.

Return ONLY valid JSON, no markdown:
{{
  "steps": [
    {{"tool": "tool_name", "params": {{...}}, "needs_previous_result": false, "reason": "short reason"}}
  ]
}}

JSON:"""

        response = model.generate_content(prompt)
        raw = _strip_fences(response.text)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Planner returned invalid JSON: {e}\nRaw: {raw[:300]}")

        steps = data.get("steps", [])
        return steps[: self.max_steps]
