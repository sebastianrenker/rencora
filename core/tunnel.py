"""
core/tunnel.py — Optionale Internet-Anbindung fuer das RENCORA Remote Dashboard.

Macht das Dashboard von ueberall im Internet erreichbar (z.B. per
Mobilfunknetz, wenn Handy und PC NICHT im selben WLAN sind), ganz ohne
Portfreigabe im Router oder DynDNS. Nutzt Cloudflares kostenlosen
"Quick Tunnel" (cloudflared) — ein signierter, oeffentlicher
https://*.trycloudflare.com-Link, der intern auf den lokalen
Dashboard-Server zeigt.

Faellt cloudflared nicht auf (nicht installiert, kein Internet zum
Runterladen o.ae.), bleibt RENCORA ganz normal im lokalen WLAN-Modus
nutzbar — dieses Modul ist rein additiv und darf niemals den Rest der
App blockieren oder crashen lassen.

Bonus: Da Cloudflare am oeffentlichen Ende ein echtes, gueltiges
TLS-Zertifikat ausstellt, verschwindet dabei auch die
"Selbstsigniertes Zertifikat"-Warnung, die man bei IP:PORT-Zugriff im
selben WLAN normalerweise einmal wegklicken muss.
"""

import asyncio
import hashlib
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
BIN_DIR  = BASE_DIR / "bin"

_URL_RE = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")


# Gepinnte cloudflared-Version mit bekannten SHA-256-Pruefsummen. Kein
# "latest": eine feste Version ist reproduzierbar und laesst sich gegen einen
# bekannten Hash pruefen, sodass eine manipulierte oder untergeschobene
# Binaerdatei niemals ausgefuehrt wird (Supply-Chain-Schutz).
PINNED_VERSION = "2026.7.3"
_RELEASE_BASE = "https://github.com/cloudflare/cloudflared/releases/download"

_DOWNLOAD_URLS = {
    "Windows": f"{_RELEASE_BASE}/{PINNED_VERSION}/cloudflared-windows-amd64.exe",
    "Linux":   f"{_RELEASE_BASE}/{PINNED_VERSION}/cloudflared-linux-amd64",
}

_EXPECTED_SHA256 = {
    "Windows": "8635da433b6df8194746e88ed9d2589566c20e38bfc2a80e431a348b7c765841",
    "Linux":   "9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17",
}


def _binary_name() -> str:
    return "cloudflared.exe" if platform.system() == "Windows" else "cloudflared"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify(path: Path) -> bool:
    """Prueft die Datei gegen die gepinnte SHA-256-Summe der jeweiligen
    Plattform. Fuer Plattformen ohne bekannten Hash wird nicht blockiert."""
    expected = _EXPECTED_SHA256.get(platform.system())
    if not expected:
        return True
    try:
        return _sha256(path).lower() == expected.lower()
    except Exception:
        return False


def find_cloudflared() -> Optional[Path]:
    """Sucht cloudflared: bevorzugt die selbst verwaltete, gegen die gepinnte
    Pruefsumme verifizierte Binaerdatei in BASE_DIR/bin/. Eine dortige Datei mit
    falschem Hash wird verworfen (kann untergeschoben sein). Danach PATH."""
    local = BIN_DIR / _binary_name()
    if local.exists():
        if _verify(local):
            return local
        print("[Tunnel] Lokale cloudflared-Binaerdatei entspricht nicht der "
              "erwarteten Pruefsumme und wird ignoriert.")
        try:
            local.unlink()
        except Exception:
            pass
    found = shutil.which("cloudflared")
    if found:
        return Path(found)
    return None


def download_cloudflared() -> Optional[Path]:
    """Laedt die gepinnte cloudflared-Version herunter (Windows/Linux amd64) und
    verifiziert sie gegen die bekannte SHA-256-Summe. Bei Abweichung wird die
    Datei verworfen. Wird in einem Thread aufgerufen, niemals im Event-Loop."""
    system = platform.system()
    url = _DOWNLOAD_URLS.get(system)
    if not url:
        print(f"[Tunnel] Kein Auto-Download fuer {system}. "
              f"Bitte cloudflared manuell installieren: "
              f"https://github.com/cloudflare/cloudflared/releases")
        return None
    try:
        import requests
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        dest = BIN_DIR / _binary_name()
        print(f"[Tunnel] Lade cloudflared {PINNED_VERSION} herunter (einmalig, ~30 MB)...")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        if not _verify(dest):
            print("[Tunnel] Pruefsumme der heruntergeladenen cloudflared stimmt "
                  "nicht — Datei wird verworfen (moegliche Manipulation).")
            try:
                dest.unlink()
            except Exception:
                pass
            return None
        if system != "Windows":
            dest.chmod(0o755)
        print(f"[Tunnel] cloudflared bereit und verifiziert: {dest}")
        return dest
    except Exception as e:
        print(f"[Tunnel] Download fehlgeschlagen: {e}")
        return None


class CloudflareTunnel:
    """Verwaltet einen optionalen `cloudflared tunnel --url ...`-Hintergrund-
    prozess und stellt die oeffentliche URL bereit, sobald sie feststeht.

    status: "idle" | "starting" | "running" | "failed" | "disabled"
    """

    def __init__(self, local_port: int, use_ssl: bool = False):
        self._local_port = local_port
        self._use_ssl     = use_ssl
        self.url: Optional[str] = None
        self.status: str = "idle"
        self._proc = None

    def _origin(self) -> str:
        proto = "https" if self._use_ssl else "http"
        return f"{proto}://127.0.0.1:{self._local_port}"

    async def run_forever(self) -> None:
        binary = find_cloudflared()
        if not binary:
            self.status = "starting"
            binary = await asyncio.to_thread(download_cloudflared)
        if not binary:
            self.status = "disabled"
            return

        args = [str(binary), "tunnel", "--url", self._origin()]
        if self._use_ssl:
            args += ["--no-tls-verify"]


        extra_kwargs = {}
        if sys.platform == "win32":
            import subprocess as _subprocess
            extra_kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW

        while True:
            self.status = "starting"
            self.url = None
            start_time = asyncio.get_event_loop().time()
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    **extra_kwargs,
                )
                async for raw in self._proc.stdout:
                    line = raw.decode(errors="ignore")
                    m = _URL_RE.search(line)
                    if m and not self.url:
                        self.url = m.group(0)
                        self.status = "running"
                        print(f"[Tunnel] Internet-Zugriff bereit: {self.url}")
                await self._proc.wait()
            except FileNotFoundError:
                self.status = "disabled"
                return
            except Exception as e:
                print(f"[Tunnel] Fehler: {e}")


            crashed_instantly = (asyncio.get_event_loop().time() - start_time) < 3.0
            if crashed_instantly:
                self._quick_fail_count = getattr(self, "_quick_fail_count", 0) + 1
            else:
                self._quick_fail_count = 0

            if self._quick_fail_count >= 5:
                self.status = "disabled"
                self.url = None
                print(
                    "[Tunnel] cloudflared stuerzt wiederholt sofort ab — "
                    "Internet-Tunnel wird deaktiviert. RENCORA laeuft normal "
                    "im lokalen WLAN weiter. Moegliche Ursachen: Antivirus/"
                    "Firewall blockiert cloudflared.exe, oder kein Internet."
                )
                return


            self.status = "failed"
            self.url = None
            await asyncio.sleep(10)

    def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
