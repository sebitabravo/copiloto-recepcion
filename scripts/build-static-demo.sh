#!/usr/bin/env bash
# Construye una versión 100% estática de la landing + /demo para publicarla en Vercel, Netlify o
# GitHub Pages. Sin backend: static-demo.js responde /api/* desde el navegador.
#
# Uso:
#   ./scripts/build-static-demo.sh                      # PUBLIC_SITE_URL=https://demo.example.com
#   PUBLIC_SITE_URL=https://mi-portfolio.vercel.app ./scripts/build-static-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# STATIC_DEMO_OUT: dist/ o un directorio externo vacío/creado por este script.
# Una salida externa lleva un marcador; nunca se limpia un directorio ajeno ni código fuente.
# En Vercel la imagen trae python3 (no siempre `python`) y no hace falta uv: este build solo usa
# la biblioteca estándar.
PYTHON_BIN="$(command -v python || command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || { echo "Falta python o python3 para construir el sitio." >&2; exit 1; }
OUT="${STATIC_DEMO_OUT:-$ROOT/dist}"
PUBLIC_SITE_URL="${PUBLIC_SITE_URL:-https://demo.example.com}"

# Validar ANTES de crear o borrar nada. Se resuelven también alias y enlaces a fuentes.
OUT="$("$PYTHON_BIN" - "$ROOT" "$OUT" <<'PY'
import pathlib
import shutil
import sys

# La shell y los tests reciben el mismo UTF-8/LF también con Python nativo de Windows.
sys.stdout.reconfigure(encoding='utf-8', newline='\n')
sys.stderr.reconfigure(encoding='utf-8', newline='\n')
root = pathlib.Path(sys.argv[1]).resolve()
asked = pathlib.Path(sys.argv[2])
out = asked.resolve()
marker = out / '.static-demo-output'
managed = (marker.is_file() and not marker.is_symlink()
           and marker.read_text(encoding='utf-8') == 'copiloto-static-demo-v1\n')
unsafe = (asked.is_symlink() or out == root or out in root.parents
          or (root in out.parents and out != root / 'dist')
          or (out.exists() and not out.is_dir())
          or (out != root / 'dist' and out.exists() and any(out.iterdir()) and not managed))
if unsafe:
    print('Error: STATIC_DEMO_OUT debe ser dist/ o una salida externa vacía o creada por este script.', file=sys.stderr)
    sys.exit(2)
out.mkdir(parents=True, exist_ok=True)
# Se conserva el directorio (Windows puede tenerlo abierto); no se siguen enlaces interiores.
for entry in out.iterdir():
    if entry.is_symlink() or not entry.is_dir():
        entry.unlink()
    else:
        shutil.rmtree(entry)
marker.write_text('copiloto-static-demo-v1\n', encoding='utf-8')
print(out.as_posix())
PY
)"

# Solo lo que el sitio necesita: HTML, CSS, JS, tipografías e imágenes. Nada de pruebas ni configs.
# config.js local (con hosts y tokens) nunca viaja: el build escribe uno propio más abajo.
cp "$ROOT"/landing/*.html "$OUT"/
cp "$ROOT"/landing/*.css "$OUT"/
find "$ROOT/landing" -maxdepth 1 -name '*.js' ! -name 'config.js' -exec cp {} "$OUT"/ \;
mkdir -p "$OUT/fonts"
cp "$ROOT"/landing/fonts/* "$OUT/fonts/" 2>/dev/null || true
for asset in favicon.svg og-image.png robots.txt sitemap.xml; do
  [ -f "$ROOT/landing/$asset" ] && cp "$ROOT/landing/$asset" "$OUT/"
done

# El marcador que reemplaza nginx (`sub_filter`) se resuelve aquí, en tiempo de build.
"$PYTHON_BIN" - "$OUT" "$PUBLIC_SITE_URL" <<'PY'
import pathlib, sys
out, public = pathlib.Path(sys.argv[1]), sys.argv[2]
for page in out.glob('*'):
    if page.is_file() and page.suffix.lower() in {'.html', '.txt', '.xml', '.json'}:
        text = page.read_text(encoding='utf-8')
        page.write_text(text.replace('__PUBLIC_SITE_URL__', public), encoding='utf-8')
PY

# config.js: modo estático o backend real, según COPILOTO_URL.
"$PYTHON_BIN" "$ROOT/scripts/write-static-config.py" "$OUT" "${COPILOTO_URL:-}"

# static-demo.js intercepta /api/* en el navegador: solo tiene sentido sin backend. Con COPILOTO_URL
# la página habla con el copiloto real por el proxy api/[...path].mjs.
if [ -z "${COPILOTO_URL:-}" ]; then
# static-demo.js tiene que ejecutarse antes que la interfaz (demo-shared.js) para interceptar fetch.
"$PYTHON_BIN" - "$OUT" <<'PY'
import pathlib, sys
out = pathlib.Path(sys.argv[1])
for page in out.glob('*.html'):
    text = page.read_text(encoding='utf-8')
    if 'static-demo.js' in text:
        continue
    text = text.replace('<script src="config.js', '<script src="static-demo.js" defer></script>\n<script src="config.js', 1)
    page.write_text(text, encoding='utf-8')
PY
fi

# Rutas limpias: /demo sirve demo.html sin backend ni reescrituras propias.
# /demo tiene que resolver en cualquier host: copia en carpeta (sirve /demo/ sin cleanUrls),
# redirección para Netlify y cleanUrls para Vercel.
mkdir -p "$OUT/demo" && cp "$OUT/demo.html" "$OUT/demo/index.html"
printf '/demo  /demo.html  200
' >"$OUT/_redirects"

cat >"$OUT/vercel.json" <<'JSON'
{
  "cleanUrls": true,
  "trailingSlash": false,
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {"key": "X-Content-Type-Options", "value": "nosniff"},
        {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"}
      ]
    }
  ]
}
JSON

FILES=$(find "$OUT" -type f | wc -l | tr -d ' ')
echo "Listo: dist/ con ${FILES} archivos · URL pública: ${PUBLIC_SITE_URL}"
echo "Publicar:  npx vercel deploy --prod dist    (o arrastra dist/ a Netlify)"
echo "Probar:    cd dist && python -m http.server 8099   → http://localhost:8099/demo.html"
echo "En Vercel/Netlify la ruta es /demo (cleanUrls o _redirects)"

# El modo elegido se informa al final, sin desplazar el resumen del build.
if [ -n "${COPILOTO_URL:-}" ]; then
  echo "Backend real: ${COPILOTO_URL} vía proxy /api/* (IA y voz activas)"
else
  echo "Sin backend: el guion estático responde /api/* en el navegador"
fi
