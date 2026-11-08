"""Servidor local de la portada para `make demo-local`: lo mismo que hace nginx en Docker, sin Docker.

- URLs limpias: /demo sirve demo.html (como `try_files $uri $uri.html` en infra/landing/nginx.conf).
- /privacidad, /static/ y /api/ se reenvían al copiloto, así los enlaces de la portada no quedan rotos.
- Con --copiloto-url, /config.js se genera aquí y no se lee landing/config.js: un config.js que dejó un
  túnel o el stack Docker no puede desviar la demo local hacia otro servidor.

Solo para desarrollo y presentación local: escucha en 127.0.0.1 y no agrega dependencias.
"""

from __future__ import annotations

import argparse
import http.server
import json
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path

PROXIED = ("/api/", "/static/", "/privacidad")


def local_config(copiloto_url: str, pms_url: str) -> bytes:
    """config.js de la demo local: solo los servicios que levantó el lanzador (json evita romper las comillas)."""
    config = {"copilotoUrl": copiloto_url, "pmsUrl": pms_url, "privacyUrl": "/privacidad"}
    return f"window.COPILOTO_CONFIG = {json.dumps(config, indent=2)};\n".encode()


class LandingHandler(http.server.SimpleHTTPRequestHandler):
    upstream = "http://127.0.0.1:8100"
    config_js: bytes | None = None

    def _proxied(self) -> bool:
        return self.path.startswith(PROXIED)

    def _forward(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "content-length"}}
        request = urllib.request.Request(self.upstream + self.path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, reply_headers, payload = response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            status, reply_headers, payload = error.code, error.headers, error.read()
        except OSError:
            self.send_error(502, "El copiloto no responde en " + self.upstream)
            return
        self.send_response(status)
        for key, value in reply_headers.items():
            if key.lower() not in {"transfer-encoding", "connection", "content-length", "server", "date"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 (nombre de la API de http.server)
        if self._proxied():
            self._forward("GET")
            return
        clean = self.path.split("?", 1)[0]
        if clean == "/config.js" and self.config_js is not None:
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            # Sin caché: el navegador no debe seguir usando el config.js de un arranque anterior.
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(self.config_js)))
            self.end_headers()
            self.wfile.write(self.config_js)
            return
        if clean.endswith("/") is False and "." not in Path(clean).name:
            candidate = Path(self.directory) / (clean.lstrip("/") + ".html")
            if candidate.is_file():
                query = self.path[len(clean):]
                self.path = clean + ".html" + query
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self._proxied():
            self._forward("POST")
            return
        self.send_error(405)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return  # silencio: la terminal de la demo muestra solo lo útil


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="landing")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--upstream", default="http://127.0.0.1:8100")
    parser.add_argument("--copiloto-url", help="genera /config.js con esta API en vez de leer landing/config.js")
    parser.add_argument("--pms-url", default="http://localhost:8200")
    args = parser.parse_args()
    LandingHandler.upstream = args.upstream.rstrip("/")
    if args.copiloto_url:
        LandingHandler.config_js = local_config(args.copiloto_url.rstrip("/"), args.pms_url.rstrip("/"))
    handler = partial(LandingHandler, directory=str(Path(args.root).resolve()))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
