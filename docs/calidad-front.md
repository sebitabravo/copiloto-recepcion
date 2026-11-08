# Calidad del front · medición y presupuesto

Medido el 2026-11-06 con Lighthouse 12 sobre Chrome headless en `localhost`, preset de escritorio.
Se repite antes de cada entrega; un cambio que rompa el presupuesto no se entrega.

## Última medición

| Página | Performance | Accesibilidad | Buenas prácticas | SEO |
| --- | --- | --- | --- | --- |
| `/` portada | **100** | **100** | **100** | **100** |
| `/demo` consola | **99** | **100** | **100** | **100** |

Métricas de carga (portada / consola):

| Métrica | Portada | Consola | Presupuesto |
| --- | --- | --- | --- |
| First Contentful Paint | 1,2 s | 1,2 s | < 2,0 s |
| Largest Contentful Paint | 1,7 s | 2,0 s | < 2,5 s |
| Total Blocking Time | 0 ms | 90 ms | < 200 ms |
| Cumulative Layout Shift | 0 | 0,047 | < 0,1 |
| Speed Index | 1,2 s | 1,2 s | < 2,5 s |

Medición posterior al rediseño del simulador (piel WhatsApp y llamada dentro del teléfono); la
accesibilidad volvió a 100 al corregir el contraste de la cabecera y de la traza.

Oportunidad abierta (portada): 244 ms de CSS bloqueante. Es el costo de servir una hoja sin build; se
resuelve en la fase 2 del ADR (`docs/adr/0001-front-estatico.md`), no antes de la entrega.

## Portada: qué cambió en esta pasada

- **Cifras verificables en vez de relleno.** La franja de datos ya no dice "4 herramientas / 1 / 0 /
  100% datos ficticios": muestra el SLA de 180 s con cronómetro (`copiloto/src/copiloto/config.py`,
  `sla_red_s=180`, ámbar a los 120 s), los 12 tipos de habitación y 20 habitaciones del PMS simulado
  (`data/hotel.yaml`, `pms_mock/tests/test_pms.py`), las 11 respuestas frecuentes verificadas, cada una
  con fuente y fecha de revisión (`data/hotel.yaml`) y el costo $0 en licencias
  (`docs/stack-abierto.md`). En móvil la rejilla es 2 × 2 en vez de una cifra por pantalla.
- **Banda de `#recepcion` a sangre.** El fondo llega a los bordes de la ventana con `border-image`
  (sin `margin-inline` negativo, que era lo que desalineaba la banda) y el contenido sigue alineado al
  contenedor. El bronce del *eyebrow* se oscurece un punto sobre `--bg-2` para no bajar de AA.
- **Ritmo vertical con un solo token** (`--section-space`). Se fueron los filetes entre secciones —que
  duplicaban la pausa— y el relleno doble antes de `#limites` y del CTA.
- **Móvil 390 px:** el chip `get_hotel_info · 31 ms` se apoya sobre el marco en vez de tapar la barra de
  dirección del mock; de 360 a 1440 px no hay desborde horizontal.
- **Rendimiento:** `font-display: swap` en las tres fuentes (antes `optional`, que dejaba el serif
  fuera si llegaba tarde) y precarga de las tres que pinta la primera vista. Caché larga e inmutable
  para fuentes y recursos con `?v=`, `no-cache` para HTML y `no-store` para `config.js`; gzip para
  texto y cabeceras de seguridad con `Permissions-Policy: microphone=(self)`.
- **SEO:** canonical, Open Graph, Twitter card, `theme-color`, JSON-LD, favicon SVG, `robots.txt` y
  `sitemap.xml`; URL pública en `PUBLIC_SITE_URL`. Detalle y comprobaciones en `docs/seo.md`.
- **Sin `localhost` en el HTML público:** los enlaces a bandeja, PMS y métricas salen de `config.js`
  (`landing/site.js`) con respaldo a `/demo`; el aviso de privacidad vive en la misma origen
  (`/privacidad`, proxied por Nginx al copiloto).

Accesibilidad y navegación comprobadas después del cambio: `:focus-visible` con anillo de 3 px, áreas
táctiles de 44 px en navegación y botones, `prefers-reduced-motion` desactiva animaciones y revelado, y
la consola del navegador queda sin errores en 360, 390, 768, 1000 y 1440 px.

## Presupuesto

| Área | Umbral | Por qué |
| --- | --- | --- |
| Accesibilidad | **100**, cero violaciones | Es una demo pública con formularios y pestañas; 100 es alcanzable y no admite excusas |
| Performance | ≥ 90 | Debajo de 90 hay bloqueo perceptible en un proyector o un equipo modesto |
| Buenas prácticas | ≥ 95 | HTTPS/CSP no aplican en local, pero consola limpia y sin errores sí |
| SEO | ≥ 90 | La portada es una página de producto |
| LCP | < 2,5 s | Umbral de Web Vitals "bueno" |
| CLS | < 0,1 | Evita saltos al cargar tipografías |
| TBT | < 200 ms | Interacción fluida en la demo |
| Peso sin comprimir | HTML ≤ 40 KB · CSS ≤ 130 KB · JS ≤ 80 KB | Se sirve sin build: el tamaño se controla a mano |
| Recursos externos | **0** | Sin CDNs, sin fuentes remotas, sin analítica |

## Cómo se mide

```bash
export CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
npx --yes lighthouse@12 http://localhost:8080 \
  --only-categories=performance,accessibility,best-practices,seo \
  --chrome-flags="--headless=new --no-sandbox --disable-gpu" \
  --output=json --output-path=.playwright-mcp/lh-landing.json --quiet
```

Repetir con `http://localhost:8080/demo`. El JSON crudo queda en `.playwright-mcp/` (ignorado por git).

## Comprobaciones funcionales que acompañan

No las cubre Lighthouse y se hacen en el navegador antes de una entrega:

1. Portada: el CTA "Probar la demo" navega a `/demo`; sin errores de consola.
2. Consola, pestaña Huésped: escribir "hola" devuelve aviso de privacidad y ubicación.
3. Consola, pestaña Recepción: con el modo demo encendido carga la cola real; apagado, muestra el camino manual.
4. Consola, pestaña Admin: el PMS entra con `?demo=1` sin pedir token; métricas abre.
5. Sin desbordes horizontales entre 360 y 1440 px, y objetivos táctiles ≥ 44 px en la consola
   (medido: 0 desbordes y 0 objetivos pequeños en 360/390/768/1000/1440).
6. `prefers-reduced-motion`: sin animaciones.

## Deuda declarada

- Sin build: no hay hashing de assets. Las fuentes y los recursos con `?v=` se cachean un año; el HTML
  no se cachea. Cambiar un CSS obliga a subir el `?v=` del HTML a mano.
- `landing/demo.css` concentra portada y consola; la fase 2 lo divide por página.
- Sin presupuesto automatizado en CI: hoy es una comprobación manual documentada aquí.
