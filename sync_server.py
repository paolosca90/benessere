"""Server HTTP per ricevere da Android i dati Health Connect.

Esempio per la rete domestica (HTTP non cifrato!):
    python sync_server.py --lan
Accesso remoto: HTTPS reverse proxy autenticato e server bound a 127.0.0.1.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from benessere import db, health_sync

TOKEN_PATH = Path(__file__).resolve().parent / "data" / "android_sync_token.txt"
MAX_BODY_BYTES = 8 * 1024 * 1024


def get_or_create_token() -> str:
    # Token non caricato in Git: un solo device/utente nel MVP.
    env = os.environ.get("BENESSERE_SYNC_TOKEN", "").strip()
    if env:
        if len(env) < 24:
            raise ValueError("BENESSERE_SYNC_TOKEN deve avere almeno 24 caratteri")
        return env
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(token) < 24:
            raise ValueError("Token salvato non valido: rigeneralo manualmente")
        return token
    token = secrets.token_urlsafe(36)
    # Usa creazione esclusiva; non sovrascrivere un token generato da un altro processo.
    try:
        with TOKEN_PATH.open("x", encoding="utf-8") as f:
            f.write(token + "\n")
        try:
            os.chmod(TOKEN_PATH, 0o600)
        except OSError:
            pass
    except FileExistsError:
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    return token


class HealthHandler(BaseHTTPRequestHandler):
    server: "SyncHTTPServer"

    def log_message(self, fmt: str, *args) -> None:
        # Non loggare i dati sanitari né Authorization.
        if self.path != "/health":
            super().log_message(fmt, *args)

    def _send(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/api/v1/health-sync":
            self._send(404, {"error": "not found"})
            return
        provided = self.headers.get("Authorization", "")
        if not hmac.compare_digest(provided, "Bearer " + self.server.sync_token):
            self._send(401, {"error": "token non valido"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if not (0 < length <= MAX_BODY_BYTES):
            self._send(413, {"error": "payload vuoto o troppo grande"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            self._send(415, {"error": "richiesto JSON"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            conn = db.connect()
            try:
                health_sync.initialize(conn)
                result = health_sync.ingest_payload(conn, payload)
            finally:
                conn.close()
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)[:200]})
            return
        except Exception:
            self._send(500, {"error": "errore interno, consulta il terminale del server"})
            raise
        self._send(200, result)


class SyncHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], sync_token: str):
        super().__init__(address, HealthHandler)
        self.sync_token = sync_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend Android Health Connect → Benessere")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--lan", action="store_true", help="consente l'accesso in LAN senza TLS (solo Wi-Fi fidata)")
    args = parser.parse_args()
    token = get_or_create_token()
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    with SyncHTTPServer((host, args.port), token) as server:
        print(f"Backend Android in ascolto: {host}:{args.port}", flush=True)
        if args.lan:
            print("ATTENZIONE: HTTP in LAN non cifrato. Usa solo Wi-Fi privata fidata, mai Internet.", flush=True)
        print(f"Token per l'app Android: {token}", flush=True)
        print("Non pubblicare il token. Per un server remoto usa HTTPS con autenticazione.", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
