"""Zentraler Zugriff auf den Gemini-Schluessel mit DPAPI-Schutz im Ruhezustand.

Beim ersten Lesen wird ein im Klartext gespeicherter Schluessel automatisch nach
DPAPI verschluesselt (`gemini_api_key_enc`) und der Klartext aus der Konfiguration
entfernt. Der verschluesselte Blob ist an das Windows-Benutzerkonto gebunden.
Auf Nicht-Windows-Systemen bleibt der Klartext-Fallback.
"""

import base64
import json
import logging
import sys
from pathlib import Path

from core import dpapi

_PLAIN = "gemini_api_key"
_ENC = "gemini_api_key_enc"
_cache: str | None = None
_log = logging.getLogger("rencora.secrets")


def _config_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent.parent
    return base / "config" / "api_keys.json"


def _load() -> dict:
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    _config_path().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def get_gemini_key() -> str:
    global _cache
    if _cache:
        return _cache
    d = _load()
    enc = d.get(_ENC)
    if enc and dpapi.available():
        try:
            _cache = dpapi.unprotect(base64.b64decode(enc)).decode("utf-8")
            return _cache
        except Exception:
            _log.warning(
                "DPAPI-Entschluesselung des Gemini-Schluessels fehlgeschlagen "
                "(korrupter Blob oder anderes Windows-Konto). Kein Schluessel geladen."
            )
    plain = d.get(_PLAIN, "") or ""
    if plain and dpapi.available():
        try:
            d[_ENC] = base64.b64encode(dpapi.protect(plain.encode("utf-8"))).decode("ascii")
            d.pop(_PLAIN, None)
            _save(d)
        except Exception:
            _log.warning(
                "DPAPI-Migration des Klartext-Schluessels fehlgeschlagen; "
                "Schluessel bleibt vorerst im Klartext gespeichert."
            )
    _cache = plain
    return plain


def set_gemini_key(key: str, extra: dict | None = None) -> None:
    global _cache
    d = _load()
    if extra:
        d.update(extra)
    if dpapi.available():
        d[_ENC] = base64.b64encode(dpapi.protect(key.encode("utf-8"))).decode("ascii")
        d.pop(_PLAIN, None)
    else:
        d[_PLAIN] = key
    _save(d)
    _cache = key


def is_configured() -> bool:
    d = _load()
    return bool(d.get(_ENC) or d.get(_PLAIN))
