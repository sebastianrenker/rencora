"""
core/version.py — zentrale Versionsnummer + Update-Pruefung.

Update-Quelle ist bewusst konfigurierbar (config/api_keys.json, Key
"update_url"): sobald Renker Industries Releases irgendwo hostet (eigener
Server, GitHub Releases, ...), zeigt die URL auf ein JSON der Form

    { "version": "21.1", "download_url": "https://.../Rencora_Setup_v21.1.exe",
      "notes": "Was ist neu ..." }

Ohne konfigurierte URL meldet check_for_update() sauber "keine Quelle" —
es wird nichts vorgetaeuscht.
"""
import json
import sys
from pathlib import Path

VERSION = "21.1"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _update_url() -> str | None:
    try:
        cfg = json.loads((_base_dir() / "config" / "api_keys.json")
                         .read_text(encoding="utf-8"))
        url = cfg.get("update_url", "").strip()
        return url or None
    except Exception:
        return None


def _newer(remote: str, local: str) -> bool:
    """Numerischer Versionsvergleich ('21.10' > '21.9', anders als Strings)."""
    def parts(v):
        return [int(p) for p in v.split(".") if p.isdigit()]
    return parts(remote) > parts(local)


def check_for_update(timeout: int = 8) -> dict:
    """
    Ergebnis-Dict:
      {"status": "no_source"}                          — keine update_url gesetzt
      {"status": "error", "detail": "..."}             — Netz/Formatfehler
      {"status": "up_to_date", "version": VERSION}
      {"status": "update", "version": "...", "download_url": "...", "notes": "..."}
    """
    url = _update_url()
    if not url:
        return {"status": "no_source"}
    try:
        import requests
        data = requests.get(url, timeout=timeout).json()
        remote = str(data.get("version", "")).strip()
        if not remote:
            return {"status": "error", "detail": "Manifest ohne 'version'-Feld"}
        if _newer(remote, VERSION):
            return {
                "status": "update",
                "version": remote,
                "download_url": data.get("download_url", ""),
                "notes": data.get("notes", ""),
            }
        return {"status": "up_to_date", "version": VERSION}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
