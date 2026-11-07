# Loop UX/UI, SEO y agente local · Copiloto de Recepción

Dueño: sesión autónoma nocturna (el usuario duerme y pidió no preguntar) · Rama: `refactor/ux-logic-cleanup`
Referencias: https://github.com/sebitabravo/agents-wa/tree/main/docs · https://github.com/sebitabravo/AgroVoz

## Specs

S1. Pedido del usuario, textual:
    "mira quiero que realices un loop dee ux/ui de mi proyecto ya que quiero que revices todas las vistas
    utilices todas las accione y quiero que el loop consista en primeor una auditoria para ver como es que
    funciona al 100% la aplicaicon y ver todas las cosas, desoues de hacer click y probar todo lo probable que
    arregles los problemas de desing que tiene el proyecto ya que siento que no es un proyecto digno de un
    senior developer como yo que le gusta las paginas bien optimizadas con un buen seo, despues del loop de
    desing quiero que realices otro loop que es de optimizacion quiero que investigues porfavor si es que
    tengo todo bien si es que tengo el mejor agente local optimizado si es que esta bien configuraco par ale
    fin que lo quiero y tambien si es que responde como un humano ya que mira yo me gui segun las ideas de
    nexoria que es que la ia sea como un humano o que se sienta como uno entonces mira yo cree antiguamente
    agrovoz quiero que lo vea y lo analises y tambien tengo una guia para estas cosas entronces quuiero que
    realices todos loop porfavor ya que ahora me voy a dormir entonces no quuiero que me preguntes nada solo
    investiga en interent ve si realmente esta bien y realiza todo lo que tengas que realizar te dpoy permiso.
    estos son los proyectos de referencia que te voy "https://github.com/sebitabravo/agents-wa/tree/main/docs"
    "https://github.com/sebitabravo/AgroVoz". mira que necesito que quede funcionando perfecto esto ahora ya
    para cuando despierte tiene que estar todo listo."

S2. Loop 1 · auditoría: recorrer en el navegador TODAS las vistas del stack levantado (portada `/`,
    consola `/demo` con sus pestañas, privacidad, panel `/panel`, métricas `/metricas`, PMS `/admin`, widget
    real) y usar TODAS las acciones visibles, en escritorio y móvil, registrando errores de consola,
    desbordes y problemas de diseño con evidencia.

S3. Loop 1 · arreglos de diseño: corregir los problemas de diseño hallados en S2 con el sistema de diseño
    del proyecto (`design/system.md`), sin romper el contrato de ids/selectores de `landing/demo.js` y
    `landing/voice.js` ni el producto (privacidad antes de preguntar, ubicación primero, menú 01/02/03,
    confirmación humana de la reserva).

S4. "paginas bien optimizadas con un buen seo": metadatos, Open Graph, datos estructurados, `robots.txt`,
    `sitemap.xml`, canónicos, `noindex` en las vistas internas, rendimiento (fuentes, imágenes, caché,
    compresión) y accesibilidad medidos antes y después.

S5. Loop 2 · optimización del agente local: investigar en internet si el modelo local, su runtime y su
    configuración son los mejores para el fin (recepción de hotel en español, herramientas, hardware de
    este equipo: RTX 5060 8 GB) y aplicar lo que mejore con evidencia medida.

S6. "si es que responde como un humano": contrastar el agente con la guía de `agents-wa/docs` y con
    AgroVoz (ideas de Nexoria: que la IA se sienta humana) y ajustar prompt, tono y comportamiento con
    evaluación antes/después.

S7. "necesito que quede funcionando perfecto": al cerrar, tests, tests de UI, e2e y recorrido en navegador
    en verde contra el stack levantado; sin preguntar al usuario (autorizado a decidir).

## Tasks

| ID | Alcance | Ruta | Specs | Commit |
| --- | --- | --- | --- | --- |
| T1 | Auditoría en navegador de todas las vistas y acciones | padre (Playwright) | S2 | — |
| T2 | Investigar referencias: guía `agents-wa/docs` y AgroVoz | explore (web) | S6 | — |
| T3 | Investigar modelo/runtime local óptimo para RTX 5060 8 GB | explore (web) | S5 | — |
| T4 | Mapa del agente actual (prompts, herramientas, config, latencias) | explore (local) | S5 S6 | — |
| T5 | Portada: diseño (L6) + SEO/rendimiento (C4, C5) + nginx | worker W1 | S3 S4 | L11 |
| T5b | Consola `/demo`: diseño (L6, L7) + C1 C2 C3 + SEO de `demo.html` | worker W2 | S3 S4 | L12 |
| T6 | Panel, métricas, privacidad y PMS: diseño (L7) + C3 + noindex | worker W3 | S3 S4 | L13 |
| T7 | Imagen OG y medición de rendimiento antes/después | padre | S4 | L9 L11 |
| T8 | Optimizar runtime/modelo local (GPU, modelo, flags) con evaluación | padre | S5 | L10 |
| T9 | Humanizar el agente (guía L5) + C1 C2 + evaluación de tono | worker W4 | S6 | L14 |
| T10 | Verificación final y documentación | padre | S7 | L15 |

## Log

L1 (usuario, original): ver S1.

L2 (evidencia inicial): stack levantado (copiloto, pms-mock, llm, chatwoot, sidekiq, landing, postgres,
    redis). El contenedor `llm` usa `ghcr.io/ggml-org/llama.cpp:server` (imagen CPU) con
    `Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M`, `-c 8192 -t 8`, sin GPU, aunque el equipo tiene una
    NVIDIA GeForce RTX 5060 de 8151 MiB.

L3 (T3, investigación web): recomendado `unsloth/Qwen3.5-4B-GGUF:UD-Q4_K_XL` en
    `ghcr.io/ggml-org/llama.cpp:server-cuda` (CUDA 12.8, requerido por Blackwell sm_120), no-thinking
    (`--chat-template-kwargs '{"enable_thinking":false}'`), `-ngl 99`, `--jinja`, sampling de la model card
    no-thinking `temp 0.7, top_p 0.8, top_k 20, min_p 0, presence_penalty 1.5`. Alternativa:
    `unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M`. Fuentes: https://unsloth.ai/docs/models/qwen3.5,
    https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507, llama.cpp `docs/docker.md`, issue #20809
    (tool calls en `reasoning_content` en builds viejos), https://docs.docker.com/compose/how-tos/gpu-support/.
    Sin benchmark de español: decide la evaluación local (`scripts/model_eval.py`).

L4 (T4, mapa del agente): prompt en `copiloto/src/copiloto/ai/prompts.py:11` (v2026-11.1); bucle en
    `ai/agent.py` (MAX_STEPS 5, MAX_REPLY 1200, temperature 0.3 fija en `ai/llm.py:52`, sin top_p/top_k);
    una burbuja por respuesta en demo y Chatwoot, sin división ni retardo humano; plantillas fijas que
    suenan a sistema (`agent.py` SAFE_*/STUCK/propuesta, `flow.py:306-316` saludo, `flow.py:842`);
    prompt empuja a listas (`prompts.py:18,39`). `scripts/model_eval.py`: 12 casos, sin métrica de tono
    ni longitud, `PROMPT_MARKERS` con "MODO DEMO AUTÓNOMO" inexistente, default de modelo 7B desalineado
    con el 3B servido. Docs con tres verdades distintas (`docs/ia.md`, `docs/ia-local.md`, compose).

L5 (T2, guía y AgroVoz): la guía `agents-wa/docs` no menciona Nexoria ni pide ocultar la IA; sí exige
    longitud explícita (2 a 4 frases según canal, `03-system-prompts.md`), texto plano por defecto, "Derivar
    sin prometer llamada posterior", frase fija para dato ausente, identidad honesta si preguntan
    ("Sí, soy AgroVoz, un asistente de inteligencia artificial…"), "No incluya personalidad extensa",
    p95 texto < 5 s (`06-canales-memoria.md` R5) y evaluación con rúbrica pass/fail por criterio
    (`07-evaluacion.md:160`). AgroVoz (`backend/app/services/prompt_builder.py:42`): "Haz como máximo una
    pregunta por turno", "No uses entusiasmo automático ni empatía vacía", "No termines siempre con una
    pregunta", máximo 2-3 oraciones; SEO en `landing/src/layouts/Base.astro:15-49` (canonical, OG, twitter,
    theme-color, `og:locale=es_CL`) y `noindex` en admin.

L6 (T1, auditoría parcial, 1440 y 390 px, consola sin errores):
    Portada `/`: sin OG/twitter/canonical/JSON-LD/theme-color/robots/sitemap, favicon solo data-URI; enlaces
    absolutos a `http://localhost:3000|8200|8100` (pie y sección recepción, incluido el aviso de privacidad);
    cifras de relleno ("4 herramientas", "1", "0", "100% datos ficticios"); banda de `#recepcion` con fondo
    desalineado (ni a sangre ni al contenedor, x=123..1303 a 1440); ritmo vertical irregular (hr + padding
    doble antes de `#limites` y del CTA). Móvil 390: chip `get_hotel_info · 31 ms` tapa la barra de URL del
    mock; cifras apiladas de a una (~900 px); página de 6792 px.
    Consola `/demo`: aviso de modo demo duplicado (franja superior + tarjeta "Demo con IA. Todo es
    ficticio"); "Escribir a recepción" + "Canal separado…" centrados y pegados al eyebrow "CONEXIONES EN
    VIVO" sin aire; botones de las tarjetas en vivo no alineados al pie; "Respuesta en — s"; chips de
    guiones con la 02 larga que deja la 03 sola. Saludo robótico ("Hola, soy el asistente de recepción con
    IA… no tengo permiso para crear reservas"). "¿tienen piscina?" → "Tienen una piscina temperada todo el
    año." (tercera persona, sin devolver el saludo, 4,74 s en CPU) y la respuesta rápida repite
    "¿Tienen piscina?" ya preguntada.
    Herramienta: las llamadas MCP de Playwright cortan a 60 s; esperar respuestas lentas en varias llamadas.

L7 (T1, auditoría completa; capturas en `.playwright-mcp/audit/`, consola del navegador sin errores):
    Guion 02 con el modelo 3B en CPU: lista numerada de 6 habitaciones con `**negrita**` Markdown literal en la
    burbuja, precios `$65,000` (coma, no formato chileno `$65.000`), ofrece "este fin de semana" antes de
    recibir fechas, lista habitaciones de 2 personas para "2 adultos y 1 niño". Voz: ~25 s en "Pensando…".
    Llamada: con reconocimiento no soportado, "Tocar para hablar" se parte en 3 líneas y tapa la nota
    "El navegador envía tu voz…"; pantalla saturada (cabecera, avatar, nombre, cronómetro, estado, aviso,
    transcripción, input, idioma, hablar, colgar, nota); saludo de voz de 4 frases.
    Pestaña Recepción: nombres aleatorios de Chatwoot (`cool-mountain-791`), esperas como `636:16` (minutos
    sin horas, ilegible; `/panel` sí dice `10h 38m`), filas idénticas sin resumen; detalle apretado ("Pre-reserva"
    pegado a "Notas privadas del turno", "← Volver a la cola" pegado al eyebrow, insignia SLA minúscula).
    Pestaña Admin: el iframe del PMS usa otro sistema visual (sans del sistema, título negro en negrita); aviso
    "Confirmar una reserva es tarea humana…" más ancho que la columna de texto.
    Traza: la capacidad "Registra una reserva de demostración" aparece aunque el modo `assisted` no reserva.
    Móvil 390 `/demo`: cabecera en 2 filas + aviso (~170 px) antes de las pestañas.
    `/panel` (8100): columna de 450 px pegada a la izquierda fuera de Chatwoot. `/metricas`: eventos con claves
    crudas (`ai_booking`, `ai_fallback`), 6 tarjetas en rejilla de 4 con 2 huecos, "Costo por consulta $783 CLP"
    con modelo local. `/privacidad`: sin marca ni regreso a la portada, columna a la izquierda. PMS `/admin`:
    otro sistema visual. Ninguna vista interna tiene `noindex`.

L8 (decisiones y contratos entre unidades, el usuario autorizó decidir sin preguntar):
    C1. Burbujas humanas: en las respuestas del agente, una línea en blanco (`\n\n`) separa ideas y el
        simulador la muestra como burbujas separadas (máximo 3) con el indicador de escritura entre ellas
        (pausa proporcional al largo, tope 1,2 s, sin pausa con `prefers-reduced-motion`). Chatwoot sigue
        recibiendo un solo mensaje (el widget muestra los párrafos).
    C2. Formato de chat: el servidor entrega texto plano sin Markdown (`**`, `#`, backticks) y montos en
        formato chileno (`$65.000`). El simulador escapa HTML y muestra `*texto*` como negrita, al estilo WhatsApp.
    C3. Nombres anónimos de Chatwoot con forma `palabra-palabra-123` se muestran como `Visitante web · 123` en la
        pestaña Recepción y en `/panel`; esperas ≥ 60 min como `10 h 38 min`.
    C4. SEO: la portada y `/demo` llevan canonical, Open Graph (`og:locale` `es_CL`, imagen `/og-image.png`
        1200×630), Twitter card, `theme-color`, JSON-LD y favicon SVG; `robots.txt` y `sitemap.xml` en la
        raíz; la URL pública sale de una variable (`PUBLIC_SITE_URL`, por defecto `http://localhost:8080`).
        Las vistas internas (`/panel`, `/metricas`, PMS `/admin`) llevan `noindex, nofollow`.
    C5. Sin `http://localhost:*` escrito en el HTML público: los enlaces a servicios salen de `config.js`; el
        aviso de privacidad se sirve en la misma origen `/privacidad`.

L9 (T7/T8, mediciones antes de los cambios):
    Rendimiento (390 px, caché caliente): `/` LCP 132 ms, CLS 0, 7 peticiones, 148 KB decodificados;
    `/demo` LCP 388 ms, CLS 0,041, 14 peticiones, 108 KB. gzip ya activo (`/` 14,4 KB → 4,2 KB;
    `demo.css` 56,5 KB → 12,2 KB). OG generada: `landing/og-image.png` 1200×630, 119 KB, fuente
    `design/og-image.html`.
    Modelo (`scripts/model_eval.py` de HEAD, 12 casos, `ai_mode=full`, tope por turno 12 s):
    - `qwen2.5-3b-instruct` Q4_K_M en CPU (actual): 10/12, p50 12,0 s, p95 12,02 s; casi todos los casos
      chocan con el tope de 12 s (los «aprobados» de seguridad pasan porque no ocurre nada); falla
      herramienta de hotel y confirmación explícita.
    - `Qwen3.5-4B UD-Q4_K_XL` en GPU (`server-cuda` b12169, `-ngl 99`, no-thinking): 10/12, p50 2,22 s,
      p95 9,01 s; los dos fallos son `http 500` del servidor (herramienta de hotel, argumentos de
      disponibilidad), no del modelo.
    GPU visible en Docker: `CUDA0: NVIDIA GeForce RTX 5060 (8123 MiB)`.
    - `Qwen3-4B-Instruct-2507 Q4_K_M` en GPU: 11/12, p50 1,53 s, p95 5,67 s, 30–100 tokens/s de
      generación; falla solo «confirmación explícita» (el modelo escribe su propio resumen sin llamar
      `create_booking(guest_confirmed=false)`, el huésped debe decir «sí» dos veces).
    Causa verificada del `http 500` de Qwen3.5: `Jinja Exception: System message must be at the beginning.`
    (`ai/agent.py` inyecta mensajes `system` a mitad de la conversación). Enviado a W4 junto con el resumen
    duplicado y el saludo «inteligencia artificial de un tercero», falso con el modelo local.

L10 (T8, decisión aplicada): `infra/docker-compose.ia.yml` sirve `unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M`
    (alias `qwen3-4b-instruct-2507`) en `ghcr.io/ggml-org/llama.cpp:server-cuda-b12169` con `-ngl 99 -c 8192
    --parallel 1 --jinja --reasoning off --cache-reuse 256 --top-k 20 --top-p 0.8 --min-p 0` y reserva de GPU;
    `infra/docker-compose.ia-cpu.yml` (nuevo) es la variante sin GPU (`server-b12169`, `deploy: !reset null`,
    `-t 8`, topes 120/90 s). `scripts/demo.sh ia` detecta `CUDA0` y elige; `LLM_GPU=0` fuerza CPU.
    `scripts/preflight.sh` usa `demo.sh ia` cuando no hay `llama-server` en el host. `scripts/local-model.sh`
    y `docs/ia-local.md` reescritos con el mismo modelo, la tabla de evaluación y las fuentes. Stack en vivo:
    `/api/demo/status` → `"model":"qwen3-4b-instruct-2507"`, VRAM 5,8 GB de 8.

L11 (T5, portada; verificado en navegador 1440/390, consola sin errores): cifras con hechos verificables
    (180 s de respuesta humana, 12 tipos de habitación, 11 respuestas frecuentes con fuente, $0 en licencias),
    rejilla 2×2 en móvil, banda de `#recepcion` a sangre con contenedor interno, ritmo vertical único, chip de
    la traza sin tapar la barra del mock (el mock ganó barra de navegador). SEO completo: canónico, Open Graph
    (`es_CL`, `/og-image.png`), Twitter, `theme-color`, JSON-LD `WebSite`+`SoftwareApplication`, `favicon.svg`,
    `robots.txt`, `sitemap.xml`; URL pública por `PUBLIC_SITE_URL` (sub_filter de nginx). Enlaces de servicio
    pasan por `config.js` (`data-service`), aviso de privacidad en la misma origen vía proxy `/privacidad`.
    `nginx`: gzip, caché inmutable para fuentes y assets con `?v=`, sin caché para HTML/config, cabeceras
    `nosniff`, `Referrer-Policy` y `Permissions-Policy` con `microphone=(self)`.

L12 (T5b, consola; verificado en navegador): un solo aviso de modo demo; la privacidad pasa a nota del
    historial; "Escribir a recepción" es sección propia con botón alineado; botones de tarjetas en vivo al pie;
    "Respuesta en" oculta hasta medir (medido: 0,97 s con GPU); chips de guiones en una fila; capacidad de
    reserva solo en modo `full`; móvil con cabecera de 63 px. Pantalla de llamada con cabecera de 3 columnas,
    controles en una fila y "Tocar para hablar" que conserva el icono. Recepción con resumen por riesgo
    ("40 conversaciones · 20 vencidas"), `Visitante web · 791` y `11 h 30 min`. Burbujas: respuesta dividida por
    línea en blanco, máximo 3, indicador entre ellas, pausa con tope 1,2 s y sin pausa con
    `prefers-reduced-motion`; `*texto*` en negrita sin interpretar HTML. `node --test`: 25/25 (10 pruebas nuevas
    con RED observado sobre la base).

L13 (T6, vistas internas; verificado en navegador y con curl): `/panel` centrado y de dos columnas fuera de
    Chatwoot, compacto dentro del iframe; `/metricas` con etiquetas en español y la clave técnica al lado,
    rejilla sin huecos y explicación del costo (el $783 CLP es correcto por diseño: 90.000 fijos ÷ 115
    consultas); `/privacidad` con marca, columna de 720 px y vuelta a la portada con `LANDING_ORIGIN`
    (antes `/` daba 404 en :8100); PMS `/admin` con tokens, Instrument Serif e Inter servidas por el propio
    PMS. `noindex, nofollow` como meta y cabecera `X-Robots-Tag` en `/panel`, `/metricas`, `/api/*` y `/admin`;
    `/privacidad` y `/health` sin la cabecera. Pruebas nuevas con RED observado (8 y 3 fallos); `pms_mock`
    47 y las 85 de la superficie en verde.

L14 (T9, agente; verificado con el modelo real): prompt v2026-11.2 con primera persona plural, una pregunta por
    turno, sin entusiasmo automático, frase fija para el dato ausente, identidad honesta y respuesta de la
    herramienta respetada tal cual (sin reescribir en tercera persona). Post-proceso del servidor: sin
    Markdown, montos `$65.000`, máximo 3 bloques. Plantillas del servidor reescritas sin jerga de sistema y
    saludo de voz con "Toca el botón" en vez de "Mantén presionado". Se corrigió el bug de los mensajes `system`
    a mitad de conversación (rompía la plantilla de Qwen3.5); ahora el modelo local es Qwen3-4B-Instruct-2507 y
    `LLM_TEMPERATURE=0.2` en el perfil de IA. `scripts/model_eval.py`: marcadores reales, `--mode`,
    métricas de tono y 4 casos nuevos. Evaluación final: **100 % (14/14), p50 0,84 s, p95 5,59 s**; la pregunta
    de la piscina responde en primera persona 4 de 4 veces.

L15 (T10, verificación final): `copiloto` 403 pruebas, `pms_mock` 47, `node --test` 25/25,
    `ruff` limpio en los cinco paquetes, `scripts/e2e.py` 39 PASS sin fallos, navegador 1440 y 390 sin
    errores de consola ni desbordes en `/`, `/demo` (tres pestañas y llamada), `/panel`, `/metricas`,
    `/privacidad` y PMS. Capturas de `docs/img` regeneradas con el diseño nuevo. Commits por unidad de trabajo
    en `refactor/ux-logic-cleanup`.
