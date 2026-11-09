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
7. Secretos, bases y logs nuevos y existentes tienen permisos privados (POSIX y ACL de Windows).

Solo permisos, sin instalar dependencias ni iniciar servicios:
    python scripts/check_demo_local.py --permissions-only
"""
# ruff: noqa: E501 — los snippets PowerShell y POSIX van en una línea; partirlos cambia su significado.

import json
import os
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


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


def private_state(state):
    """Comprueba metadatos, nunca lee tokens, bases ni logs."""
    state = Path(state)
    return all(stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
               for path in [state, *state.rglob("*")])


def windows_acl(script, path):
    """PowerShell integrado; devuelve solo metadatos anonimizados, nunca contenido de archivos."""
    powershell = shutil.which("powershell.exe")
    assert powershell, "Falta Windows PowerShell para verificar ACL reales"
    command = ('$ErrorActionPreference = "Stop"; try { ' + script +
               ' } catch { [Console]::Error.Write($_.Exception.GetType().Name + ":" + $_.CategoryInfo.Reason); exit 1 }')
    result = subprocess.run([powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                            env={**os.environ, "DEMO_ACL_ROOT": str(path)},
                            capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, "Falló la preparación/inspección aislada de ACL: " + result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def acl_snapshot(state):
    return windows_acl(r'''
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$items = @(Get-Item -LiteralPath $env:DEMO_ACL_ROOT) + @(Get-ChildItem -LiteralPath $env:DEMO_ACL_ROOT -Force -Recurse)
$result = @(foreach ($item in $items) {
    $acl = if ($item.PSIsContainer) { [System.IO.Directory]::GetAccessControl($item.FullName) }
           else { [System.IO.File]::GetAccessControl($item.FullName) }
    $rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]) | ForEach-Object {
        $principal = switch ($_.IdentityReference.Value) {
            $me { "current-user"; break }
            "S-1-5-18" { "SYSTEM"; break }
            "S-1-5-32-544" { "Administrators"; break }
            default { "other" }
        }
        @{principal=$principal; inherited=$_.IsInherited; rights=[int]$_.FileSystemRights;
          allow=($_.AccessControlType -eq "Allow"); inheritance=[int]$_.InheritanceFlags}
    })
    @{relative=$item.FullName.Substring($env:DEMO_ACL_ROOT.Length).Replace("\", "/");
      directory=$item.PSIsContainer; protected=$acl.AreAccessRulesProtected; rules=$rules}
})
ConvertTo-Json -InputObject $result -Depth 6 -Compress
''', state)


def assert_private_acl(state, existing):
    snapshot = acl_snapshot(state)
    inherited_new = 0
    for item in snapshot:
        rules = item["rules"]
        assert {rule["principal"] for rule in rules} == {"current-user", "SYSTEM", "Administrators"}, "ACL amplia restante"
        assert len(rules) == 3 and all(rule["allow"] and rule["rights"] == 2032127 for rule in rules), "ACL inesperada"
        if item["directory"]:
            assert all(rule["inheritance"] == 3 for rule in rules), "Directorio sin herencia privada"
        new_file = item["relative"] in {"/new.sqlite", "/logs/new.log", "/effective-mask"}
        if item["relative"] == "" or (existing and not new_file):
            assert item["protected"] and not any(rule["inherited"] for rule in rules), "Herencia amplia no eliminada"
        else:
            assert all(rule["inherited"] for rule in rules), "Estado nuevo sin herencia privada"
        if new_file:
            inherited_new += 1
    assert inherited_new == 3, "Falta comprobar los archivos nuevos"
    print(f"ACL NTFS: objetos={len(snapshot)}, archivos nuevos con herencia privada={inherited_new}, "
          "principales=current-user/SYSTEM/Administrators, acceso amplio=0")


def permissions_only():
    source = Path(__file__).resolve().with_name("demo-local.sh")
    bash = "bash"
    if os.name == "nt":
        # Python puede encontrar el lanzador de WSL antes que Git Bash.
        git = Path(shutil.which("git") or "git")
        bash = next((str(base / suffix) for base in list(git.parents)[:3]
                     for suffix in ("usr/bin/bash.exe", "bin/bash.exe", "bash.exe")
                     if (base / suffix).is_file()), bash)
    for existing in (True, False):
        with tempfile.TemporaryDirectory(prefix="demo-permissions-") as folder:
            root = Path(folder)
            (root / "scripts").mkdir()
            (root / "pms_mock").mkdir()
            shutil.copy2(source, root / "scripts/demo-local.sh")
            mocks = root / "bin"
            mocks.mkdir()
            # Las sondas de puertos no usan la red; la generación de secretos sí usa Python real.
            python = mocks / "python3"
            python.write_text('#!/usr/bin/env bash\n'
                              'if [ "$1" = "-" ]; then exit 1; fi\n'
                              f'exec {shlex.quote(Path(sys.executable).as_posix())} "$@"\n')
            python.chmod(0o700)
            uv = mocks / "uv"
            # Hereda la umask como los servicios. Se detiene antes de instalar o arrancar nada.
            uv.write_text('#!/usr/bin/env bash\n'
                          ': > ../.demo-local/new.sqlite\n'
                          ': > ../.demo-local/logs/new.log\n'
                          'umask > ../.demo-local/effective-mask\n'
                          'exit 17\n')
            uv.chmod(0o700)
            chmod = mocks / "chmod"
            chmod.write_text('#!/usr/bin/env bash\nmode="$1"; shift\n'
                             'for path in "$@"; do\n'
                             f'  printf "%s|%s\\n" "$mode" "$path" >> {shlex.quote((root / "chmod-calls").as_posix())}\n'
                             'done\nexec /usr/bin/chmod "$mode" "$@"\n')
            chmod.chmod(0o700)
            state = root / ".demo-local"
            if os.name == "nt":
                windows_acl(r'''
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$sid = New-Object System.Security.Principal.SecurityIdentifier("S-1-1-0")
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.AddAccessRule($rule)
[System.IO.Directory]::SetAccessControl($env:DEMO_ACL_ROOT, $acl)
''', root)
            if existing:
                (state / "logs").mkdir(parents=True)
                state.chmod(0o777)
                (state / "logs").chmod(0o777)
                for name in ("panel-token", "staff-token", "events-token", "copiloto.sqlite",
                             "copiloto.sqlite-wal", "copiloto.sqlite-shm", "pms.sqlite",
                             "pms.sqlite-wal", "pms.sqlite-shm", "logs/copiloto.log",
                             "logs/pms.log", "logs/portada.log"):
                    path = state / name
                    path.write_text("fixture\n")
                    path.chmod(0o666)
                if os.name == "nt":
                    windows_acl(r'''
foreach ($path in @($env:DEMO_ACL_ROOT, (Join-Path $env:DEMO_ACL_ROOT "logs"), (Join-Path $env:DEMO_ACL_ROOT "copiloto.sqlite"))) {
    $directory = [System.IO.Directory]::Exists($path)
    $acl = if ($directory) { [System.IO.Directory]::GetAccessControl($path) } else { [System.IO.File]::GetAccessControl($path) }
    $sid = New-Object System.Security.Principal.SecurityIdentifier("S-1-1-0")
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, "FullControl", "Allow")
    $acl.AddAccessRule($rule)
    if ($directory) { [System.IO.Directory]::SetAccessControl($path, $acl) } else { [System.IO.File]::SetAccessControl($path, $acl) }
}
''', state)
                    before = acl_snapshot(state)
                    assert any(rule["inherited"] and rule["principal"] == "other"
                               for item in before for rule in item["rules"]), "Fixture sin herencia amplia"
                    assert any(not rule["inherited"] and rule["principal"] == "other"
                               for item in before for rule in item["rules"]), "Fixture sin acceso explícito amplio"
                    print("ACL NTFS inicial: acceso amplio heredado y explícito confirmado")
            test_path = os.pathsep.join((str(mocks), str(Path(bash).parent), os.environ["PATH"]))
            result = subprocess.run([bash, "-c", 'umask 000; exec "$BASH" scripts/demo-local.sh'],
                                    cwd=root, capture_output=True, text=True, encoding="utf-8",
                                    env={**os.environ, "PATH": test_path}, timeout=20)
            assert result.returncode == 17, (result.returncode, result.stdout, result.stderr)
            expected = "Preparando dependencias con uv…\n"
            if existing:
                expected = ("Se conservan las solicitudes de la sesión anterior (.demo-local/). "
                            "Para partir de cero: make demo-local LIMPIO=1\n" + expected)
            assert result.stdout == expected, result.stdout
            assert result.stderr == "", result.stderr
            assert (state / "effective-mask").read_text().strip() == "0077", "umask heredada no es 077"
            if os.name == "posix":
                assert private_state(state), "tokens, bases o logs tienen permisos abiertos"
            else:
                assert_private_acl(state, existing)
            if existing:
                calls = (root / "chmod-calls").read_text().splitlines()
                for path in [state, *state.rglob("*")]:
                    if path.name in {"new.sqlite", "new.log", "effective-mask"}:
                        continue
                    mode = "700" if path.is_dir() else "600"
                    suffix = path.relative_to(root).as_posix()
                    assert any(line.startswith(mode + "|") and line.endswith("/" + suffix)
                               for line in calls), f"no se restringió {suffix}"
            print(f"PASA permisos {'existentes' if existing else 'nuevos'}")
            if os.name == "nt" and existing:
                # Ambas salidas deben ocurrir antes de generar secretos, sincronizar o lanzar servicios.
                uv_marker = state / "effective-mask"
                marker_before = uv_marker.stat().st_mtime_ns
                for missing in (True, False):
                    failure_env = {**os.environ, "PATH": os.pathsep.join((str(mocks), str(Path(bash).parent)))}
                    if not missing:
                        fake = mocks / "powershell.exe"
                        fake.write_text("#!/usr/bin/env bash\nexit 23\n")
                        fake.chmod(0o700)
                    failed = subprocess.run([bash, "scripts/demo-local.sh"], cwd=root, capture_output=True,
                                            encoding="utf-8", env=failure_env, timeout=20)
                    assert failed.returncode == 1 and failed.stdout == "", "Fallo ACL no detuvo el arranque"
                    detail = ("falta Windows PowerShell (powershell.exe)" if missing
                              else "no se pudieron proteger los permisos de .demo-local con Windows PowerShell")
                    assert failed.stderr == f"Error: {detail}; no se inició ningún servicio.\n", "Error ACL no explicado"
                    assert uv_marker.stat().st_mtime_ns == marker_before, "Se ejecutó uv tras el fallo ACL"
                print("PASA fallo previo a servicios: PowerShell ausente/error ACL")
    print("2/2 comprobaciones de permisos pasan")


if sys.argv[1:] == ["--permissions-only"]:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    permissions_only()
    sys.exit(0)


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
if os.name == "posix":
    check("secretos, bases y logs tienen permisos privados", private_state(Path(repo) / ".demo-local"))
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
