#!/usr/bin/env bash
# Construye una versión 100% estática de la landing + /demo para publicarla en Vercel, Netlify o
# GitHub Pages. Sin backend: static-demo.js responde /api/* desde el navegador.
#
# Uso:
#   ./scripts/build-static-demo.sh                      # PUBLIC_SITE_URL=https://demo.example.com
#   PUBLIC_SITE_URL=https://mi-portfolio.vercel.app ./scripts/build-static-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# STATIC_DEMO_OUT permite construir en un directorio temporal (pruebas) sin tocar dist/.
OUT="${STATIC_DEMO_OUT:-$ROOT/dist}"
PUBLIC_SITE_URL="${PUBLIC_SITE_URL:-https://demo.example.com}"

rm -rf "$OUT"
mkdir -p "$OUT"

# Solo lo que el sitio necesita: HTML, CSS, JS, tipografías e imágenes. Nada de pruebas ni configs.
cp "$ROOT"/landing/*.html "$OUT"/
cp "$ROOT"/landing/*.css "$OUT"/
cp "$ROOT"/landing/*.js "$OUT"/
mkdir -p "$OUT/fonts"
cp "$ROOT"/landing/fonts/* "$OUT/fonts/" 2>/dev/null || true
for asset in favicon.svg og-image.png robots.txt sitemap.xml; do
  [ -f "$ROOT/landing/$asset" ] && cp "$ROOT/landing/$asset" "$OUT/"
done

# El marcador que reemplaza nginx (`sub_filter`) se resuelve aquí, en tiempo de build.
python - "$OUT" "$PUBLIC_SITE_URL" <<'PY'
import pathlib, sys
out, public = pathlib.Path(sys.argv[1]), sys.argv[2]
for page in out.glob('*'):
    if page.is_file() and page.suffix.lower() in {'.html', '.txt', '.xml', '.json'}:
        text = page.read_text(encoding='utf-8')
        page.write_text(text.replace('__PUBLIC_SITE_URL__', public), encoding='utf-8')
# En estático la API es el propio sitio: mismo origen, sin CORS ni cookies.
(out / 'config.js').write_text(
    'window.COPILOTO_CONFIG = {\n'
    '  chatwootUrl: "",\n'
    '  copilotoUrl: "",\n'
    '  pmsUrl: "",\n'
    '  websiteToken: "",\n'
    '  privacyUrl: "",\n'
    '  staticDemo: true,\n'
    '};\n', encoding='utf-8')
PY

# static-demo.js tiene que ejecutarse antes que demo.js para interceptar fetch.
python - "$OUT" <<'PY'
import pathlib, sys
out = pathlib.Path(sys.argv[1])
for page in out.glob('*.html'):
    text = page.read_text(encoding='utf-8')
    if 'static-demo.js' in text:
        continue
    text = text.replace('<script src="config.js', '<script src="static-demo.js" defer></script>\n<script src="config.js', 1)
    page.write_text(text, encoding='utf-8')
PY

# Rutas limpias: /demo sirve demo.html sin backend ni reescrituras propias.
# Netlify y hosts sin cleanUrls: /demo resuelve al HTML sin extensión.
printf '/demo  /demo.html  200
/privacidad  /demo.html  200
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
