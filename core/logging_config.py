"""
core/logging_config.py — Zentrale Logging-Konfiguration für RENCORA.

Ersetzt die bisherigen verstreuten print(f"[Modul] ...")-Aufrufe durch ein
einheitliches logging-Setup:
  - Konsole: kurzes Format, INFO und höher
  - Datei (logs/rencora.log): ausführliches Format inkl. Timestamp, DEBUG und
    höher, mit Rotation (5 MB je Datei, 3 Backups) damit die Logdatei nicht
    unbegrenzt wächst.

Verwendung in jedem Modul:

    from core.logging_config import get_logger
    log = get_logger(__name__)
    log.info("Etwas ist passiert")
    log.error("Etwas ist schiefgelaufen: %s", exc)

Migration von bestehendem Code:
    print(f"[open_app] Blockiert: {app_name!r}")
    -> log.warning("Blockiert: %r", app_name)

Hinweis: Dieses Modul richtet das Root-Logging einmalig ein (idempotent -
mehrfaches Aufrufen von setup_logging() hängt keine doppelten Handler an).
Die Migration der ca. 190 bestehenden print(...)-Aufrufe in actions/*.py auf
log.* ist eine rein mechanische Anschlussarbeit und noch nicht überall
durchgeführt - das Modul selbst ist aber sofort einsatzbereit.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_LOG_DIR = _BASE_DIR / "logs"
_LOG_FILE = _LOG_DIR / "rencora.log"

_CONFIGURED = False


def setup_logging(level: int = logging.DEBUG) -> None:
    """Richtet Konsolen- und Datei-Handler am Root-Logger ein. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Gibt einen Logger zurück und stellt sicher, dass setup_logging()
    bereits gelaufen ist (wird beim ersten Aufruf automatisch nachgeholt)."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
