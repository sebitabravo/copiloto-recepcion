"""Pruebas de aceptación del arranque oficial (`make demo-local`) sobre una copia limpia del repositorio.

Uso: make demo-local-check   (o: python3 scripts/check_demo_local.py [copia-ya-hecha])
Sin argumento copia los archivos versionados y los nuevos no ignorados a un directorio temporal: sin .venv,
sin .demo-local y sin landing/config.js, como un clon recién hecho. Necesita los puertos 8080, 8100 y 8200
libres, `make`, `uv` y `ps` (Linux o macOS). Tarda uno o dos minutos (la copia instala sus dependencias).

1. LIMPIO=0 conserva una solicitud de prueba entre dos arranques; LIMPIO=1 la borra.
2. Un landing/config.js viejo (túnel) no desvía la demo local.
3. Puerto ocupado → error claro, ningún proceso iniciado.
4. Plazo vencido → dice qué servicio no respondió y detiene solo lo suyo.
5. Un servicio que se cae → dice cuál, detiene el resto; un proceso ajeno sigue vivo.
6. Ctrl+C → se detienen los tres y los puertos quedan libres.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def clean_copy() -> str:
    root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    files = subprocess.check_output(["git", "ls-files", "-z", "-co", "--exclude-standard"], cwd=root, text=True)
    target = tempfile.mkdtemp(prefix="copiloto-copia-")
    for name in filter(None, files.split("\0")):
        source = os.path.join(root, name)
        if os.path.isfile(source):
            os.makedirs(os.path.dirname(os.path.join(target, name)), exist_ok=True)
            shutil.copy2(source, os.path.join(target, name))
    return target


temporary = len(sys.argv) < 2
repo = clean_copy() if temporary else sys.argv[1]
print(f"Copia limpia: {repo}", flush=True)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("PASA " if ok else "FALLA") + f" · {name}" + (f" · {detail}" if detail else ""), flush=True)


def get(url):
    with opener.open(url, timeout=5) as response:
        return response.status, response.read().decode()


def post(url, body):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read())


def port_free(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def start(limpio=None, env=None):
    args = ["make", "--no-print-directory", "demo-local"] + ([f"LIMPIO={limpio}"] if limpio is not None else [])
    return subprocess.Popen(args, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            env={**os.environ, **(env or {})}, start_new_session=True)


def wait_for(proc, marker, timeout=240):
    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        lines.append(line.rstrip())
        if marker in line:
            return True, lines
    return False, lines


def interrupt(proc):
    # Ctrl+C en la terminal llega a todo el grupo de primer plano (make y el lanzador).
    os.killpg(proc.pid, signal.SIGINT)
    try:
        out = proc.communicate(timeout=20)[0]
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out = proc.communicate()[0]
    return out


def guest_request(session):
    post("http://127.0.0.1:8080/api/demo/chat", {"session_id": session, "message": "Hablar con recepción",
                                                  "client_message_id": "prueba-arranque-1"})
    _, body = get(f"http://127.0.0.1:8080/api/demo/conversation?session_id={session}")
    return json.loads(body).get("request")


SESSION = "prueba-arranque-limpio-0001"
config_path = os.path.join(repo, "landing", "config.js")
with open(config_path, "w") as stale:
    stale.write('window.COPILOTO_CONFIG = {copilotoUrl: "https://tunel-viejo.example.com"};\n')

# 1) Primer arranque limpio + solicitud de prueba.
proc = start(limpio=1)
ok, lines = wait_for(proc, "listo")
check("arranque desde copia limpia imprime «listo»", ok, lines[-1] if lines else "")
if not ok:
    print("\n".join(lines))
    interrupt(proc)
    sys.exit(1)
_, config = get("http://127.0.0.1:8080/config.js")
check("config.js viejo no desvía la demo local", "localhost:8100" in config and "tunel-viejo" not in config)
request = guest_request(SESSION)
check("se crea una solicitud de prueba", bool(request), request and request.get("code"))
out = interrupt(proc)
time.sleep(0.5)
check("Ctrl+C detiene los tres servicios", all(port_free(p) for p in (8080, 8100, 8200)), out.strip().splitlines()[-1])

# 2) LIMPIO=0 conserva la solicitud.
proc = start(limpio=0)
ok, lines = wait_for(proc, "listo")
_, body = get(f"http://127.0.0.1:8080/api/demo/conversation?session_id={SESSION}")
kept = json.loads(body).get("request")
check("LIMPIO=0 conserva la solicitud", ok and bool(kept) and kept.get("code") == request.get("code"),
      kept and kept.get("code"))

# 5) Un servicio que se cae: el lanzador dice cuál y detiene el resto; un proceso ajeno sigue vivo.
outsider = subprocess.Popen(["sleep", "300"])
listing = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True).splitlines()
# El proceso Python del copiloto (no el `uv run` que lo lanzó): simula una caída real del servicio.
pid = next(int(line.split()[0]) for line in listing
           if "copiloto.app:create_app" in line and "--port 8100" in line and "uv run" not in line)
os.kill(pid, signal.SIGKILL)
try:
    out = proc.communicate(timeout=30)[0]
except subprocess.TimeoutExpired:
    out = ""
check("servicio caído → dice cuál", "el copiloto (:8100) se detuvo" in out, out.strip().splitlines()[-1] if out else "")
time.sleep(0.5)
check("servicio caído → detiene el resto", all(port_free(p) for p in (8080, 8200)) and proc.returncode != 0)
check("proceso ajeno sigue vivo", outsider.poll() is None)
outsider.kill()

# 3) Puerto ocupado → error claro sin iniciar nada.
blocker = socket.socket()
blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
blocker.bind(("127.0.0.1", 8100))
blocker.listen()
proc = start()
out = proc.communicate(timeout=30)[0]
check("puerto ocupado → error claro", "8100 (copiloto)" in out and proc.returncode != 0,
      out.strip().splitlines()[-1])
check("puerto ocupado → no inicia nada", port_free(8080) and port_free(8200))
blocker.close()

# 4) Plazo vencido.
proc = start(env={"DEMO_TIMEOUT": "0"})
out = proc.communicate(timeout=60)[0]
check("plazo vencido → nombra los servicios pendientes", "no respondieron en 0 s" in out and proc.returncode != 0,
      [line for line in out.splitlines() if "Error" in line][:1])
time.sleep(0.5)
check("plazo vencido → detiene lo suyo", all(port_free(p) for p in (8080, 8100, 8200)))

# 6) LIMPIO=1 borra.
proc = start(limpio=1)
ok, lines = wait_for(proc, "listo")
_, body = get(f"http://127.0.0.1:8080/api/demo/conversation?session_id={SESSION}")
check("LIMPIO=1 borra las solicitudes", ok and not json.loads(body).get("request"))
interrupt(proc)

os.remove(config_path)
if temporary:
    shutil.rmtree(repo, ignore_errors=True)
failed = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} comprobaciones pasan")
sys.exit(1 if failed else 0)
