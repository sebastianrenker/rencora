"""Stellt vor dem Build sicher, dass bin/cloudflared.exe vorhanden und gegen die
gepinnte SHA-256-Summe verifiziert ist. Die Binaerdatei liegt bewusst nicht im
Repository (Groesse); sie wird hier reproduzierbar und geprueft beschafft.

Nutzt die Download-/Verifikationslogik aus core/tunnel.py (gleiche gepinnte
Version und Pruefsumme wie zur Laufzeit)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import tunnel


def main() -> int:
    dest = tunnel.BIN_DIR / tunnel._binary_name()
    if dest.exists() and tunnel._verify(dest):
        print(f"[fetch] cloudflared bereits vorhanden und verifiziert: {dest}")
        return 0
    print(f"[fetch] Beschaffe cloudflared {tunnel.PINNED_VERSION} ...")
    p = tunnel.download_cloudflared()
    if p and tunnel._verify(p):
        print(f"[fetch] cloudflared bereit und verifiziert: {p}")
        return 0
    print("[fetch] cloudflared konnte nicht verifiziert beschafft werden.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
