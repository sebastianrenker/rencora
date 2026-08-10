"""
actions/smart_search.py — Tiefe, inhaltsbasierte Dateisuche (Wunsch 2.1).

"Such die Datei, in der es um die Steuererklaerung 2024 geht"
"Finde meine Notizen zum BASI-Projekt"

Durchsucht Dokumente/Desktop/Downloads rekursiv - nicht nur Dateinamen,
sondern auch den INHALT von Text-Dateien (txt, md, py, json, csv, log,
docx). Bewertet Treffer nach: Dateiname-Treffer > Inhalts-Treffer,
mehrere Suchwoerter > eines, neuere Dateien > aeltere.

Sicherheits-Limits: max. 4000 Dateien, max. 2 MB pro Datei, max. 20
Sekunden - damit die Suche nie das System einfriert.
"""
from __future__ import annotations

import time
from pathlib import Path

_TEXT_EXT = {".txt", ".md", ".py", ".json", ".csv", ".log", ".ini", ".bat", ".ps1", ".html", ".js"}
_MAX_FILES = 4000
_MAX_BYTES = 2 * 1024 * 1024
_MAX_SECONDS = 20.0
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv",
              "AppData", "site-packages", "dist", "build"}


def _default_roots() -> list[Path]:
    home = Path.home()
    roots = []
    for name in ("Documents", "Dokumente", "Desktop", "Downloads"):
        p = home / name
        if p.is_dir():
            roots.append(p)
    return roots or [home]


def _read_text(path: Path) -> str:
    try:
        if path.suffix.lower() == ".docx":
            try:
                import docx
                d = docx.Document(str(path))
                return "\n".join(p.text for p in d.paragraphs)
            except Exception:
                return ""
        if path.stat().st_size > _MAX_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _score(path: Path, words: list[str], now: float) -> tuple[float, str]:
    """Liefert (Score, Trefferart). 0 = kein Treffer."""
    name = path.name.lower()
    name_hits = sum(1 for w in words if w in name)
    content_hits = 0
    snippet_kind = ""

    if name_hits:
        snippet_kind = "Dateiname"
    if path.suffix.lower() in _TEXT_EXT or path.suffix.lower() == ".docx":
        text = _read_text(path).lower()
        if text:
            content_hits = sum(1 for w in words if w in text)
            if content_hits and not snippet_kind:
                snippet_kind = "Inhalt"

    if not name_hits and not content_hits:
        return 0.0, ""

    score = name_hits * 10.0 + content_hits * 3.0

    if name_hits + content_hits >= len(words):
        score += 8.0

    try:
        age_days = (now - path.stat().st_mtime) / 86400
        if age_days < 30:
            score += max(0.0, 5.0 - age_days / 6)
    except Exception:
        pass
    return score, snippet_kind


def smart_search(parameters: dict, player=None) -> str:
    """Tool-Entry-Point. query (Pflicht), folder (optional)."""
    query = (parameters.get("query") or "").strip()
    if not query:
        return "Bitte gib an, wonach ich suchen soll."
    words = [w.lower() for w in query.split() if len(w) >= 3][:8]
    if not words:
        words = [query.lower()]

    folder = parameters.get("folder")
    roots = [Path(folder)] if folder and Path(folder).is_dir() else _default_roots()

    started = time.time()
    scanned = 0
    results: list[tuple[float, Path, str]] = []

    for root in roots:
        try:
            iterator = root.rglob("*")
        except Exception:
            continue
        for path in iterator:
            if scanned >= _MAX_FILES or (time.time() - started) > _MAX_SECONDS:
                break
            try:
                if path.is_dir():
                    continue
                if any(part in _SKIP_DIRS for part in path.parts):
                    continue
                scanned += 1
                s, kind = _score(path, words, started)
                if s > 0:
                    results.append((s, path, kind))
            except Exception:
                continue

    if not results:
        return (f"Nichts zu '{query}' gefunden ({scanned} Dateien durchsucht in "
                f"{', '.join(str(r) for r in roots)}).")

    results.sort(key=lambda t: -t[0])
    top = results[:8]
    lines = [f"{p.name} ({kind}-Treffer) - {p}" for _, p, kind in top]
    more = f" (+{len(results)-8} weitere)" if len(results) > 8 else ""
    return (f"{len(results)} Treffer zu '{query}'{more}, beste zuerst: "
            + " | ".join(lines))
