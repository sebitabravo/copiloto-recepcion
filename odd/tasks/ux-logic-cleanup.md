# UX, lógica y código muerto · Copiloto de Recepción

Dueño: sesión única (auditoría) · Rama: `refactor/ux-logic-cleanup` · Estado: en ejecución

## Specs

S1. Pedido del usuario, textual:
    "mira siento que la ux/ui y la logica de programacion esta rara y hay mucho dead code
    entonces necesito que invesitugues eso y que lo dejes todo bien porfavor"

S2. "Dejes todo bien" = cada hallazgo auditado queda (a) corregido con test cuando cambia
    comportamiento, o (b) diferido por escrito con motivo. No se acepta un hallazgo sin destino.

S3. Se preserva el comportamiento documentado y ya validado end-to-end:
    privacidad antes de preguntar, ubicación primero, menú guiado 01/02/03, propuesta de reserva
    con confirmación manual y `e2e` en verde. Nada de rediseñar el flujo del producto.

S4. Código muerto se elimina solo cuando es certero (0 referencias comprobadas con grep en todo
    el repositorio, tests incluidos). Si hay duda, se deja y se reporta.

S5. Sin dependencias nuevas de runtime, sin servicios externos nuevos, sin cambios de contrato
    público (rutas HTTP, formato de `.env.runtime`, variables de entorno documentadas).

S6. Este equipo es Windows con Git Bash: los scripts del repositorio deben poder ejecutarse ahí
    (rutas MSYS, `sed` GNU, `python` en vez de `python3`, `tzdata`, encoding de stdout).

## Tasks

| ID | Alcance | Superficie | Specs | Commit |
| --- | --- | --- | --- | --- |
| T1 | Bugs de lógica del servicio `copiloto` + duplicaciones y muerto | `copiloto/src/`, `copiloto/tests/` | S1 S2 S3 S4 | sí |
| T2 | UX/UI, accesibilidad y CSS muerto de la landing | `landing/`, `infra/landing/` | S1 S2 S3 S4 | sí |
| T3 | Bugs de `pms_mock`, `pms_bridge`, `wa_bridge` + tests portables | `pms_mock/`, `pms_bridge/`, `wa_bridge/` | S1 S2 S3 S4 S6 | sí |
| T4 | Portabilidad de scripts, Makefile, seed, CI y config muerta | `scripts/`, `Makefile`, `infra/bootstrap/`, `infra/docker-compose.yml`, `.github/workflows/ci.yml` | S1 S2 S4 S6 | sí |
| T5 | Sincronizar documentación con el comportamiento corregido | `docs/`, `README.md` | S2 S5 | sí |
| T6 | Verificación final: tests, ruff, e2e, navegador, smoke | — | S2 S3 | — |

## Log

L1 (usuario, original):
    "mira siento que la ux/ui y la logica de programacion esta rara y hay mucho dead code
    entonces necesito que invesitugues eso y que lo dejes todo bien porfavor"

L2 (evidencia, tres auditorías read-only con `path:line`):
    copiloto: menú FAQ opción "10 Volver al menú" inalcanzable (`flow.py:243-250,365-372`); "si" sin
    tilde no confirma reserva (`ai/tools.py:22-29`); limitador de tasa crece sin límite
    (`ratelimit.py:20-28`); `DEMO_ENABLED` con verdad difusa (`config.py:115`); contador de tope IA no
    persistido (`flow.py:712-718`); `/api/demo/status.mode` contradice al agente inyectado
    (`app.py:404`); retención duplicada (`app.py:134` vs `privacy.py:107`); regla de estadía duplicada
    (`ai/tools.py:18,235` vs `flow.py:388-460`); clave de métrica con 180 fijo (`metrics.py:52,72`);
    `PREBOOKING_MINUTES` documentada y no cableada; docstring de eventos desalineado (`events.py:9-27`);
    muerto: `ai/sessions.py:8 SESSION_ID`, `store.py contact_ref`; duplicados `_read_label`, `money`,
    `plural`, `LOCAL_HOSTS`.
    landing: enlace de privacidad absoluto a `localhost:8100` (`index.html:332`) sin ruta en nginx;
    `#ai-disclaimer` oculto cuando falla `/api/demo/status` (`demo.js:222-231`); la etiqueta 02 pierde
    su número (`demo.js:211`); promesa rechazada cacheada del SDK (`demo.js:550-568`); estado de chat
    colgado (`demo.js:576-584`); `catch` silencioso (`demo.js:546`); jerga `make up` en copy público;
    `setInterval` sin limpiar (`demo.js:148`); composer deshabilitado durante la animación
    (`demo.js:372-386`); `focus` forzado (`demo.js:416`); propuesta vencida con botón muerto
    (`demo.js:330-333`); `aria-live` faltante (`index.html:190,90`); `voice.js:167-170` sin guarda;
    contraste `--muted` < 4.5:1; "Borde Luz" vs "Bordeluz"; verbos repetidos para tres canales;
    CSS muerto: `--user/--user-ink`, `.phone-column > .text-button`, `.messages` 2 alturas muertas,
    `.demo-grid` 2 declaraciones muertas, media query duplicada, `.composer` 3 bloques, `.message-label`.
    servicios: `pms_bridge` crea `httpx.AsyncClient` por petición (`main.py:26`, `beds24.py:68`) y marca
    eterno un token estático (`beds24.py:67`); `SIMULATE_DOWN` no cubre escrituras (`pms_mock/main.py:202`);
    `wa_bridge` arranca con tokens vacíos (`config.py:42-44`), purga solo al inicio (`main.py:64`),
    descarta mensajes sin log (`bridge.py:197`); Makefile sale con error al cancelar (`:51,55`);
    `python3` ausente en Windows (`:80,83`); `bootstrap.sh` usa `sed -i ''` BSD (`:36`);
    `seed-chatwoot.sh` rompe por conversión MSYS (`:19`); `smoke-docker.sh` y `wa-e2e.sh` igual;
    `preflight.sh` con `/tmp` fijo; CI no corre `pms_bridge`/`wa_bridge` ni su lint;
    `seed.rb` exporta `CHATWOOT_INBOX_ID`/`CHATWOOT_BOT_ID` que nadie lee; `scripts/test-demo-ui.mjs` huérfano.

L3 (revisión estricta, misma sesión):
    RDD nativo no pudo completarse por un defecto del proveedor, no por permisos: el candidato completo
    (`main..HEAD`, 3294 líneas) fue rechazado con `lens_context_budget_exceeded`; dividido en 4 slices por
    commit en worktrees (rev-landing, rev-copiloto, rev-pms, rev-tooling). El slice de landing obtuvo
    consentimiento humano y 4 lentes, pero el relay devolvió cero texto dos veces:
    `nan/glm5.3-flash` (32.768 tokens, `stopReason=length`) y `nan/deepseek-v4-flash` (42.263 tokens,
    `stopReason=length`), ambos con `textChars: 0`. Verificador no disponible: no se reintenta más.
    Sustituto aplicado: dos revisores ciegos independientes (A/B) sobre `main...HEAD`, 18 hallazgos.
    Coincidentes y verificados por el padre: `landing/demo.js` pasaba la URL sin reescribir al SDK
    (`baseUrl`), y `_restart_session` reutilizaba la sesión de IA con el tope agotado. Aceptados además:
    foco tras respuesta rápida, solapamiento del trace, «propuesta vencida» al confirmar, `voice.js` sin
    resolver de host, `preflight` con modelo muerto, `make reset` no interactivo, `is_local_url` por
    subcadena, retención pisando `Settings` inyectado, cabeceras de nginx incompletas y alias de la
    métrica SLA. Diferidos con motivo: columna `contact_ref` (migración destructiva), cierre de clientes
    HTTP en `wa_bridge` (preexistente), CORS `127.0.0.1` vs `localhost` (configuración del servidor).
