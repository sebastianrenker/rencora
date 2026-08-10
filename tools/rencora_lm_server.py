"""RencoraLM v3 als lokaler, OpenAI-kompatibler Server (Port 5151).

Stellt /health, /v1/models und /v1/chat/completions (streaming + nicht-streaming)
bereit, damit RENCORA sein eigenes lokales Modell nutzen kann. Reines NumPy, keine
GPU noetig. RencoraLM v3 ist ein Textfortsetzer, kein Werkzeug-Aufrufer -> tool_calls
bleibt leer.
"""

import argparse
import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL_ID = "rencoralm-v3"
_ENGINE = None


def _add_platform_to_path():
    """rencora-platform stellt das rencora.lm-Paket bereit. Pfad ueber die
    Umgebungsvariable RENCORA_PLATFORM oder als Nachbarordner dieses Repos."""
    here = Path(__file__).resolve()
    cands = []
    if os.environ.get("RENCORA_PLATFORM"):
        cands.append(Path(os.environ["RENCORA_PLATFORM"]))
    cands += [p / "rencora-platform" for p in here.parents]
    for c in cands:
        if (c / "rencora" / "lm").is_dir():
            sys.path.insert(0, str(c))
            return
    raise SystemExit("rencora-platform nicht gefunden. RENCORA_PLATFORM setzen.")


def _finde_bundle(explizit):
    """Modell-Bundle finden. Reihenfolge: --bundle, RENCORA_LM_BUNDLE,
    ./models/bundle_v3 neben dem Repo."""
    here = Path(__file__).resolve()
    cands = []
    if explizit:
        cands.append(Path(explizit))
    if os.environ.get("RENCORA_LM_BUNDLE"):
        cands.append(Path(os.environ["RENCORA_LM_BUNDLE"]))
    cands += [here.parents[1] / "models" / "bundle_v3", here.parents[1] / "bundle_v3"]
    for p in cands:
        if (p / "modell.npz").exists():
            return p
    raise SystemExit("Kein RencoraLM-Bundle gefunden. --bundle PFAD oder "
                     "RENCORA_LM_BUNDLE setzen.")


def _lade_engine(bundle):
    global _ENGINE
    from rencora.lm.engine import RencoraLMEngine
    t0 = time.time()
    _ENGINE = RencoraLMEngine.lade(bundle)
    c = _ENGINE.config
    print(f"[RencoraLM] {bundle} geladen in {time.time()-t0:.1f}s | "
          f"Schritt {c.get('schritte')} | val_ppl {c.get('val_ppl')}", flush=True)


def _prompt(messages):
    for m in reversed(messages):
        if m.get("role") == "user":
            return (m.get("content") or "").strip() or "Der"
    return "Der"


def _generiere(messages, max_tokens):
    seed = _prompt(messages)
    n = max(16, min(int(max_tokens or 120), 200))
    txt = _ENGINE.generiere(seed, n=n, temperature=0.7, top_k=40)
    if txt.startswith(seed):
        txt = txt[len(seed):]
    return " ".join(txt.split()).strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.rstrip("/")
        if p == "/health":
            self._json(200, {"status": "ok", "model": MODEL_ID})
        elif p == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": MODEL_ID, "object": "model", "owned_by": "renker-industries"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._json(400, {"error": {"message": f"bad request: {e}"}})
            return

        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        try:
            text = _generiere(req.get("messages") or [], req.get("max_tokens") or 120)
        except Exception as e:
            self._json(500, {"error": {"message": f"generation failed: {e}"}})
            return

        if not req.get("stream"):
            self._json(200, {
                "id": cid, "object": "chat.completion", "created": int(time.time()),
                "model": MODEL_ID,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text,
                                         "tool_calls": []}}]})
            return

        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def sse(delta, finish=None):
            choice = {"index": 0, "delta": delta}
            if finish:
                choice["finish_reason"] = finish
            payload = {"id": cid, "object": "chat.completion.chunk",
                       "created": int(time.time()), "model": MODEL_ID, "choices": [choice]}
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
            self.wfile.flush()

        sse({"role": "assistant"})
        for i, w in enumerate(text.split(" ")):
            sse({"content": w if i == 0 else " " + w})
        sse({}, finish="stop")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5151)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--bundle", default=None)
    args = ap.parse_args()

    bundle = _finde_bundle(args.bundle)
    _add_platform_to_path()
    _lade_engine(bundle)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[RencoraLM] http://{args.host}:{args.port} ({MODEL_ID})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
