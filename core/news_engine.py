"""
core/news_engine.py — gemeinsame Nachrichten-Engine.

Wird von ZWEI Oberflaechen genutzt:
  - dashboard/server.py  (/api/globe-news fuer Web-Dashboard + Mobile-App)
  - ui.py                (natives NEWS-Terminal in der exe)

Holt pro Land mehrere RSS-Quellen quer durchs politische Spektrum
(dashboard/news_sources.py), haengt die feste Bias-Einstufung an und
uebersetzt nicht-deutsche Schlagzeilen in einem einzigen Gemini-Aufruf.
Ergebnisse werden 10 Minuten pro Land gecacht.
"""
import json
from core.secrets import get_gemini_key
import re
import sys
import time
import threading
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
CACHE_TTL_SECONDS = 600

_cache: dict[str, tuple[float, list]] = {}
_cache_lock = threading.Lock()


def _gemini_key() -> str | None:
    try:
        cfg = json.loads((BASE_DIR / "config" / "api_keys.json")
                         .read_text(encoding="utf-8"))
        return get_gemini_key()
    except Exception:
        return None


def translate_headlines_de(headlines: list[str], api_key: str) -> list[str]:
    """Alle Schlagzeilen in EINEM Gemini-Aufruf uebersetzen; bei jedem
    Fehler kommen die Originaltexte zurueck (News duerfen nie blockieren)."""
    if not headlines:
        return []
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        numbered = "\n".join(f"{i + 1}) {t}" for i, t in enumerate(headlines))
        prompt = (
            "Uebersetze die folgenden Nachrichten-Schlagzeilen ins Deutsche. "
            "Gib NUR die uebersetzten Zeilen zurueck, exakt in der gleichen "
            "nummerierten Reihenfolge, ein Eintrag pro Zeile, ohne weitere "
            "Erklaerungen oder Kommentare:\n\n" + numbered
        )
        resp = client.models.generate_content(model="gemini-2.5-flash",
                                              contents=prompt)
        text = (resp.text or "").strip()
        parsed: dict[int, str] = {}
        for line in text.splitlines():
            m = re.match(r"^\s*(\d+)\)\s*(.+)$", line)
            if m:
                parsed[int(m.group(1))] = m.group(2).strip()
        return [parsed.get(i + 1, headlines[i]) for i in range(len(headlines))]
    except Exception:
        return headlines


def fetch_news(country: str = "de", translate: bool = True,
               per_source: int = 5) -> list[dict]:
    """
    Synchoner Abruf aller Quellen eines Landes. Ergebnis-Items:
      {title, link, source, bias, bias_color, lang[, original_title]}
    """
    with _cache_lock:
        cached = _cache.get(country)
        if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

    from dashboard.news_sources import SOURCES, BIAS_COLORS, FEED_USER_AGENT

    sources = SOURCES.get(country, SOURCES["de"])
    items: list[dict] = []
    try:
        import xml.etree.ElementTree as ET
        import requests

        for name, url, bias, lang in sources:
            try:
                resp = requests.get(url, timeout=6,
                                    headers={"User-Agent": FEED_USER_AGENT})
                root = ET.fromstring(resp.content)
                count = 0
                for it in root.iter("item"):
                    title = (it.findtext("title") or "").strip()
                    link = (it.findtext("link") or "").strip()
                    if not title:
                        continue
                    items.append({
                        "title": title, "link": link, "source": name,
                        "bias": bias,
                        "bias_color": BIAS_COLORS.get(bias, "#9dffb0"),
                        "lang": lang,
                    })
                    count += 1
                    if count >= per_source:
                        break
            except Exception:
                continue
    except Exception:
        pass

    if translate:
        api_key = _gemini_key()
        if api_key:
            idx = [i for i, it in enumerate(items) if it["lang"] != "de"]
            if idx:
                translated = translate_headlines_de(
                    [items[i]["title"] for i in idx], api_key)
                for i, tr in zip(idx, translated):
                    items[i]["original_title"] = items[i]["title"]
                    items[i]["title"] = tr

    with _cache_lock:
        _cache[country] = (time.time(), items)
    return items
