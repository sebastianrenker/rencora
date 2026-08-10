"""
agents/qa_agent.py — QAAgent, generalisiert aus
actions/dev_agent.py::_classify_error/_parse_traceback/_is_rate_limit/
_has_error (Teil 5 "QA Agent" + Teil 8 "Fehlererkennung/Selbstkorrektur" +
Teil 13 Refactoring-Plan #7).

Der eigentliche Fix-Loop (_fix_files/_run_project/_build_project in
dev_agent.py, der LLM-Aufrufe macht um Dateien zu reparieren) ist
Coding-Projekt-spezifisch und bleibt bewusst in dev_agent.py - das hier
extrahierte Stueck ist der generische, wiederverwendbare Teil: "welche Art
von Fehler liegt vor". Das war laut Architektur-Review bereits ein gutes,
wiederverwendbares Muster, nur hart an Python-Tracebacks/Coding-Projekte
gebunden. QAAgent.diagnose() ist bewusst nicht auf Python-Syntax
beschraenkt, sondern erkennt generische Fehlerkategorien (dependency,
syntax, import, runtime) unabhaengig von der aufrufenden Aktion - z.B.
auch fuer einen fehlgeschlagenen browser_control- oder web_search-Schritt
im PlanningEngine-Kontext (Teil 8) nutzbar, nicht nur fuer dev_agent.py.

dev_agent.py bleibt fast unveraendert und ruft diese Funktionen weiterhin
unter ihren alten Namen auf (_classify_error = QAAgent().diagnose, etc.) -
kein Verhaltenswechsel, nur Herkunft der Logik.
"""

from __future__ import annotations

import re
from pathlib import Path


class QAAgent:
    """diagnose() ist die generalisierte Form von dev_agent.py::_classify_error
    (nicht mehr auf Python-Tracebacks beschraenkt, siehe Modul-Docstring)."""

    @staticmethod
    def is_rate_limit(error: Exception) -> bool:
        msg = str(error).lower()
        return "429" in msg or "quota" in msg or "resource_exhausted" in msg

    @staticmethod
    def parse_traceback(output: str, project_files: list[str]) -> tuple[str | None, int | None]:
        pattern = re.compile(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', re.IGNORECASE)
        matches = pattern.findall(output)

        for raw_path, line_str in reversed(matches):
            raw_name = Path(raw_path).name
            for pf in project_files:
                if Path(pf).name == raw_name or pf == raw_path or raw_path.endswith(pf):
                    return pf, int(line_str)

        return None, None

    @staticmethod
    def diagnose(output: str) -> str:
        """Generalisierte Fehlerklassifikation (ehem. _classify_error).
        Rein textbasiertes Pattern-Matching, unabhaengig davon, ob output
        aus einem Python-Traceback, einer fehlgeschlagenen Tool-Ausgabe
        oder einem anderen Aktions-Fehler stammt."""
        low = output.lower()

        if any(x in low for x in ("no module named", "modulenotfounderror", "importerror")):
            return "dependency_error"

        if "syntaxerror" in low or "invalid syntax" in low:
            return "syntax_error"

        if "cannot import" in low or "importerror" in low:
            return "import_error"

        if any(x in low for x in (
            "traceback", "exception", "error:", "nameerror", "typeerror",
            "attributeerror", "valueerror", "keyerror", "indexerror",
            "zerodivisionerror", "filenotfounderror", "permissionerror",
        )):
            return "runtime_error"

        return "none"

    def has_error(self, output: str, run_command: str) -> bool:
        low = output.lower()

        if "timed out" in low:
            return False
        if not output.strip():
            return False

        return self.diagnose(output) != "none"
