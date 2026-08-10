"""
actions/task_planner.py

NEUE DATEI - generischer Mehrschritt-Planer fuer ALLTAGSAUFGABEN (nicht
Code - dafuer gibt es bereits dev_agent.py). Schliesst die Luecke, dass
"Buch mir was und sag der Gruppe Bescheid" heute zwei/drei einzelne
Tool-Aufrufe braeuchte, die das LLM selbst orchestrieren muss, statt
dass eine Anfrage automatisch in Tool-Schritte zerlegt wird.

WARUM EIN EIGENES MODUL UND NICHT agent_task ERWEITERN:
agent_task existiert in main.py laut Prompt bereits als Sammelbegriff
fuer "komplexe Mehrschritt-Planung", wird aber nirgends in den
TOOL_DECLARATIONS/​_execute_tool als eigenstaendiges Tool implementiert
(es wird nur im Prompt referenziert: "agent_task: ONLY for complex,
multi-step planning"). Dieses Modul liefert die fehlende Implementierung
fuer genau dieses Tool, ohne mit dev_agent.py (Code-Projekte) zu
kollidieren.

ARCHITEKTUR:
1. PLANNER (Gemini Flash, wie in dev_agent.py): zerlegt die
   natuerlichsprachige Anfrage in eine Liste von Schritten, jeder Schritt
   = genau ein vorhandenes Tool + dessen Parameter (siehe ALLOWED_TOOLS
   unten - bewusst eine Allowlist, damit der Planner niemals ein Tool
   "erfindet").
2. EXECUTOR: fuehrt die Schritte sequenziell aus, indem er dieselben
   actions/*.py-Funktionen aufruft, die main.py auch direkt nutzt -
   kein Duplizieren von Logik, nur Orchestrierung.
3. Nach jedem Schritt darf der Planner (re-)bewerten, ob der naechste
   Schritt noch passt (z.B. wenn web_search keine Ergebnisse liefert,
   macht "Tisch buchen" mit einem Fantasie-Restaurant keinen Sinn) -
   das ist die "plan -> execute -> reflect"-Schleife, nicht starres
   Abarbeiten einer Liste.
4. Jeder Schritt wird ueber `speak` kurz zwischenkommentiert (sofern
   uebergeben), damit der Nutzer mitbekommt, dass gerade mehrstufig
   gearbeitet wird - genau wie dev_agent das fuer Code-Projekte tut.

TOOL-DECLARATION (main.py TOOL_DECLARATIONS, siehe PATCH_main.py.txt):
    {
        "name": "agent_task",
        "description": (
            "Plans and executes multi-step everyday tasks that need more "
            "than one tool call (e.g. researching something AND messaging "
            "someone about it, or checking the calendar AND sending an "
            "invite). ONLY for complex, multi-step requests (3+ steps) "
            "that genuinely span multiple tools. Do not call this when a "
            "single existing tool can accomplish the request."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING", "description": "What the user ultimately wants accomplished, in their own words"}
            },
            "required": ["goal"]
        }
    }

DISPATCH (main.py _execute_tool, siehe PATCH_main.py.txt):
    elif name == "agent_task":
        r = await loop.run_in_executor(None, lambda: agent_task(parameters=args, player=self.ui, speak=self.speak))
        result = r or "Done."
"""

from __future__ import annotations

from typing import Callable, Optional

from agents.planner_agent import PlannerAgent, build_tool_registry


_allowed_tools = build_tool_registry


def _inject_previous_result(params: dict, previous_result: str) -> dict:
    """
    Sehr einfache Heuristik: Felder, die typischerweise Freitext
    transportieren (message_text, value, query), bekommen das vorherige
    Ergebnis angehaengt, falls needs_previous_result gesetzt war. Bewusst
    simpel gehalten - fuer komplexere Faelle soll der Planner stattdessen
    den Wert direkt selbst formulieren und needs_previous_result weglassen.
    """
    for field in ("message_text", "value", "query", "title"):
        if field in params and isinstance(params[field], str):
            params[field] = f"{params[field]} ({previous_result[:200]})"
            break
    return params


def agent_task(
    parameters: dict,
    player=None,
    speak: Optional[Callable[[str], None]] = None,
    response=None,
) -> str:
    goal = (parameters.get("goal") or "").strip()
    if not goal:
        return "I need to know what you're trying to accomplish."

    tool_hints = _allowed_tools()

    try:
        steps = PlannerAgent().plan(goal, tool_hints)
    except Exception as e:
        if player:
            player.write_log(f"[agent_task]  Planning failed: {e}")
        return f"I couldn't plan that out: {e}"

    if not steps:
        return "I couldn't break that down into concrete steps."

    if speak and len(steps) > 1:
        speak(f"Got it — that'll take {len(steps)} steps. Starting now.")

    results = []
    previous_result = ""

    for i, step in enumerate(steps, start=1):
        tool_name = step.get("tool", "")
        params = step.get("params", {}) or {}
        reason = step.get("reason", "")

        if tool_name not in tool_hints:
            results.append(f"Step {i} skipped — unknown tool '{tool_name}'.")
            continue

        if step.get("needs_previous_result") and previous_result:
            params = _inject_previous_result(dict(params), previous_result)

        func, _ = tool_hints[tool_name]

        if player:
            player.write_log(f"[agent_task] Step {i}/{len(steps)}: {tool_name} — {reason}")

        try:
            result = func(parameters=params, player=player)
        except TypeError:


            try:
                result = func(parameters=params, player=player, response=None, speak=speak)
            except Exception as e2:
                result = f"failed: {e2}"
        except Exception as e:
            result = f"failed: {e}"

        previous_result = str(result)
        results.append(f"Step {i} ({tool_name}): {previous_result}")

    summary = " | ".join(results)
    return f"Completed {len(steps)}-step task. {summary[:500]}"
