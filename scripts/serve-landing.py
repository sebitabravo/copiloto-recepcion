"""Servidor local de la portada para `make demo-local`: lo mismo que hace nginx en Docker, sin Docker.

- URLs limpias: /demo sirve demo.html (como `try_files $uri $uri.html` en infra/landing/nginx.conf).
- /privacidad, /static/ y /api/ se reenvían al copiloto, así los enlaces de la portada no quedan rotos.

Solo para desarrollo y presentación local: escucha en 127.0.0.1 y no agrega dependencias.
"""

import argparse
import http.server
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path

PROXIED = ("/api/", "/static/", "/privacidad")


class LandingHandler(http.server.SimpleHTTPRequestHandler):
    upstream = "http://127.0.0.1:8100"

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
    args = parser.parse_args()
    LandingHandler.upstream = args.upstream.rstrip("/")
    handler = partial(LandingHandler, directory=str(Path(args.root).resolve()))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
