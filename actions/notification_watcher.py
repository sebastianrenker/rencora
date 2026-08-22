"""
actions/notification_watcher.py

NEUE DATEI - faengt Windows-Benachrichtigungen ab (Toasts: Mail, Teams,
WhatsApp Desktop, etc.) und lasst RENCORA sie zusammenfassen/vorlesen.
Ergaenzt computer_settings.py (das OS-Aktionen AUSFUEHRT) um die
umgekehrte Richtung: OS-Ereignisse EMPFANGEN.

PLATTFORM-REALITAET (wichtig, da requirements.txt Windows/macOS/Linux
gleichzeitig unterstuetzt):
- Windows: nutzt die UserNotificationListener-API aus winrt
  (Paket: winrt-Windows.UI.Notifications.Management +
  winrt-Windows.UI.Notifications). Erfordert einmalig eine
  Nutzerfreigabe (Windows fragt beim ersten Aufruf "App X moechte auf
  Benachrichtigungen zugreifen" - das ist ein OS-Dialog, kein RENCORA-Code).
- macOS/Linux: Es gibt keine stabile, dokumentierte System-API, um
  fremde Toasts programmatisch mitzulesen (macOS sperrt das bewusst aus
  Privacy-Gruenden ab, Linux haengt vom jeweiligen Notification-Daemon
  ab). Der Watcher deaktiviert sich dort automatisch und meldet das
  einmalig im Log - kein Crash, keine vage Fehlfunktion.

Dadurch bleibt das Modul auf allen drei Plattformen sicher importierbar;
es liefert nur unter Windows tatsaechlich Daten.

INTEGRATION:
- Laeuft NICHT als main.py-Tool (es gibt nichts zu "rufen" - es ist ein
  passiver Listener), sondern wird wie hologram_bridge per
  `NotificationWatcher().start()` in main() einmalig gestartet (siehe
  PATCH_main.py.txt).
- Eingehende Benachrichtigungen werden NICHT sofort laut vorgelesen
  (das waere bei z.B. 20 Mails/Stunde extrem nervig). Statt dessen
  landen sie in einer kurzen Queue, die der proactive_engine-Check
  `check_pending_notifications` periodisch geb√ºndelt zusammenfasst -
  siehe unten `drain_pending()`, das genau dafuer gedacht ist.
- Eine simple Filterliste (NOISY_APPS) unterdrueckt App-Kategorien, die
  erfahrungsgemaess nur Rauschen erzeugen (z.B. Download-Fortschritt).
"""

from __future__ import annotations

import platform
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional


NOISY_APPS = {"Windows Security", "Windows-Sicherheit", "Microsoft Store"}
MAX_QUEUE = 50


@dataclass
class CapturedNotification:
    app: str
    title: str
    body: str
    ts: float


class NotificationWatcher:
    """Singleton-artig wie hologram_bridge: eine Instanz pro Prozess."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[CapturedNotification]" = queue.Queue(maxsize=MAX_QUEUE)
        self._thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._supported = platform.system() == "Windows"
        self._warned_unsupported = False

    def start(self) -> None:
        if not self._supported:
            if not self._warned_unsupported:
                print(
                    "[NotificationWatcher] ℹ Notification capture is only "
                    "available on Windows — disabled on this platform."
                )
                self._warned_unsupported = True
            return

        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._run_windows, daemon=True, name="NotificationWatcherThread"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def drain_pending(self) -> list[CapturedNotification]:
        """
        Holt alle aktuell wartenden Benachrichtigungen aus der Queue
        (non-blocking) - gedacht fuer einen periodischen Check in
        core/proactive_engine.py, NICHT fuer sofortiges 1:1-Vorlesen.
        """
        items: list[CapturedNotification] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return items


    def _run_windows(self) -> None:
        try:
            self._listen_windows_loop()
        except ImportError:
            print(
                "[NotificationWatcher] ℹ Package 'winrt' not installed — "
                "run: pip install winrt-Windows.UI.Notifications.Management "
                "winrt-Windows.UI.Notifications  (optional feature, RENCORA "
                "works fine without it)."
            )
        except Exception as e:
            print(f"[NotificationWatcher]  Disabled after error: {e}")

    def _listen_windows_loop(self) -> None:


        from winrt.windows.ui.notifications.management import (
            UserNotificationListener,
            UserNotificationListenerAccessStatus,
        )

        listener = UserNotificationListener.get_current()
        access = listener.request_access_async().get()

        if access != UserNotificationListenerAccessStatus.ALLOWED:
            print(
                "[NotificationWatcher]  Notification access not granted. "
                "Allow it in Windows Settings → Privacy → Notifications if "
                "you want RENCORA to read incoming toasts."
            )
            return

        print("[NotificationWatcher]  Listening for Windows notifications.")
        seen_ids: set[int] = set()

        while not self._stop_requested.is_set():
            try:
                notifications = listener.get_notifications_async(0x07).get()
                for notif in notifications:
                    notif_id = notif.id
                    if notif_id in seen_ids:
                        continue
                    seen_ids.add(notif_id)

                    app_name = notif.app_info.display_info.display_name if notif.app_info else "Unknown"
                    if app_name in NOISY_APPS:
                        continue

                    title, body = self._extract_text(notif)
                    self._enqueue(CapturedNotification(app=app_name, title=title, body=body, ts=time.time()))


                if len(seen_ids) > 500:
                    seen_ids.clear()

            except Exception as e:
                print(f"[NotificationWatcher]  Poll error (continuing): {e}")

            time.sleep(4)

    @staticmethod
    def _extract_text(notif) -> tuple[str, str]:
        try:
            binding = notif.notification.visual.get_binding(
                notif.notification.visual.bindings[0].template
            ) if notif.notification.visual.bindings else None
            texts = [t.text for t in binding.get_text_elements()] if binding else []
            title = texts[0] if len(texts) > 0 else ""
            body = " ".join(texts[1:]) if len(texts) > 1 else ""
            return title, body
        except Exception:
            return "", ""

    def _enqueue(self, item: CapturedNotification) -> None:
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(item)
            except queue.Empty:
                pass


notification_watcher = NotificationWatcher()


def check_pending_notifications(ctx) -> Optional["ProactiveEvent"]:  # noqa: F821 (Typ nur fuer Doku)
    """
    Check-Funktion fuer core/proactive_engine.py CHECKS-Liste. Buendelt
    alle seit dem letzten Durchlauf aufgelaufenen Benachrichtigungen zu
    EINER kurzen Meldung statt jede einzeln vorzulesen.

    Einbindung in proactive_engine.py:
        from actions.notification_watcher import check_pending_notifications
        CHECKS.append(check_pending_notifications)
    (siehe PATCH_proactive_engine_checks.txt fuer den exakten Diff)
    """
    from core.proactive_engine import ProactiveEvent

    pending = notification_watcher.drain_pending()
    if not pending:
        return None

    if len(pending) == 1:
        n = pending[0]
        message = f"Notification from {n.app}: {n.title} {n.body}".strip()
    else:
        apps = ", ".join(sorted({n.app for n in pending}))
        message = f"You've got {len(pending)} new notifications — from {apps}."


    try:
        from core.hologram_bridge import hologram_bridge
        hologram_bridge.send_notification(message, level="info")
    except Exception:
        pass

    return ProactiveEvent(message=message, channel="notification", cooldown_seconds=0)
