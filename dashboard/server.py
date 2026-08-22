"""
dashboard/server.py — RENCORA Local HTTP Dashboard

Plain HTTP on port 8000 (no SSL warnings, no firewall issues).
Security at the application layer: AES-256-CBC with session-key-derived key.
CryptoJS is auto-downloaded once and served locally — no CDN needed after that.

Install deps:  pip install fastapi "uvicorn[standard]" cryptography
"""

import asyncio
from core.secrets import get_gemini_key
import base64
import hashlib
import re
import secrets
import socket
import string
import time
from pathlib import Path

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    import uvicorn
    _DEPS_OK = True
except ImportError:
    pass


_UPLOAD_OK = False
try:
    from fastapi import UploadFile, File as FastAPIFile
    _UPLOAD_OK = True
except Exception:
    pass

BASE_DIR    = Path(__file__).resolve().parent.parent
STATIC_DIR  = Path(__file__).parent / "static"
PORT        = 8000
MAX_UPLOAD_MB = 500


TOKEN_TTL_SECONDS          = 12 * 3600
TOKEN_IDLE_TIMEOUT_SECONDS = 2 * 3600


LOGIN_MAX_ATTEMPTS   = 5
LOGIN_WINDOW_SECONDS = 300
LOGIN_BLOCK_SECONDS  = 300


def _make_uploads_dir() -> Path:
    """Return (and create) the cross-platform uploads folder."""
    for candidate in [
        Path.home() / "Downloads" / "RENCORA Uploads",
        Path.home() / "Documents" / "RENCORA Uploads",
        BASE_DIR / "uploads",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    return BASE_DIR / "uploads"


UPLOADS_DIR = _make_uploads_dir()


def _safe_filename(raw: str) -> str:
    """Reduziert einen vom Client gelieferten Dateinamen auf einen sicheren
    Basisnamen: entfernt Verzeichnisanteile (Pfad-Traversal) und ersetzt
    problematische Zeichen. Der Rueckgabewert enthaelt nie Separatoren."""
    name = Path(raw).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(". ")
    return name or "upload"

def _get_gemini_key() -> str | None:
    try:
        import json as _json
        with open(BASE_DIR / "config" / "api_keys.json", "r", encoding="utf-8") as f:
            return get_gemini_key()
    except Exception:
        return None

_KEY_CHARS = [c for c in (string.ascii_uppercase + string.digits)
              if c not in ('O', 'I', 'L', '0', '1')]


_AES_SALT = b'RENCORA-DASHBOARD-v1'


def _derive_key(session_key: str) -> bytes:
    """SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed)."""
    return hashlib.sha256(session_key.encode('utf-8') + _AES_SALT).digest()


def _decrypt_gcm(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(IV[12] ‖ ciphertext‖tag[16]) with AES-256-GCM.

    Matches the layout produced by the browser's native WebCrypto
    SubtleCrypto.encrypt('AES-GCM', ...), which appends the 16-byte
    auth tag to the end of the ciphertext. GCM provides authenticated
    encryption (integrity + confidentiality) — unlike the previous
    CBC mode, a tampered or truncated payload fails to decrypt instead
    of silently producing garbage plaintext.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(enc_b64)
    nonce, ct_and_tag = raw[:12], raw[12:]
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, ct_and_tag, None).decode('utf-8')


_CRYPTOJS_CDN  = ("https://cdnjs.cloudflare.com/ajax/libs/"
                  "crypto-js/4.2.0/crypto-js.min.js")
_CRYPTOJS_FILE = STATIC_DIR / "crypto-js.min.js"


def _firewall_settings() -> tuple[bool, bool]:
    """Liest (lan_firewall, allow_network_profile_change) aus config/security.json.

    lan_firewall (Standard True): darf ueberhaupt eine Firewall-Regel fuer den
      LAN-Zugriff angelegt werden. False = keine Netzwerk-/Rechteanhebung.
    allow_network_profile_change (Standard False): darf ein als "Oeffentlich"
      markiertes Netzwerk auf "Privat" umgestellt werden. Standard aus, weil das
      die Firewall in fremden Netzen (z. B. oeffentliches WLAN) schwaechen wuerde.
    """
    try:
        import json as _json
        cfg = _json.loads((BASE_DIR / "config" / "security.json").read_text(encoding="utf-8"))
        return (bool(cfg.get("lan_firewall", True)),
                bool(cfg.get("allow_network_profile_change", False)))
    except Exception:
        return (True, False)


def _ensure_network_access(port: int) -> None:
    """Cross-platform, best-effort: open port in the OS firewall for LAN access.

    Runs in a background thread — never blocks uvicorn startup. Die eingehende
    Regel ist auf das lokale Subnetz beschraenkt (nur Geraete im selben Netz,
    z. B. das eigene Handy), niemals fuer beliebige entfernte Hosts.

    Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW
              (native UAC dialog, guaranteed to appear). One-time setup.
    macOS   : osascript admin dialog if the Application Firewall is on.
    Linux   : pkexec GUI → sudo -n → prints manual command as fallback.
    """
    import sys, subprocess, os, tempfile, threading

    lan_firewall, allow_profile_change = _firewall_settings()
    if not lan_firewall:
        print("[Dashboard] LAN-Firewallregel per Konfiguration deaktiviert "
              "(lan_firewall=false). Fernzugriff nur ueber den Internet-Tunnel.")
        return


    if sys.platform == "win32":
        import ctypes, time

        port_rule = f"RENCORA Dashboard Port {port}"
        prog_rule  = "RENCORA Dashboard Python"
        py_exe     = sys.executable

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        need_port    = not _netsh_rule_exists(port_rule)
        need_prog    = not _netsh_rule_exists(prog_rule)
        need_private = allow_profile_change and _network_is_public()
        if not allow_profile_change and _network_is_public():
            print("[Dashboard] Netzwerk ist als 'Oeffentlich' eingestuft. RENCORA "
                  "aendert das nicht automatisch (allow_network_profile_change=false). "
                  "Fuer LAN-Zugriff das Netzwerk in den Windows-Einstellungen auf "
                  "'Privat' stellen oder den Internet-Tunnel nutzen.")

        if not need_port and not need_prog and not need_private:
            return


        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        if need_port:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rule}" protocol=TCP dir=in '
                f'localport={port} action=allow '
                f'remoteip=LocalSubnet profile=private'
            )
        if need_prog:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{prog_rule}" dir=in action=allow '
                f'program="{py_exe}" enable=yes '
                f'remoteip=LocalSubnet profile=private'
            )

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="rencora_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))
            os.close(fd)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            return


        try:
            r = subprocess.run(
                [bat_path], capture_output=True, timeout=8, shell=True
            )
            if r.returncode == 0:
                print(f"[Dashboard] Firewall configured for port {port}.")
                try:
                    os.unlink(bat_path)
                except Exception:
                    pass
                return
        except Exception:
            pass


        print("[Dashboard] One-time network setup required.")
        print("[Dashboard] >>> A Windows security dialog will appear — click 'Yes' <<<")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                bat_path,
                None,
                None,
                0,
            )
            if int(ret) > 32:


                time.sleep(2)
                print(f"[Dashboard] Network setup complete — port {port} is open.")
                print("[Dashboard] Refresh your phone browser to connect.")
            else:
                print("[Dashboard] Setup was not allowed.")
                print("[Dashboard] Phone connections may fail until RENCORA is run as Administrator.")
        except Exception as e:
            print(f"[Dashboard] Firewall setup error: {e}")
        finally:

            def _cleanup(path: str) -> None:
                time.sleep(5)
                try:
                    os.unlink(path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()
        return


    if sys.platform == "darwin":
        fw_ctl = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        try:
            r = subprocess.run(
                [fw_ctl, "--getglobalstate"], capture_output=True, text=True, timeout=5,
            )
            if "disabled" in r.stdout.lower():
                return

            py = sys.executable
            listed = subprocess.run(
                [fw_ctl, "--listapps"], capture_output=True, text=True, timeout=5,
            )
            if py in listed.stdout:
                return

            print("[Dashboard] One-time network setup — enter your password in the macOS dialog.")
            subprocess.run(
                ["osascript", "-e",
                 f'do shell script "{fw_ctl} --add {py} && {fw_ctl} --unblockapp {py}"'
                 f' with administrator privileges'],
                timeout=60,
            )
        except Exception:
            pass
        return


    def _privileged(cmd: list[str]) -> bool:
        for prefix in (["pkexec"], ["sudo", "-n"]):
            try:
                r = subprocess.run(prefix + cmd, capture_output=True, timeout=30)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    try:
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
        if "active" in r.stdout.lower():
            if _privileged(["ufw", "allow", f"{port}/tcp"]):
                print(f"[Dashboard] ufw: port {port} allowed.")
            else:
                print(f"[Dashboard] Run manually:  sudo ufw allow {port}/tcp")
            return
    except FileNotFoundError:
        pass

    try:
        r = subprocess.run(
            ["firewall-cmd", "--state"], capture_output=True, text=True, timeout=5,
        )
        if "running" in r.stdout.lower():
            ok = (_privileged(["firewall-cmd", "--add-port", f"{port}/tcp", "--permanent"])
                  and _privileged(["firewall-cmd", "--reload"]))
            if ok:
                print(f"[Dashboard] firewalld: port {port} allowed.")
            else:
                print(f"[Dashboard] Run manually:  sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload")
            return
    except FileNotFoundError:
        pass

    try:
        r = subprocess.run(["iptables", "-L", "INPUT", "-n"], capture_output=True, timeout=5)
        if r.returncode == 0:
            if _privileged(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]):
                print(f"[Dashboard] iptables: port {port} opened.")
            else:
                print(f"[Dashboard] Run manually:  sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    except FileNotFoundError:
        pass


def _ensure_crypto_js() -> None:
    if _CRYPTOJS_FILE.exists():
        return
    try:
        import urllib.request
        print("[Dashboard] Downloading CryptoJS (one-time setup)…")
        urllib.request.urlretrieve(_CRYPTOJS_CDN, str(_CRYPTOJS_FILE))
        print("[Dashboard] CryptoJS cached — will serve locally from now on.")
    except Exception as e:
        print(f"[Dashboard] CryptoJS download failed: {e}")
        print(f"[Dashboard] Encryption will fall back to CDN load on client.")


_ensure_crypto_js()


def _local_ip() -> str:
    """Return the best LAN-facing IPv4 address, no internet required."""

    for probe in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass


    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass


    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


class DashboardServer:

    def __init__(self):
        self._ip                          = _local_ip()

        self._tokens: dict[str, dict]     = {}
        self._token_keys: dict[str, str]  = {}
        self._aes_cache:  dict[str, bytes]= {}

        self._failed_logins: dict[str, list] = {}

        self._login_blocked_until: dict[str, float] = {}
        self._clients: set[WebSocket]     = set()
        self._history: list[dict]         = []
        self._command_queue               = asyncio.Queue()
        self._wake_callback               = None
        self._connect_callback            = None
        self._pending_keys: dict[str, float] = {}
        self._last_key: str | None = None
        self._device_sessions: dict[str, dict] = {}
        self._phone_audio_queue: asyncio.Queue    = asyncio.Queue(maxsize=200)
        self._uploads_dir                 = UPLOADS_DIR
        self._last_net_io = None
        self._last_net_t: float = 0.0
        self._login_html                  = _read("login.html")
        self._app_html                    = _read("app.html")
        self.app                          = self._build_app()


    def new_key(self, expiry_secs: int = 600) -> str:
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        key = ''.join(secrets.choice(_KEY_CHARS) for _ in range(6))
        self._pending_keys[key] = now + expiry_secs
        self._last_key = key
        return key

    @staticmethod
    def _ssl_enabled() -> bool:
        certs = BASE_DIR / "config" / "certs"
        return (certs / "rencora.key").exists() and (certs / "rencora.crt").exists()

    def get_url(self) -> str:
        proto = "https" if self._ssl_enabled() else "http"
        return f"{proto}://{self._ip}:{PORT}"

    def get_manual_url(self) -> str:
        """URL for manual browser entry. When HTTPS active, points to alias port (also HTTPS)."""
        if self._ssl_enabled():
            return f"{self._ip}:{PORT + 1}"
        return f"{self._ip}:{PORT}"

    def _aes_key(self, session_key: str) -> bytes:
        if session_key not in self._aes_cache:
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk:
            return None
        try:
            return _decrypt_gcm(self._aes_key(sk), enc_b64)
        except Exception:
            return None


    def _issue_token(self, session_key: str) -> str:
        """Create a fresh auth token bound to a session_key, with created/
        last_used timestamps for later TTL + idle-timeout enforcement."""
        tok = secrets.token_urlsafe(32)
        now = time.time()
        self._tokens[tok] = {"created": now, "last_used": now}
        self._token_keys[tok] = session_key
        self._aes_key(session_key)
        return tok

    def _token_valid(self, tok: str) -> bool:
        """True if tok exists and hasn't exceeded its absolute TTL or gone
        idle too long. Updates last_used on success. Expired tokens are
        removed so they don't linger in memory."""
        if not tok:
            return False
        info = self._tokens.get(tok)
        if info is None:
            return False
        now = time.time()
        if now - info["created"] > TOKEN_TTL_SECONDS:
            self._revoke_token(tok)
            return False
        if now - info["last_used"] > TOKEN_IDLE_TIMEOUT_SECONDS:
            self._revoke_token(tok)
            return False
        info["last_used"] = now
        return True

    def _revoke_token(self, tok: str) -> None:
        self._tokens.pop(tok, None)
        self._token_keys.pop(tok, None)


    @staticmethod
    def _client_ip(req: "Request") -> str:
        return req.client.host if req.client else "unknown"

    def _is_login_blocked(self, ip: str) -> bool:
        until = self._login_blocked_until.get(ip)
        if until is None:
            return False
        if time.time() >= until:
            self._login_blocked_until.pop(ip, None)
            self._failed_logins.pop(ip, None)
            return False
        return True

    def _record_failed_login(self, ip: str) -> None:
        now = time.time()
        attempts = [t for t in self._failed_logins.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
        attempts.append(now)
        self._failed_logins[ip] = attempts
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            self._login_blocked_until[ip] = now + LOGIN_BLOCK_SECONDS

    def _record_successful_login(self, ip: str) -> None:
        self._failed_logins.pop(ip, None)
        self._login_blocked_until.pop(ip, None)


    def set_wake_callback(self, fn) -> None:
        self._wake_callback = fn

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn


    async def broadcast(self, msg: dict) -> None:
        self._history.append(msg)
        if len(self._history) > 300:
            self._history = self._history[-300:]
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead


    def _build_app(self) -> "FastAPI":
        app = FastAPI(docs_url=None, redoc_url=None)

        def _auth(req: Request) -> bool:
            tok = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            return self._token_valid(tok)


        @app.get("/static/crypto.js")
        async def serve_crypto():
            if _CRYPTOJS_FILE.exists():
                return FileResponse(str(_CRYPTOJS_FILE),
                                    media_type="application/javascript")
            from fastapi.responses import RedirectResponse
            return RedirectResponse(_CRYPTOJS_CDN)

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            return HTMLResponse(self._login_html)


        @app.get("/globe", response_class=HTMLResponse)
        async def globe_page():
            globe_file = Path(__file__).parent / "static" / "globe.html"
            try:
                return HTMLResponse(globe_file.read_text(encoding="utf-8"))
            except Exception:
                return HTMLResponse("Globe-Seite nicht gefunden.", status_code=404)

        @app.get("/api/globe-news")
        async def globe_news(country: str = "de"):
            """
            Nachrichten pro Land — nutzt die gemeinsame Engine in
            core/news_engine.py (mehrere Quellen quer durchs Spektrum,
            feste Bias-Einstufung, Batch-Uebersetzung, 10-Minuten-Cache).
            Der blockierende Abruf laeuft im Executor, damit der
            Event-Loop frei bleibt.
            """
            try:
                from core.news_engine import fetch_news
                items = await asyncio.get_event_loop().run_in_executor(
                    None, fetch_news, country)
                return JSONResponse(items)
            except Exception:
                return JSONResponse([])


        @app.get("/", response_class=HTMLResponse)
        async def index():


            html = (self._app_html
                    .replace("__IP__", self._ip)
                    .replace("__PORT__", str(PORT)))
            return HTMLResponse(html)

        @app.post("/login")
        async def login(req: Request):
            ip = self._client_ip(req)
            if self._is_login_blocked(ip):
                return JSONResponse(
                    {"ok": False, "error": "Too many failed attempts. Try again later."},
                    status_code=429,
                )
            body    = await req.json()
            entered = str(body.get("pin", "")).strip().upper()
            now     = time.time()
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                del self._pending_keys[entered]
                self._record_successful_login(ip)
                tok = self._issue_token(entered)
                if self._connect_callback:
                    self._connect_callback()
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Remote connection established."}
                ))

                return JSONResponse({"ok": True, "token": tok})
            self._record_failed_login(ip)
            return JSONResponse({"ok": False, "error": "Invalid or expired key"},
                                status_code=401)

        @app.get("/auto-login")
        async def auto_login(req: Request, key: str = ""):
            """QR code target — validates one-time key, creates session, redirects phone."""
            ip  = self._client_ip(req)
            now = time.time()
            if self._is_login_blocked(ip):
                return HTMLResponse("Too many attempts. Try again later.", status_code=429)
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                self._record_failed_login(ip)
                return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
  h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px}
</style></head>
<body><div><h2>Link Expired</h2>
<p>Press <strong style="color:#afffaf">Remote Control</strong> in RENCORA to get a new QR code.</p>
</div></body></html>""")

            del self._pending_keys[key]
            self._record_successful_login(ip)
            tok     = self._issue_token(key)
            dev_tok = secrets.token_urlsafe(32)
            self._device_sessions[dev_tok] = {"session_key": key}

            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Remote connection established via QR code."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('rencora_token','{tok}');
  sessionStorage.setItem('rencora_key','{key}');
  localStorage.setItem('rencora_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},400);
</script>
<p>Connecting to RENCORA…</p>
</body></html>""")

        @app.post("/api/pair")
        async def pair_native(req: Request):
            """Natives App-Pairing (Android/iPad). Nimmt denselben Einmal-Key
            entgegen, den auch der QR-Code für den Browser enthält, und gibt
            Token + Device-Token als JSON zurück statt als HTML-Redirect mit
            sessionStorage-JS (das eine native App nicht ausführen kann)."""
            ip  = self._client_ip(req)
            now = time.time()
            if self._is_login_blocked(ip):
                return JSONResponse({"ok": False, "error": "too_many_attempts"}, status_code=429)
            try:
                body = await req.json()
            except Exception:
                body = {}
            key = (body.get("key") or "").strip()
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                self._record_failed_login(ip)
                return JSONResponse({"ok": False, "error": "expired_or_invalid"}, status_code=401)

            del self._pending_keys[key]
            self._record_successful_login(ip)
            tok     = self._issue_token(key)
            dev_tok = secrets.token_urlsafe(32)
            self._device_sessions[dev_tok] = {"session_key": key}

            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "App-Verbindung hergestellt (Pairing-Code)."}
            ))
            return JSONResponse({"ok": True, "token": tok, "device_token": dev_tok, "key": key})

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            """Return a fresh auth token for a previously paired device token."""
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False}, status_code=400)
            dev_tok = (body.get("device_token") or "").strip()
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            session_key = self._device_sessions[dev_tok]["session_key"]
            tok = self._issue_token(session_key)
            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Known device reconnected automatically."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/revoke-devices")
        async def revoke_devices(req: Request):
            """Invalidate all persistent device tokens (admin action)."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            count = len(self._device_sessions)
            self._device_sessions.clear()
            return JSONResponse({"ok": True, "revoked": count})

        @app.post("/api/command")
        async def command(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body  = await req.json()
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc   = body.get("enc", "")
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Decryption failed"}, status_code=400)
            else:
                text = (body.get("text") or "").strip()
            if text:
                await self._command_queue.put(text)
                if self._wake_callback:
                    self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/wake")
        async def wake_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True})


        if _UPLOAD_OK:
            @app.post("/api/vision/upload")
            async def vision_upload(
                req: Request,
                file: UploadFile = FastAPIFile(...),
                text: str = "",
            ):
                """Nimmt ein Foto von der App entgegen (z.B. 'Hey BASI,
                analysiere dieses Objekt' mit Kamerabild) und speist es in
                dieselbe Gemini-Live-Vision-Session ein, die auch die PC-
                Webcam benutzt. Die Antwort kommt asynchron über /ws
                (type=='log') an alle verbundenen Geräte zurück."""
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)
                try:
                    image_bytes = await file.read()
                except Exception as e:
                    return JSONResponse({"error": f"read_failed: {e}"}, status_code=400)
                if not image_bytes:
                    return JSONResponse({"error": "empty_file"}, status_code=400)

                mime_type = file.content_type or "image/jpeg"
                try:
                    from actions.screen_processor import analyze_external_image
                except Exception as e:
                    return JSONResponse(
                        {"error": f"vision_module_unavailable: {e}"}, status_code=500
                    )

                ok = analyze_external_image(image_bytes, mime_type, text)
                if self._wake_callback:
                    self._wake_callback()
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Foto von der App empfangen — analysiere..."}
                ))
                return JSONResponse({"ok": ok})


        @app.websocket("/ws/phone-audio")
        async def phone_audio_ws(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not self._token_valid(tok):
                await websocket.close(code=4001)
                return
            await websocket.accept()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Phone microphone live."}
            ))
            try:
                while True:
                    data = await websocket.receive_bytes()
                    try:
                        self._phone_audio_queue.put_nowait(
                            {"data": data, "mime_type": "audio/pcm"}
                        )
                    except asyncio.QueueFull:
                        pass
            except WebSocketDisconnect:
                pass
            finally:
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Phone microphone stopped."}
                ))


        if _UPLOAD_OK:
            @app.post("/api/upload")
            async def upload_file(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

                safe = _safe_filename(file.filename or "upload")
                dest = self._uploads_dir / safe
                stem, suffix = Path(safe).stem, Path(safe).suffix
                counter = 1
                while dest.exists():
                    dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                try:
                    with open(dest, "wb") as fout:
                        while True:
                            chunk = await file.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                fout.close()
                                dest.unlink(missing_ok=True)
                                return JSONResponse(
                                    {"error": f"File too large (max {MAX_UPLOAD_MB} MB)"},
                                    status_code=413,
                                )
                            fout.write(chunk)
                except Exception as exc:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return JSONResponse({"error": str(exc)}, status_code=500)

                asyncio.create_task(self.broadcast({
                    "type": "file_received",
                    "name": dest.name,
                    "size": size,
                    "saved_to": str(self._uploads_dir),
                }))
                return JSONResponse({"ok": True, "name": dest.name, "size": size})
        else:
            @app.post("/api/upload")
            async def upload_unavailable(req: Request):
                return JSONResponse(
                    {"error": "File uploads require: pip install python-multipart"},
                    status_code=503,
                )


        if _UPLOAD_OK:
            @app.post("/api/secondbrain-upload")
            async def upload_secondbrain(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

                note = ""
                try:
                    note = (req.query_params.get("note") or "").strip()[:300]
                except Exception:
                    pass

                safe = _safe_filename(file.filename or "note")
                dest = self._uploads_dir / safe
                stem, suffix = Path(safe).stem, Path(safe).suffix
                counter = 1
                while dest.exists():
                    dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                try:
                    with open(dest, "wb") as fout:
                        while True:
                            chunk = await file.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                fout.close()
                                dest.unlink(missing_ok=True)
                                return JSONResponse(
                                    {"error": f"File too large (max {MAX_UPLOAD_MB} MB)"},
                                    status_code=413,
                                )
                            fout.write(chunk)
                except Exception as exc:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return JSONResponse({"error": str(exc)}, status_code=500)

                await self.broadcast({
                    "type": "secondbrain_received",
                    "name": dest.name,
                    "size": size,
                })


                note_part = f" Notiz vom Nutzer dazu: \"{note}\"." if note else ""
                instruction = (
                    f"[SECOND_BRAIN_UPLOAD] path={dest} | name={dest.name}\n"
                    f"Der Nutzer hat gerade '{dest.name}' fuers Second Brain "
                    f"hochgeladen.{note_part} Werte die Datei mit dem "
                    f"second_brain_save-Tool aus (file_path={dest}"
                    + (f", note=\"{note}\"" if note else "")
                    + f") und sag danach in maximal zwei kurzen Saetzen, was du dir "
                    f"gemerkt hast."
                )
                await self._command_queue.put(instruction)
                if self._wake_callback:
                    self._wake_callback()

                return JSONResponse({"ok": True, "name": dest.name, "size": size})
        else:
            @app.post("/api/secondbrain-upload")
            async def upload_secondbrain_unavailable(req: Request):
                return JSONResponse(
                    {"error": "File uploads require: pip install python-multipart"},
                    status_code=503,
                )

        @app.get("/api/theme")
        async def get_theme():
            """Aktives Farbprofil (config/themes.json) — haelt Browser-Dashboard
            und exe farblich synchron. Bewusst ohne Auth: reine Farbwerte,
            wird schon von der Login-Seite gebraucht."""
            try:
                from core.theme_manager import get_active_colors
                return JSONResponse(get_active_colors())
            except Exception:
                return JSONResponse({})

        @app.get("/api/system-status")
        async def system_status(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from actions.system_monitor import get_system_status
                data = get_system_status()


                import psutil
                now = time.time()
                io = psutil.net_io_counters()
                if self._last_net_io is not None and now > self._last_net_t:
                    dt = now - self._last_net_t
                    data["net_sent_kbps"] = round(
                        (io.bytes_sent - self._last_net_io.bytes_sent) / 1024 / dt, 1)
                    data["net_recv_kbps"] = round(
                        (io.bytes_recv - self._last_net_io.bytes_recv) / 1024 / dt, 1)
                else:
                    data["net_sent_kbps"] = 0.0
                    data["net_recv_kbps"] = 0.0
                self._last_net_io = io
                self._last_net_t = now

                return JSONResponse(data)
            except Exception:
                return JSONResponse({"error": "unavailable"}, status_code=503)

        @app.get("/api/files")
        async def list_files(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            files = []
            try:
                for f in sorted(
                    (p for p in self._uploads_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    files.append({"name": f.name, "size": f.stat().st_size})
            except Exception:
                pass
            return JSONResponse({"files": files})

        @app.get("/uploads/{filename}")
        async def download_file(filename: str, token: str = ""):

            tok = token.strip()
            if not self._token_valid(tok):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = self._uploads_dir / safe
            if not path.exists() or not path.is_file():
                return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(path), filename=safe)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not self._token_valid(tok):
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            for entry in self._history[-50:]:
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "command":
                        enc = data.get("enc", "")
                        t   = self._decrypt(tok, enc) if enc else (data.get("text") or "").strip()
                        if t:
                            await self._command_queue.put(t)
                            if self._wake_callback:
                                self._wake_callback()
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        return app


    async def _serve_alias(self) -> None:
        """Second HTTPS server on PORT+1 sharing the same app and in-memory state.
        Chrome HTTPS-upgrades any bare IP:PORT the user types, so this port also needs TLS.
        User types IP:8001 → Chrome tries https → self-signed cert warning → accept once → done."""
        ssl_key  = BASE_DIR / "config" / "certs" / "rencora.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "rencora.crt"
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT + 1)
        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=PORT + 1, log_level="warning",
            ssl_keyfile=str(ssl_key), ssl_certfile=str(ssl_cert),
        )
        print(f"[Dashboard] Manual entry:  {self._ip}:{PORT + 1}  (type in browser, accept cert once)")
        await uvicorn.Server(cfg).serve()

    async def serve(self) -> None:
        global PORT
        log_path = BASE_DIR / "dashboard_error.log"

        def _dlog(msg: str) -> None:
            """Schreibt Dashboard-Statusmeldungen in eine Datei neben der exe -
            print() ist in der fensterlosen RENCORA.exe unsichtbar, deshalb war
            ein Server-Startfehler bisher komplett stumm."""
            try:
                from datetime import datetime as _dt
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
            except Exception:
                pass

        if not _DEPS_OK:
            msg = ("fastapi/uvicorn/cryptography konnten nicht geladen werden - "
                   "Dashboard deaktiviert. (In der exe: Build-Problem, bitte melden. "
                   "Im Quellcode-Betrieb: pip install fastapi uvicorn[standard] cryptography)")
            print(f"[Dashboard] {msg}")
            _dlog(msg)
            return


        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT)

        use_ssl  = self._ssl_enabled()
        ssl_key  = BASE_DIR / "config" / "certs" / "rencora.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "rencora.crt"


        import traceback as _tb

        base_port = PORT
        ssl_retry_done = False
        for port_try in range(base_port, base_port + 10):
            PORT = port_try
            cfg = uvicorn.Config(
                self.app, host="0.0.0.0", port=port_try, log_level="warning",
                **({"ssl_keyfile": str(ssl_key), "ssl_certfile": str(ssl_cert)} if use_ssl else {}),
            )
            proto = "https" if use_ssl else "http"
            _dlog(f"Starte Dashboard auf {proto}://{self._ip}:{port_try} ...")
            print(f"[Dashboard] {proto}://{self._ip}:{port_try}")

            if use_ssl:
                asyncio.create_task(self._serve_alias())

            try:
                await uvicorn.Server(cfg).serve()
                _dlog("Dashboard-Server wurde regulaer beendet.")
                return
            except (SystemExit, OSError) as e:

                _dlog(f"Port {port_try} nicht nutzbar ({e!r}) - versuche naechsten Port.")
                continue
            except Exception:
                _dlog("Dashboard-Absturz:\n" + _tb.format_exc())
                if use_ssl and not ssl_retry_done:
                    _dlog("Versuche Neustart OHNE SSL (http) als Notfall-Fallback ...")
                    use_ssl = False
                    ssl_retry_done = True
                    continue
                _dlog("Dashboard endgueltig deaktiviert - siehe Fehler oben.")
                return

        _dlog(f"Kein freier Port zwischen {base_port} und {base_port + 9} gefunden - "
              "Dashboard deaktiviert. Belegt ein anderes Programm alle diese Ports?")
