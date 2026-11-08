"""OpenWA simulado para la prueba E2E (scripts/wa-e2e.sh). No habla con WhatsApp.

Hace de gateway: responde /api/sessions y /send-text (registrando lo que el puente "enviaría" al huésped) y,
por /_inject, entrega al puente un webhook `message.received` firmado igual que el OpenWA real.
"""

import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ["OPENWA_WEBHOOK_SECRET"]
API_KEY = os.environ.get("OPENWA_API_KEY", "")
BRIDGE = os.environ.get("BRIDGE_URL", "http://wa-bridge:8400")
SESSION = {"id": "fake-session-id", "name": "default", "status": "ready"}
SENT: list[dict] = []
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _send(self, code: int, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _authorized(self) -> bool:
        return not API_KEY or self.headers.get("X-API-Key") == API_KEY

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(200, {"status": "ok"})
        if self.path == "/_sent":
            with LOCK:
                return self._send(200, list(SENT))
        if not self._authorized():
            return self._send(401, {"error": "api key"})
        if self.path == "/api/sessions":
            return self._send(200, [SESSION])
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/_reset":
            with LOCK:
                SENT.clear()
            return self._send(200, {"ok": True})
        if self.path == "/_inject":
            return self._inject(self._body())
        if not self._authorized():
            return self._send(401, {"error": "api key"})
        if self.path == f"/api/sessions/{SESSION['id']}/messages/send-text":
            data = self._body()
            with LOCK:
                SENT.append({"chatId": data.get("chatId"), "text": data.get("text"), "at": time.time()})
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def _inject(self, spec: dict) -> None:
        chat_id = spec["chatId"]
        data = {"id": spec.get("id") or f"fake-{time.time_ns()}", "chatId": chat_id, "from": chat_id,
                "body": spec.get("body", ""), "type": spec.get("type", "chat"), "fromMe": spec.get("fromMe", False),
                "isGroup": spec.get("isGroup", False), "contact": {"pushName": spec.get("name", "Huésped E2E")}}
        raw = json.dumps({"event": "message.received", "sessionId": spec.get("sessionId", SESSION["id"]),
                          "idempotencyKey": data["id"], "data": data}).encode()
        signature = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        request = urllib.request.Request(f"{BRIDGE}/webhooks/openwa", data=raw, method="POST",
                                         headers={"Content-Type": "application/json", "X-OpenWA-Signature": signature})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                self._send(200, {"bridge_status": response.status})
        except urllib.error.HTTPError as error:
            self._send(200, {"bridge_status": error.code})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 2785), Handler).serve_forever()
