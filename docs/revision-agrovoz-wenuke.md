# Revisión de AgroVoz y Wenuke

Revisión de solo lectura (sin ejecutar su código) de `sebitabravo/AgroVoz` (commit `3f71eb7`) y
`sebitabravo/Wenuke`, hecha para dos cosas: mejorar este proyecto con lo que ya resolvieron bien y dejarte la
lista de defectos reales de cada repo. Cada hallazgo se leyó en el código; los marcados «externo» dependen de
algo fuera del repo.

## Lo que se adoptó en este proyecto

| Origen | Qué se aplicó | Dónde |
|---|---|---|
| AgroVoz | Falla al arrancar si faltan secretos o son cortos (producción) y sal propia para seudónimos | `config.py`, `store.py`, `tests/test_config.py` |
| AgroVoz | Tope de tamaño del cuerpo antes de autenticar el webhook | `app.py` (`read_capped`) |
| AgroVoz | Contenedores sin root, sistema de archivos de solo lectura, `cap_drop: ALL`, `no-new-privileges` | `*/Dockerfile`, `infra/docker-compose.yml` |
| AgroVoz | Sondas `liveness` y `readiness` en `/health` | `app.py` |
| AgroVoz | Límite por IP sobre las rutas de lectura, sin confiar en `X-Forwarded-For` | `ratelimit.py` |
| AgroVoz y Wenuke | Cabeceras de seguridad, con `frame-ancestors` solo para Chatwoot (no `DENY`, que rompería el panel) | `app.py` |
| AgroVoz | CI con acciones fijadas por SHA, tests y ruff | `.github/workflows/ci.yml`, `ruff.toml` |
| AgroVoz | Datos mínimos: ya no se guarda el texto de los mensajes en los eventos | `flow.py` |
| Ambos | Comparar firmas en bytes (un valor no ASCII daba 500 en vez de 401) | `app.py` |
| Wenuke | Escrituras multi-sentencia en transacción; el test encontró además que el estado en memoria no se revertía | `store.transaction`, `flow._persist_handoff` |
| Revisión propia | Umbral del SLA en métricas configurable, locks por conversación sin fuga de memoria, etiquetas serializadas | `metrics.py`, `flow.py`, `chatwoot.py` |

No se copió: LLM, voz, caché de datos viejos para disponibilidad (vendería cupos que ya no existen), limitadores
en memoria, el volumen de documentación de gobierno.

## Defectos de AgroVoz

| # | Sev. | Dónde | Qué pasa | Arreglo mínimo |
|---|---|---|---|---|
| A-1 | Alta | `backend/app/services/audio_service.py:384-401`, `:491-513` | Si falla el TTS o el pipeline, el agricultor recibe el audio de saludo `hello.ogg` y ninguna respuesta de texto; una excepción deja silencio | Enviar `text_response` con `send_text` cuando no hay audio y un texto de disculpa en el `except`; no enviar `hello.ogg` como respuesta |
| A-2 | Media | `backend/app/api/panel.py:25`, `agronomist.py:30`, `core/security.py:79-83` | Los tokens de acceso van en la ruta o la query y quedan en los access logs; el docstring dice «un solo uso» pero no hay registro de uso | Mover a header o desactivar el access log en esas rutas; implementar un solo uso real o corregir la documentación |
| A-3 | Media | `core/security.py:214-264`, `main.py:596` | El límite global de 60 req/min por IP también corta el webhook: todos los agricultores comparten el cupo | Excluir `/api/v1/webhook/whatsapp` del limitador |
| A-4 | Media | `schemas/webhook.py:117-126`, `services/audio_service.py:305` | Open-WA manda `idempotencyKey` pero nada la lee: un reenvío repite Whisper, LLM, TTS y la respuesta | Tabla con clave única para `idempotencyKey` antes de encolar |
| A-5 | Media | `config.py:40,52,119,173` | Con `APP_ENV` sin definir quedan activos los secretos por defecto públicos (webhook, admin, pepper) | Que el default sea `production` o negarse a arrancar con valores por defecto |
| A-6 | Media | `services/pipeline_service.py:130,1447` | El timeout de 120 s cancela la corrutina, no el hilo de Whisper/LLM: las solicitudes siguientes se encolan detrás | Semáforo en las etapas pesadas y cancelación cooperativa |
| A-7 | Media | `main.py:108-146` | La sincronización de ODEPA hace un intento al día: un fallo a las 06:00 deja precios viejos 24 h | Reintentos dentro del ciclo (5, 15 y 45 min) |
| A-13 | Media | `docker-compose.prod.yml:195-197` | La imagen del gateway de WhatsApp va en `:latest` con el secreto del webhook y la sesión | Fijar por digest `@sha256:...` |
| A-8 a A-12 | Baja | ver reporte | Notas de voz solapadas en paralelo, `compare_digest` con no ASCII da 500, `X-Forwarded-For` confiable, doc de readiness desfasada, CI sin `ruff format` ni auditoría de dependencias | — |

## Defectos de Wenuke

| # | Sev. | Dónde | Qué pasa | Arreglo mínimo |
|---|---|---|---|---|
| D1 | Alta | `backend/main.py:111-115`, `:692-693`, `db.py:335` | Un token vencido es un bloqueo permanente: `/refresh-token` exige token válido y volver a registrar da 409 | Expiración deslizante y reemisión por admin |
| D2 | Alta* | `main.py:668-684` | Cualquier usuario puede subirse a `premium` con `POST /plan` sin pagar (*alta si se vende) | Quitar la ruta pública; cambiar plan solo por admin o webhook de pago |
| D3 | Alta | `backend/vercel.json`, `scheduler.py:32-37` | En Vercel nada agenda las alertas (no hay `crons`) | Vercel Cron a un endpoint protegido |
| D4 | Alta | `servicio_alertas.py:54-55`, `db.py:242-249` | La misma alerta se reenvía cada 6 h (hasta 28 mensajes por helada) y no hay candado entre scheduler y `/enviar-alertas` | Índice único `(usuario, tipo, día)` con `INSERT OR IGNORE` y un `asyncio.Lock` |
| D5 | Media | `main.py:69-80,534-580` | El limitador usa la IP del par TCP y su diccionario nunca se limpia; tras nginx todos comparten el cupo (si uvicorn no confía en el proxy; no verificado) | `--proxy-headers --forwarded-allow-ips` y poda de claves |
| D6, D7 | Media | `models.py:192,235-242`, `db.py:335` | Teléfono sin normalizar (duplicados), sin doble opt-in, y el 409 devuelve el número completo | Normalizar a `+569XXXXXXXX`, mensaje fijo en el 409 |
| D8, D9 | Media | `servicio_alertas.py:54-73`, `whatsapp.py:66-75` | Alertas registradas como enviadas aunque falle el envío; una excepción aborta la ronda de todos los usuarios | Registrar tras confirmar el envío; `try/except` por usuario |
| D11, D12 | Media | `clima.py:61-66`, `main.py:198-215,561-564` | Si cae el clima responde 500 (el modo offline nunca se usa) y se sirve clima vencido sin su edad, con `Cache-Control: public` incluso en errores | Excepción propia mapeada a 502 o respuesta offline; `Cache-Control` solo en 200 |
| D13 | Media | `db.py:35-57,306-336,107-115` | Una conexión compartida con transacciones que cruzan `await`; en Turso `BEGIN/COMMIT` no hacen nada: un registro a medias deja un usuario sin token | Lock por unidad transaccional; operación atómica para Turso |
| D14 | Media | `db.py:218-249` | No hay borrado de cuenta ni retención para teléfono, coordenadas e historial (Ley 21.719) | Endpoint de eliminación y purga programada |
| D15 | Media | `reglas.py:289-291` | «Próximas 6 horas» son las horas 00:00 a 05:00 de hoy, no desde ahora | Cortar desde la hora actual |
| D16 | Media | `.github/workflows/test.yml:75` | Ningún test importa `main.py`: la API no tiene cobertura en CI | `TestClient` por familia de endpoints |
| D17 a D28 | Baja a Media | ver reporte | BD en `/tmp` en Vercel, imagen sin `.dockerignore` ni `USER`, `0.0 °C` tratado como dato faltante (`reglas.py:282-284`), día bisiesto en `/historico`, y otros | — |

## Cómo seguir

1. AgroVoz: A-1 (el agricultor se queda sin respuesta), luego A-3, A-4, A-5 y A-13 antes de un piloto real.
2. Wenuke: D4 (mensajes repetidos), D1 y D2, y agregar tests de la API (D16) antes de arreglar cada defecto.
3. Escribir primero un test que falle por cada defecto, como en este proyecto.
