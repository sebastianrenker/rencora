"""
core/proactive_engine.py

NEUE DATEI - macht RENCORA proaktiv statt nur reaktiv.

Bisher meldet sich RENCORA ausschliesslich, wenn der Nutzer etwas sagt
oder ein Tool aufruft. Diese Datei fuegt einen Hintergrund-Loop hinzu,
der periodisch eine Reihe von "Checks" ausfuehrt (CPU/RAM-Last, faellige
Reminder, neue Kalendertermine, etc.) und RENCORA ueber session.speak()
unaufgefordert sprechen laesst, wenn ein Check etwas Meldenswertes findet.

ARCHITEKTUR:
- ProactiveEngine ist komplett eigenstaendig und kennt RencoraLive nicht
  direkt - sie bekommt bei start() nur eine `speak_fn`-Callback (also
  z.B. rencora.speak) und eine optionale `hologram` Referenz uebergeben.
  Dadurch bleibt main.py minimal-invasiv patchbar: ein Import + ein
  Task in der bestehenden TaskGroup.
- Jeder Check ist eine einzelne Funktion mit Signatur
      def check(ctx: ProactiveContext) -> ProactiveEvent | None
  registriert in CHECKS unten. Neue Checks ergaenzen heisst: Funktion
  schreiben, in CHECKS eintragen - fertig, kein bestehender Code wird
  angefasst.
- Cooldowns pro Check verhindern Spam (z.B. nicht alle 20s an die
  CPU-Last erinnern). Eigener Zustand pro Check liegt in
  ProactiveContext.state, das zwischen Durchlaeufen erhalten bleibt.
- Ein einfacher "Ruhe-Modus" (quiet_hours) unterdrueckt proaktive
  Meldungen nachts, ohne den Loop selbst zu stoppen (Checks laufen
  weiter, sie werden nur nicht gesprochen).

SICHERHEIT / ZURUECKHALTUNG:
- Proaktive Meldungen sind IMMER kurz (siehe PROACTIVE_PREFIX im Prompt-
  Patch) und unterbrechen niemals eine laufende Spracheingabe/-ausgabe
  (Check `ctx.is_busy()` vor jedem speak()).
- Bei jedem Fehler in einem einzelnen Check wird nur dieser Check
  uebersprungen - ein kaputter Check darf nie die ganze Engine crashen.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Callable, Optional

try:
    import psutil
except ImportError:
    psutil = None


POLL_INTERVAL_SECONDS = 20
DEFAULT_QUIET_HOURS    = (dtime(23, 0), dtime(7, 30))

CONFIG_REL_PATH = Path("config") / "proactive_settings.json"


def _base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _load_settings() -> dict:
    """
    Optionale Datei config/proactive_settings.json, z.B.:
    {
      "enabled": true,
      "quiet_hours": ["23:00", "07:30"],
      "cpu_threshold_percent": 90,
      "cpu_sustained_seconds": 120,
      "disk_low_gb": 10
    }
    Fehlt die Datei oder ein Feld, greifen die Defaults oben.
    """
    path = _base_dir() / CONFIG_REL_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@dataclass
class ProactiveEvent:
    """Was ein Check melden will."""
    message: str
    channel: str = "system"
    cooldown_seconds: int = 600
    priority: str = "normal"


@dataclass
class ProactiveContext:
    """Wird an jeden Check uebergeben. Haelt geteilten Zustand zwischen Durchlaeufen."""
    state: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    is_busy: Callable[[], bool] = lambda: False


def check_system_load(ctx: ProactiveContext) -> Optional[ProactiveEvent]:
    """Warnt, wenn CPU ueber laengere Zeit sehr hoch ist (z.B. haengender Prozess)."""
    if psutil is None:
        return None

    threshold = ctx.settings.get("cpu_threshold_percent", 90)
    sustained = ctx.settings.get("cpu_sustained_seconds", 120)

    cpu = psutil.cpu_percent(interval=None)
    key = "_cpu_high_since"

    if cpu < threshold:
        ctx.state.pop(key, None)
        return None

    since = ctx.state.get(key)
    now = time.monotonic()
    if since is None:
        ctx.state[key] = now
        return None

    if now - since < sustained:
        return None

    return ProactiveEvent(
        message=(
            f"Heads up — CPU load has been above {threshold}% for over "
            f"{sustained // 60} minutes. Might be worth checking what's running."
        ),
        channel="system",
        cooldown_seconds=900,
    )


def check_low_disk(ctx: ProactiveContext) -> Optional[ProactiveEvent]:
    """Warnt, wenn auf dem Systemlaufwerk wenig Platz frei ist."""
    if psutil is None:
        return None

    low_gb = ctx.settings.get("disk_low_gb", 10)
    try:
        usage = psutil.disk_usage(str(Path.home().anchor or "/"))
    except Exception:
        return None

    free_gb = usage.free / (1024 ** 3)
    if free_gb >= low_gb:
        return None

    return ProactiveEvent(
        message=(
            f"Your system drive is down to about {free_gb:.1f} GB free. "
            f"Want me to help clean something up?"
        ),
        channel="disk",
        cooldown_seconds=3600,
    )


def check_due_reminders(ctx: ProactiveContext) -> Optional[ProactiveEvent]:
    """
    Liest memory/long_term.json (Kategorie 'wishes'/'notes' wird vom
    bestehenden reminder-Tool nicht dafuer genutzt - Reminder laufen ueber
    den OS-Scheduler und feuern eigene Notify-Skripte). Dieser Check ist
    daher bewusst fuer eine ZWEITE, leichtgewichtige Klasse von Remindern
    gedacht: Dinge, die der Nutzer beilaeufig erwaehnt hat und die
    save_memory unter category="due_items" ablegt (siehe Prompt-Patch).
    Erwartetes Format pro Eintrag:
        {"due_items": {"<key>": {"value": "...", "due_at": "2026-06-30T09:00:00"}}}
    """
    mem_path = _base_dir() / "memory" / "long_term.json"
    if not mem_path.exists():
        return None
    try:
        data = json.loads(mem_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    due_items = data.get("due_items", {})
    if not isinstance(due_items, dict) or not due_items:
        return None

    now = datetime.now()
    fired_key = "_fired_due_items"
    fired = ctx.state.setdefault(fired_key, set())

    for key, entry in due_items.items():
        if key in fired or not isinstance(entry, dict):
            continue
        due_at_str = entry.get("due_at")
        if not due_at_str:
            continue
        try:
            due_at = datetime.fromisoformat(due_at_str)
        except ValueError:
            continue
        if now >= due_at:
            fired.add(key)
            return ProactiveEvent(
                message=f"Reminder — {entry.get('value', key)}",
                channel="reminder",
                cooldown_seconds=0,
                priority="high",
            )
    return None


def check_upcoming_calendar_event(ctx: ProactiveContext) -> Optional[ProactiveEvent]:
    """
    Meldet Kalendertermine, die in <=10 Minuten beginnen.
    Nutzt actions/calendar_mail.py (siehe dort), faellt aber still
    auf "nichts melden" zurueck, falls die Kalender-Integration nicht
    eingerichtet ist - das darf den Rest der Engine nie blockieren.
    """
    try:
        from actions.calendar_mail import get_upcoming_events
    except Exception:
        return None

    try:
        events = get_upcoming_events(within_minutes=10)
    except Exception:
        return None

    if not events:
        return None

    fired_key = "_fired_calendar_events"
    fired = ctx.state.setdefault(fired_key, set())

    for ev in events:
        ev_id = ev.get("id") or ev.get("summary")
        if ev_id in fired:
            continue
        fired.add(ev_id)
        when = ev.get("start_human", "soon")
        return ProactiveEvent(
            message=f"Just a heads up — \"{ev.get('summary', 'an event')}\" starts {when}.",
            channel="calendar",
            cooldown_seconds=0,
            priority="high",
        )
    return None


def check_unread_important_mail(ctx: ProactiveContext) -> Optional[ProactiveEvent]:
    """Meldet neue ungelesene, als wichtig markierte Mails (siehe calendar_mail.py)."""
    try:
        from actions.calendar_mail import get_unread_important_mail
    except Exception:
        return None

    try:
        mails = get_unread_important_mail()
    except Exception:
        return None

    if not mails:
        return None

    fired_key = "_fired_mail_ids"
    fired = ctx.state.setdefault(fired_key, set())

    for mail in mails:
        mail_id = mail.get("id")
        if not mail_id or mail_id in fired:
            continue
        fired.add(mail_id)
        sender = mail.get("from", "someone")
        subject = mail.get("subject", "")
        return ProactiveEvent(
            message=f"New message from {sender}: {subject}".strip(),
            channel="mail",
            cooldown_seconds=0,
        )
    return None


CHECKS: list[Callable[[ProactiveContext], Optional[ProactiveEvent]]] = [
    check_due_reminders,
    check_upcoming_calendar_event,
    check_unread_important_mail,
    check_system_load,
    check_low_disk,
]


try:
    from actions.notification_watcher import check_pending_notifications
    CHECKS.append(check_pending_notifications)
except Exception:
    pass


class ProactiveEngine:
    """
    Treibt die Checks periodisch an. Wird NICHT als eigener Thread
    gestartet, sondern als asyncio-Task in der bestehenden TaskGroup von
    RencoraLive.run()  - dadurch teilt sie sich
    automatisch den Lifecycle mit Connect/Reconnect und muss beim
    Reconnect nicht separat verwaltet werden.
    """

    def __init__(
        self,
        speak_fn: Callable[[str], None],
        is_busy_fn: Callable[[], bool] = lambda: False,
        hologram_notify_fn: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._speak_fn = speak_fn
        self._hologram_notify_fn = hologram_notify_fn
        settings = _load_settings()
        self._enabled = settings.get("enabled", True)
        self.ctx = ProactiveContext(settings=settings, is_busy=is_busy_fn)
        self._last_fired: dict[str, float] = {}
        self._quiet_start, self._quiet_end = self._parse_quiet_hours(settings)

    @staticmethod
    def _parse_quiet_hours(settings: dict) -> tuple[dtime, dtime]:
        raw = settings.get("quiet_hours")
        if not raw or len(raw) != 2:
            return DEFAULT_QUIET_HOURS
        try:
            start = dtime.fromisoformat(raw[0])
            end = dtime.fromisoformat(raw[1])
            return start, end
        except Exception:
            return DEFAULT_QUIET_HOURS

    def _in_quiet_hours(self) -> bool:
        now = datetime.now().time()
        start, end = self._quiet_start, self._quiet_end
        if start <= end:
            return start <= now <= end

        return now >= start or now <= end

    async def run_forever(self) -> None:
        """Async-Loop, als Task in main.py's TaskGroup eingehaengt."""
        import asyncio

        if not self._enabled:
            return

        while True:
            try:
                self._run_once()
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def _run_once(self) -> None:
        if self.ctx.is_busy():
            return

        for check in CHECKS:
            try:
                event = check(self.ctx)
            except Exception:
                traceback.print_exc()
                continue

            if event is None:
                continue

            if event.priority != "high" and self._in_quiet_hours():
                continue

            last = self._last_fired.get(event.channel, 0.0)
            if time.monotonic() - last < event.cooldown_seconds:
                continue

            self._last_fired[event.channel] = time.monotonic()
            self._fire(event)

    def _fire(self, event: ProactiveEvent) -> None:
        print(f"[ProactiveEngine]  ({event.channel}) {event.message}")
        try:
            self._speak_fn(event.message)
        except Exception:
            traceback.print_exc()

        if self._hologram_notify_fn:
            try:
                self._hologram_notify_fn(event.message, event.channel)
            except Exception:
                pass
