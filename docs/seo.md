# SEO y metadatos del sitio público

Portada `/` y simulador `/demo` se sirven estáticos con Nginx (`infra/landing/nginx.conf`) desde
`landing/`. Esta página explica qué lleva cada documento, de dónde sale la URL pública y cómo
comprobarlo. Las cifras de la portada salen del repositorio (cronómetro SLA de
`copiloto/src/copiloto/config.py`, inventario de `data/hotel.yaml` y `pms_mock`, FAQ verificadas y
licencias de `docs/stack-abierto.md`): no se publica ninguna cifra que no se pueda verificar en el
código o en los datos.

## Qué lleva la portada (`landing/index.html`)

| Elemento | Valor |
| --- | --- |
| `<title>` | `Copiloto de Recepción · Hotel Bordeluz` |
| `canonical` | `PUBLIC_SITE_URL/` |
| Open Graph | `og:type`, `og:site_name`, `og:locale` `es_CL`, `og:url`, `og:title`, `og:description`, `og:image` (`/og-image.png`, 1200×630) con ancho, alto, tipo y texto alternativo |
| Twitter | `summary_large_image` con título, descripción e imagen |
| `theme-color` | `#f3ebdf` (claro) y `#14100b` (oscuro), uno por `prefers-color-scheme` |
| Datos estructurados | JSON-LD `@graph` con `WebSite` y `SoftwareApplication` (categoría de negocio, sistema `Web`, gratis, `offers` en CLP, idioma `es`, y un `description` que dice que es un prototipo académico con datos ficticios) |
| Favicon | `landing/favicon.svg` (una sola pieza, también para legado: `/favicon.ico` se sirve con el mismo SVG) |
| `robots` | `index, follow` |

`landing/demo.html` lleva su propio canonical, Open Graph, Twitter card, `theme-color` y favicon. `/demo`
es una página pública (no lleva `noindex`) y aparece en el sitemap.

Las vistas internas (`/panel`, `/metricas` del copiloto y el PMS `/admin`) llevan `noindex, nofollow`
y no aparecen en el sitemap. Se sirven desde otro origen (puerto distinto del 8080), así que su
`robots.txt` propio —o su cabecera `X-Robots-Tag`— es el que manda para ellas.

## URL pública (`PUBLIC_SITE_URL`)

Ni `index.html` ni `demo.html` escriben la URL del sitio: llevan el marcador `__PUBLIC_SITE_URL__` y
Nginx lo reemplaza al servir (`sub_filter`), con el valor de la variable de entorno del contenedor
`landing`.

```yaml
# infra/docker-compose.yml (servicio landing)
environment:
  PUBLIC_SITE_URL: ${PUBLIC_SITE_URL:-http://localhost:8080}
  COPILOTO_UPSTREAM: ${COPILOTO_UPSTREAM:-http://copiloto:8100}
  NGINX_ENVSUBST_FILTER: ^(PUBLIC_SITE_URL|COPILOTO_UPSTREAM)$
```

- En local no hay que hacer nada: el valor por defecto es `http://localhost:8080`.
- En un dominio real, define `PUBLIC_SITE_URL=https://copiloto.tu-hotel.cl` en `.env` **sin barra
  final** y recrea el contenedor para que la plantilla se vuelva a procesar:

  ```bash
  MSYS_NO_PATHCONV=1 docker compose -f infra/docker-compose.yml --project-directory . up -d --force-recreate landing
  ```

- `docker restart copiloto-landing-1` basta cuando solo cambia el contenido de `landing/`; para
  cambiar la variable de entorno hay que recrear el contenedor (el `restart` conserva el entorno).
- `NGINX_ENVSUBST_FILTER` limita `envsubst` a esas dos variables: las de Nginx (`$uri`,
  `$request_uri`, `$host`…) quedan intactas en la plantilla.

`robots.txt` y `sitemap.xml` usan el mismo marcador, así que el sitemap siempre apunta al dominio
real. `sitemap.xml` lista solo `/` y `/demo`.

## Enlaces a servicios: `config.js`, no `localhost` fijo

El HTML público no escribe `http://localhost:PUERTO`. Los enlaces a la bandeja de Chatwoot, al PMS y
a métricas llevan `data-service` y `href="/demo"` de respaldo; `landing/site.js` los completa con
`window.COPILOTO_CONFIG` (`landing/config.js`, generado y gitignored por `scripts/seed-chatwoot.sh`):

```js
window.COPILOTO_CONFIG = {
  chatwootUrl, copilotoUrl, pmsUrl, websiteToken,
  privacyUrl: "/privacidad",
};
```

Sin `config.js` (por ejemplo un checkout recién clonado sin seed) `site.js` deriva las URLs del host
de la página con los puertos del stack (3000, 8100, 8200) y respeta la demo por LAN: si la página no
se abre en `localhost`, reescribe el host de la config al de la página, igual que `demo.js`. Sin
JavaScript los enlaces quedan en `/demo`, que también enlaza a esos paneles: nada se rompe.

El aviso de privacidad se sirve en la misma origen, `/privacidad`: Nginx lo pasa al copiloto
(`COPILOTO_UPSTREAM`) y conserva la CSP que envía el servicio. Así el enlace funciona igual en
`localhost`, en la LAN y detrás de un dominio.

## Caché, compresión y cabeceras (`infra/landing/nginx.conf`)

| Recurso | `Cache-Control` |
| --- | --- |
| HTML (`/`, `/demo`) | `no-cache` (siempre revalida) |
| `config.js` | `no-store` (lleva el token del widget) |
| `*.woff2` | `public, max-age=31536000, immutable` |
| `*.css`, `*.js`, `*.svg`, `*.png` pedidos con `?v=` | `public, max-age=31536000, immutable` |

- `gzip on` para HTML, CSS, JS, JSON, XML, `robots.txt`, `sitemap.xml` y SVG (`gzip_min_length 512`).
- Cabeceras en todas las respuestas: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: strict-origin-when-cross-origin` y
  `Permissions-Policy: camera=(), geolocation=(), microphone=(self), payment=(), usb=()` — el micrófono
  queda solo para esta origen porque la demo de voz lo pide.
- La política de caché se decide con un `map` sobre la URL y se emite con un único `add_header` en el
  `server`: no hay `add_header` repetidos por `location` que se olviden de heredar las cabeceras.
- Las fuentes usan `font-display: swap` y el HTML precarga las tres que pinta la primera vista
  (Instrument Serif normal e itálica, Inter); el resto llega con la página ya pintada.

## Cómo se comprueba

```bash
curl -sI http://localhost:8080/            # cabeceras y Cache-Control: no-cache
curl -s  http://localhost:8080/ | grep -E 'canonical|og:|twitter:|application/ld\+json'
curl -s  http://localhost:8080/robots.txt
curl -s  http://localhost:8080/sitemap.xml
curl -sI http://localhost:8080/demo.css?v=1   # Cache-Control immutable
curl -sI http://localhost:8080/fonts/inter-normal.woff2
curl -sI -H 'Accept-Encoding: gzip' http://localhost:8080/demo.css | grep -i content-encoding
curl -sI http://localhost:8080/privacidad      # proxy al copiloto, 200 con su CSP
```

En las respuestas del HTML, `robots.txt` y `sitemap.xml` no debe quedar ninguna aparición de
`__PUBLIC_SITE_URL__`: si queda, el contenedor no arrancó con la plantilla nueva
(`up -d --force-recreate landing`).

## Lo que queda fuera

- Sin build no hay hashing de assets: la caché larga depende del `?v=` que se cambia a mano en el HTML
  (`demo.css?v=…`, `site.js?v=…`). Un archivo sin `?v=` se sirve con `no-cache`.
- `og-image.png` es estático (1200×630). Si cambia el mensaje de la portada, se regenera aparte.
- La portada se sirve solo por HTTP en local: `https`, HSTS y una CSP estricta son tareas del reverse
  proxy del despliegue real, no de este contenedor.
