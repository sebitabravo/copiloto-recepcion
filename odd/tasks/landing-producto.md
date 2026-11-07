# Landing de producto · implementación

Estado: en ejecución · Rama: `refactor/ux-logic-cleanup` · Referencia visual: `design/landing-profesional/01-tour-producto.html`

## Specs

S1. Pedido del usuario, textual:
    "sii ahora lo que realizaste de cambas esta perfecto es lo que quiero dale porfavor realizalo y con
    calma mira que el miercoles tengo que mostrar el funcionamiento de esto por lo cual tengo que realizarlo"

S2. Se implementa en la landing real la dirección `01-tour-producto.html`: hero compuesto (huésped + cola en
    una sola pieza 3D), cifras con contexto, pipeline de cinco pasos, pantallas de recepción, "qué decide y
    qué no", CTA, ticker y brillo cálido.

S3. Se conserva el producto: privacidad antes de preguntar, ubicación primero, menú guiado 01/02/03,
    confirmación manual de la reserva, widget real de Chatwoot y demo de voz.

S4. Contrato del JavaScript intacto: todo id y selector que usan `landing/demo.js` y `landing/voice.js`
    sigue existiendo (lista en L3). Las tarjetas `[data-live]` conservan su `.live-button`.

S5. Accesibilidad y rendimiento: WCAG AA, `:focus-visible`, `aria-live`/`role`, `prefers-reduced-motion`,
    tipografías auto-hospedadas, sin CDN ni recursos externos.

S6. El miércoles se muestra en vivo: la página debe funcionar contra el stack levantado, sin errores de
    consola y sin desbordes entre 380 y 1440 px.

## Tasks

| ID | Alcance | Superficie | Specs | Commit |
| --- | --- | --- | --- | --- |
| T1 | Reestructurar `landing/index.html` (hero, cifras, ticker, pipeline, recepción, límites, CTA) | `landing/index.html` | S2 S3 S4 S5 | sí |
| T2 | Lenguaje visual nuevo en `landing/demo.css` y retiro del CSS de las secciones reemplazadas | `landing/demo.css` | S2 S5 | sí |
| T3 | Verificar: node, navegador, 6 anchos, demo funcional | — | S3 S6 | — |
| T4 | Documentar y commitear | `docs/`, `README.md` | S2 | sí |

## Log

L1 (usuario, original):
    "sii ahora lo que realizaste de cambas esta perfecto es lo que quiero dale porfavor realizalo y con
    calma mira que el miercoles tengo que mostrar el funcionamiento de esto por lo cual tengo que realizarlo"

L2 (decisión): se implementa la dirección 01 (tour de producto). Es la única de las tres con forma de
    landing completa; la 02 es un shell de aplicación y la 03 deja el demo detrás de un CTA.

L3 (contrato JS, inventario verificado con grep):
    IDs de `demo.js`: actions-panel, ai-disclaimer, assistant-announcement, cancel-scenario, capability,
    char-count, chat-error, chat-form, chat-status, connection-label, guided-banner, hero-stage,
    message-input, messages, messages-left, model-label, open-chat, privacy-link, rate-status, reset,
    response-time, scenario-status, scroll-progress, send, status-dot, status-error, timeline,
    timeline-empty, toggle-actions, topbar, typing.
    Selectores: `.hero-shell`, `.how-visual`, `.quick-replies`, `[data-live]` + `.live-button`/`.live-result`,
    `[data-scenario]` + `.scenario-label`, `.demo-grid`, `main > section:not(#demo)`.
    IDs de `voice.js`: voice-demo, voice-form, voice-hangup, voice-lang, voice-log, voice-start, voice-state,
    voice-support, voice-talk, voice-typed-input.
    `.how-visual` puede desaparecer (solo lo recorre un `querySelectorAll`), pero `[data-live]` debe
    conservar su botón.

L4 (usuario, nueva instrucción):
    "estaria bueno que la logica de la landing la hicieras como la de agrovoz
    https://github.com/sebitabravo/AgroVoz que el simulador pueda otra pagina mejor no que todo este en el
    mismo lado ya que asi se ve mas ordenado y tiene sentido el boton de probar demo"

L5 (referencia verificada): AgroVoz separa `landing/src/pages/index.astro` (marketing) de
    `landing/src/pages/demo.astro` (simulador dedicado), con el CTA de la portada apuntando a `/demo`
    (`index.astro:363`) y una página `privacidad.astro`. Se adopta el mismo patrón.

T5-T7: `index.html` queda como landing de marketing (hero compuesto, cifras, ticker, recorrido, recepción,
    límites, CTA "Probar la demo" → `/demo`); `demo.html` concentra el simulador, la traza, los guiones, la
    voz, las tarjetas en vivo y el canal real de Chatwoot, con todos los ids del contrato L3. `site.js`
    aporta solo el chrome de la landing; `demo.js`/`voice.js` se cargan únicamente en `demo.html`.
    `infra/landing/nginx.conf` resuelve `/demo` y no cachea HTML.

L6 (usuario, nueva instrucción):
    "y asi se tiene en esa vista el acceso a todas las funcionalidades y el usuario no tiene que estar
    entrando a rutas y cosas raras ya que asi llega a prueba nomas las cosas como si de whassap se tratara y
    se ve la perspectiva tanto del cleinte como la del genrente del hotel y la del admin"

L7 (alcance derivado): `demo.html` deja de ser solo el simulador y pasa a ser una consola de demo con tres
    perspectivas en la misma vista, conmutables por tabs, sin rutas intermedias:
    - Huésped: el simulador tipo WhatsApp que ya existe (vivo).
    - Recepción (gerente): cola con tiempos y riesgo de SLA + detalle de la conversación, leídos de
      `/api/panel/*` con el token del panel inyectado por el seed en `config.js` (el mismo token que ya viaja
      en la URL del Dashboard App). Solo lectura: la confirmación sigue siendo humana.
    - Admin: PMS simulado embebido (listado de habitaciones) y métricas del piloto, más enlaces directos.
    El token de personal del PMS NO se expone en el navegador: confirmar una reserva sigue pidiéndolo.

L8 (usuario, nueva instrucción):
    "yo como senior siento que es muy mala practica en un mockup o demo tener crenciales y esas cosas ya que
    le estas impidiendo al usuario investigar de ultima hay que crear un boton que se pueda desactivar que
    diga algo de modo demo y que te ponga credenciales y cosas por defecto que sean parte de la demo"

L9 (decisión de diseño, sin credenciales en el navegador):
    - `POST /api/demo/session` (copiloto): con `DEMO_ENABLED` activo, crea la sesión firmada del panel con un
      nombre demo y responde 204 con la cookie; con la demo apagada responde 403. Nunca devuelve el token.
    - `GET /api/demo/session`: informa `{demo, name}` para que la página sepa si el modo demo está disponible.
    - `pms_mock`: con `DEMO_MODE` activo, `GET /admin?demo=1` deja una cookie de personal válida y redirige a
      `/admin`; las rutas que hoy exigen el token también aceptan esa cookie. Con la demo apagada, 404.
    - `landing/demo.html`: conmutador visible "Modo demo" (por defecto encendido, persistido en
      `localStorage`), con aviso de que los datos son ficticios y las credenciales automáticas. Al apagarlo,
      no se crea sesión ni se ofrecen accesos automáticos.
    - La consola de demo (L7) usa esas dos vías: pestaña Recepción con la sesión demo, pestaña Admin con el
      PMS en modo demo. Sin tokens en JS ni en `config.js`.

L10 (usuario, revisión de diseño):
    "revisa el diseno de la demo ... no respeta el diseno estricto y bien elaborado de un disenador grafico y
    alguien experto en ux/ui ya que hay cosas que estan muy juntas no tienen sentido y se ve feo"
    "el celular no se parece al diseno que tiene whassap la idea es que sea el simulador de un whassap
    tambien la idea es tener el boton de llamada ya que tenemos la opcion de que se pueda llamar al bot y que
    te hable en vez de solo escribirle entonces esa funcionalidad igual hay que dejarla bien y fina"

L11 (diagnóstico medido, 1440 px):
    - El hero compacto y la sección `#demo` repiten título (dos h2 para lo mismo) y entre las pestañas y el
      teléfono hay 240 px de texto (heading 86 + intro 101 + aviso 54).
    - `.demo-grid` es de una columna de 520 px con `#actions-panel` oculto: el teléfono queda centrado en un
      card de 1.062 px con 271 px vacíos a cada lado, y la traza de herramientas (lo mejor del producto) no
      se ve sin hacer clic.
    - El bloque de guiones (235 px) y la tarjeta de voz son secciones apiladas más, con su propio eyebrow/h3.
    - El teléfono no imita WhatsApp: sin iconos de llamada/video/menú, sin colita en las burbujas, sin
      separador de día, composer sin emoji/adjuntar/cámara.
L12 (decisión de diseño):
    - Consola de dos columnas en escritorio: teléfono 340-400 px + acciones visibles por defecto; una sola
      franja compacta de título, sin intro larga.
    - Piel WhatsApp fiel con los tokens `--wa-*` ya existentes (cabecera 56 px con avatar, estado y acciones;
      burbujas con colita y marcas; separador HOY; composer con emoji, adjuntar, cámara y botón verde).
    - **Llamada dentro del teléfono**: el icono de llamada abre una pantalla de llamada (fondo oscuro, avatar,
      estado, cronómetro, transcripción y colgar) que usa el flujo de voz existente. Si el navegador no
      soporta reconocimiento, la misma pantalla ofrece el modo escrito. Sin audio real en la demo de escritorio,
      la pantalla debe verse y funcionar igual.
