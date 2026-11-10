# Despliegue

## Local (demo)

El arranque oficial de la evaluación no usa Docker:

```bash
make demo-local          # = ./scripts/demo-local.sh · http://localhost:8080/demo
```

Con Docker, la misma demo (`make up`) o el stack completo con Chatwoot:

```bash
make up-full && make creds
```

Sin `make` (Windows con Git Bash), `./scripts/demo.sh` expone los mismos comandos con el mismo nombre:
`./scripts/demo.sh local`, `./scripts/demo.sh up`, `./scripts/demo.sh up-full && ./scripts/demo.sh creds`.

Requiere Docker con 4 GB o más. Si Chatwoot no arranca por falta de memoria con OrbStack, sube el límite:
`orb config set memory_mib 8192` (reinicia la VM de Docker, así que detiene otros contenedores).

El stack se define en `infra/docker-compose.yml` con imágenes fijadas: `chatwoot/chatwoot:v4.18.0-ce`,
`pgvector/pgvector:pg16`, `redis:7-alpine`, `nginx:alpine`. `make up` es idempotente: puedes repetirlo.

## Dos modos de arranque

La demo no necesita Chatwoot. Hay dos formas de levantar el proyecto y conviene elegir la liviana para
presentar:

| Comando | Servicios | RAM en reposo | Cuándo usarlo |
| --- | --- | --- | --- |
| `make up` | landing, copiloto, pms-mock | ~110 MB | Presentar `/demo`: huésped → recepción → respuesta |
| `make up-full` | los anteriores + Chatwoot, Sidekiq, Postgres, Redis | ~1,3 GB | Probar la bandeja real, el widget y WhatsApp |

Chatwoot, Sidekiq, Postgres y Redis están detrás del perfil `full` (`docker compose --profile full`), así
que un `docker compose up -d` normal arranca solo la demo. `seed-chatwoot.sh`, `smoke-docker.sh`,
`backup.sh` y `wa-e2e.sh` declaran ese perfil porque operan sobre Chatwoot. `wait-healthy.sh` y
`preflight.sh` esperan solo los servicios que están corriendo, así que funcionan en ambos modos.
`./scripts/demo.sh up` es el perfil liviano y `./scripts/demo.sh up-full` el completo, igual que en el Makefile.

En el perfil liviano el copiloto arranca con `CHATWOOT_ENABLED` deducido del token: sin `CHATWOOT_BOT_TOKEN`
(solo existe tras sembrar Chatwoot) la integración queda apagada, el token no se exige y `/webhooks/chatwoot`
responde 503 sin leer el cuerpo. Con la integración encendida, el token y `WEBHOOK_SECRET` son obligatorios y
el webhook exige firma válida (401 sin ella).

Sin Chatwoot, el botón «Escribir a recepción» de la landing muestra su aviso de canal no disponible en vez
de abrir el widget: el canal real es opcional para la demo.

### IA y voz por API

El contenedor local de modelo (`llama.cpp`/Qwen, 4,4 GB de imagen) es opcional y ya no hace falta: el
cliente del copiloto habla la API de DeepSeek. Basta con dejar en `.env`:

```sh
LLM_API_KEY=<clave de DeepSeek>      # sin esto la demo responde en modo guiado, sin IA
# LLM_BASE_URL y LLM_MODEL ya apuntan a DeepSeek por defecto en el compose
ELEVENLABS_API_KEY=<clave>           # sin esto la voz usa la síntesis del navegador
ELEVENLABS_VOICE_ID=<id>
ELEVENLABS_VOICE_ID_EN=<id en inglés>
```

El modelo local sigue disponible como respaldo con `infra/docker-compose.ia.yml` y `make model`.

Este repo se desarrolla en Windows con Git Bash y los scripts lo tienen en cuenta: desactivan la conversión
de rutas de MSYS (`MSYS_NO_PATHCONV`) y los comandos de Python usan `uv run python`, así que `make piloto` y
`make e2e` (que añade `tzdata`) funcionan igual en Windows y Linux.

## Red

Los puertos se publican solo en `127.0.0.1`. Para mostrar la demo a otros equipos de tu red define
`BIND_ADDR=0.0.0.0` antes de `make up`; en ese caso protege el panel y las métricas (ver «Servidor»).

Al abrir la demo desde otro equipo, define también `LANDING_ORIGIN` con la URL que escribes en el navegador
(por ejemplo `http://192.168.1.50:8080`), no la de `localhost`. El copiloto solo acepta peticiones de ese
origen (CORS) y tanto la consola (`/demo`) como el chat hablan con el copiloto en `:8100` de forma
*cross-origin*: si el origen no coincide, el navegador bloquea las llamadas y el síntoma es que la consola
queda en «Sin sesión» y el chat no responde. Déjalo en `.env` y reinicia el copiloto.

Las URLs públicas no se editan a mano en la landing: `scripts/seed-chatwoot.sh` genera `landing/config.js`
(gitignored) con la URL de Chatwoot, la del copiloto, el token del widget y `privacyUrl`. Si cambias
`COPILOTO_PUBLIC_URL` o `CHATWOOT_PUBLIC_URL`, vuelve a correr `make seed` para regenerarla.

## Requisitos medidos

Con el stack en reposo dentro de una VM Docker de 4 GB y 1 CPU (OrbStack) los contenedores usan:
Chatwoot ~570 MB, Sidekiq ~510 MB, Postgres ~70 MB, copiloto ~40 MB, pms-mock ~40 MB, Redis y nginx unos
pocos MB: cerca de 1,3 GB en total. El mínimo recomendado sigue siendo 4 GB de RAM por el primer arranque de
Chatwoot (migraciones). No es una medición de carga: no se probó con tráfico sostenido ni en un host de menor
capacidad, y limitar CPU en una máquina potente no reproduce la contención de un servidor pequeño.

## Presentar sin VPS

La demo no necesita servidor propio para la presentación. Tres caminos, de menor a mayor riesgo:

1. **En persona, local (recomendado).** `make up` y abrir `http://localhost:8080/demo`. Sin internet ni
   cuentas; es el escenario que está probado de punta a punta.
2. **Audiencia remota, túnel gratuito.** Con el stack liviano arriba:
   ```sh
   cloudflared tunnel --url http://localhost:8080
   ```
   Copia la URL `https://…trycloudflare.com` y regenera la configuración con **ese** origen:
   ```sh
   COPILOTO_PUBLIC_URL=https://…trycloudflare.com ./scripts/landing-config.sh
   ```
   Así el navegador pide `/api/...` a la misma URL del túnel y nginx la pasa al copiloto
   (`location /api/`), de modo que la cookie de sesión del panel sigue siendo same-site. Con ngrok el
   procedimiento es el mismo (`ngrok http 8080`). La URL cambia en cada arranque gratuito.
   Límite: la pestaña Administración embebe el PMS en `http://localhost:8200`, que no existe para la
   audiencia remota; para mostrarla completa hay que presentar en local.
3. **Portfolio público, sin servidor propio.** `make static-demo` genera `dist/`: la landing y `/demo`
   con `static-demo.js`, que mantiene el estado de la demo en el navegador (conversación, bandeja,
   cronómetro). El chat y la llamada pueden usar IA real —DeepSeek y ElevenLabs— a través de las
   funciones de Vercel, con las claves como variables del proyecto; sin claves, la página responde con
   los guiones y la voz del navegador, y lo declara. No hay PMS ni Chatwoot. Se publica gratis:
   ```sh
   PUBLIC_SITE_URL=https://copiloto-recepcion.vercel.app ./scripts/build-static-demo.sh
   npx vercel deploy --prod dist
   ```
   En Netlify basta arrastrar `dist/` (lleva `_redirects`); en Vercel, `cleanUrls` resuelve `/demo` y
   `/privacidad`. Comprobado: en esa versión ninguna petición a `/api` sale a la red.

   **Publicado:** <https://copiloto-recepcion.vercel.app> (proyecto `copiloto-recepcion` de la cuenta
   `sebitabravo`). Para volver a publicar hay dos pasos que no están en el repositorio:

   ```sh
   PUBLIC_SITE_URL=https://copiloto-recepcion.vercel.app ./scripts/build-static-demo.sh
   cp .vercel/project.json dist/.vercel/project.json   # el build limpia dist/, incluido su enlace
   cd dist && npx vercel deploy --prod
   ```

   `dist/` está en `.gitignore` y el enlace `.vercel/` también; nada de eso se versiona.
   La página `/privacidad` no es un archivo del repositorio: el build la renderiza con el mismo
   `privacy.render` del copiloto (`scripts/render-privacy.py`), así que el texto legal tiene una sola
   fuente y `copiloto/tests/test_static_privacy.py` evita que se publique vacía o con enlaces locales.

### La IA del chat en la misma URL publicada (función de Vercel)

`api/demo/chat.mjs` es el asistente del sitio publicado: una función serverless que llama a DeepSeek
con los hechos aprobados del hotel (`api/_hotel.json`, generado desde `data/hotel.yaml`) y las mismas
reglas del copiloto (primera persona, no inventa datos, no confirma reservas, una pregunta por turno,
texto plano).

1. En el proyecto de Vercel, variable `LLM_API_KEY` con tu clave de DeepSeek. Opcional:
   `LLM_MODEL` (por defecto `deepseek-chat`) y `LLM_BASE_URL`.
2. Volver a desplegar. El build escribe `aiChat: true` en `config.js` cuando encuentra la clave.
3. Con `aiChat`, el chat del huésped pide la respuesta a la función y el resto del flujo —fechas,
   disponibilidad, propuesta, bandeja y cronómetro— sigue siendo determinista y local.

Sin clave, `/api/demo/chat` responde 503 con el motivo y la página usa el guion estático: nunca se
queda muda. Si el modelo falla, el shim no deja mensajes a medias y cae al guion.

La llamada de prueba usa la misma idea: `api/demo/tts.mjs` convierte el texto en audio con ElevenLabs
(`ELEVENLABS_API_KEY` y `ELEVENLABS_VOICE_ID` en el proyecto) y el botón de llamada del handset
reconoce la voz del navegador por turnos. Sin esas claves la llamada funciona con la voz del
navegador y no cuesta nada. El servicio `copiloto` conserva `POST /api/demo/voice` para la demo
completa con backend.

## Verificación de las imágenes

`make smoke` valida el compose (`docker compose config`), construye las imágenes de `copiloto` y `pms_mock` y
comprueba que arrancan y responden `/health` con las mismas restricciones de producción (sin root, solo lectura,
`cap_drop: ALL`). Corre también en CI. Existe porque una imagen puede fallar aunque los tests unitarios
pasen, por ejemplo con una dependencia que no está en la imagen (caso AgroVoz #270).

## Respaldo y restauración

`make backup` deja en `backups/<fecha>/` (gitignored, permisos 600) un `pg_dump` de Chatwoot y copias
consistentes de las bases SQLite del copiloto y del PMS. Cada SQLite se verifica con `PRAGMA integrity_check`.
Para restaurar:

```bash
gunzip -c backups/<fecha>/chatwoot.sql.gz | docker compose -f infra/docker-compose.yml --project-directory . exec -T postgres psql -U postgres chatwoot
```

y para las SQLite detén el servicio, copia el archivo al volumen (`copiloto_state` o `pms_state`) y vuelve a
levantarlo. Prueba la restauración antes de depender de ella.

## Endurecimiento

- `copiloto` y `pms-mock` corren sin root, con sistema de archivos de solo lectura (`/tmp` en tmpfs),
  `cap_drop: ALL` y `no-new-privileges`. El estado vive en los volúmenes `copiloto_state` y `pms_state`
  (los volúmenes `copiloto_data` y `pms_data` de versiones anteriores quedan sin uso y se pueden borrar).
- `COPILOTO_ENV=production` hace que el copiloto no arranque si falta un secreto o tiene menos de 16
  caracteres. `/health?probe=readiness` revisa la base; el healthcheck de Docker usa la sonda `liveness`.
- Los webhooks aceptan cuerpos de hasta 256 KB y las páginas de lectura tienen un límite de 60 solicitudes por
  minuto por IP. Si pones un proxy delante, el límite verá la IP del proxy: aplícalo también ahí.
- CI en `.github/workflows/ci.yml` (pytest de `copiloto`, `pms_mock`, `pms_bridge` y `wa_bridge`, ruff sobre
  los mismos cuatro, y los tests de la UI de la demo con `node --test scripts/test-demo-ui.mjs`).

## Variables

Se generan en `.env` (gitignored) a partir de `.env.example`. Las de Chatwoot (tokens, ids) las escribe el seed
en `.env.runtime` (gitignored). Nunca las commitees.

| Variable | Uso |
|---|---|
| `WEBHOOK_SECRET` | Firma HMAC del webhook de Chatwoot y secreto del webhook del PMS |
| `PSEUDONYM_SALT` | Sal secreta para seudonimizar identificadores al vencer la retención (obligatoria en producción) |
| `PMS_EVENTS_SECRET` | Secreto (header) con que el PMS avisa reservas confirmadas al copiloto |
| `PANEL_TOKEN` | Token del panel de Chatwoot para leer datos de una conversación |
| `STAFF_TOKEN` | Token que usa recepción en el PMS simulado |
| `SHIFT_START` / `SHIFT_END` | Turno humano (hora de `America/Santiago`) |
| `FIXED_MONTHLY_CLP` | Costo fijo mensual para el costo por consulta |

## Servidor

1. Una VM con 4 GB de RAM y Docker. Copia el repo, corre `make up`.
2. Pon un proxy con HTTPS delante (Caddy o nginx) y ajusta `FRONTEND_URL` en `infra/docker-compose.yml` a la URL pública de Chatwoot.
   Configura también `COPILOTO_PUBLIC_URL` con HTTPS: determina el atributo `Secure` de la cookie del panel.
   `COPILOTO_PUBLIC_URL` y `CHATWOOT_PUBLIC_URL` alimentan la landing: el seed las escribe en `landing/config.js`
   (URL del copiloto, URL de Chatwoot para el SDK del widget, token y enlace de privacidad `privacyUrl`, que
   sigue a `COPILOTO_PUBLIC_URL`). En producción solo se permite HTTP para `localhost` y `127.0.0.1`, para
   conservar la demo local.
3. `/api/panel/*` exige una sesión firmada o el `PANEL_TOKEN` en el header `X-Panel-Token`.
   Sin clave configurada se rechazan ambos mecanismos, incluso en desarrollo. El acceso manual usa
   `POST /api/panel/login`; la cookie dura 12 horas y es `HttpOnly`, `SameSite=Lax` y `Secure` con HTTPS.
   El seed conserva el token inicial en la URL del Dashboard App por compatibilidad: al cargar, el panel
   lo elimina inmediatamente de la ubicación y lo intercambia mediante el mismo login por una cookie.
   No lo guarda en almacenamiento del navegador ni lo agrega a enlaces posteriores. El primer acceso
   aún puede dejar esa URL inicial en logs del proxy: evita registrar query strings del panel y no compartas
   ese enlace. Solo se cargan datos del personal después del intercambio y la validación de sesión.
   `/webhooks/*` verifican firma o secreto. **`/metricas` y `/metricas/data.json` exigen la sesión del
   panel o el header `X-Panel-Token`** (401 sin credenciales); con el modo demo encendido la consola abre
   esa sesión y los scripts locales la obtienen por la misma vía o con `PANEL_TOKEN`. Expón sin login solo
   `/webhooks/*`, `/panel` (HTML estático) y `/privacidad`.
4. Cambia la URL del Dashboard App en Chatwoot (Configuración → Integraciones → Dashboard Apps) a la URL
   pública del panel, y `PMS_STAFF_URL` a la del PMS.
5. Respalda con `make backup` (Chatwoot y las bases SQLite; ver `docs/whatsapp-demo.md` para el canal de WhatsApp).

## Del PMS simulado al real

Apunta `PMS_URL` a un servicio que cumpla `docs/conector-pms.md` (el adaptador HTTP genérico está en
`copiloto/src/copiloto/pms.py`; `pms_bridge` lo hace para Beds24): lectura de solo consulta con sello de hora. Necesita credenciales del hotel y el contrato del proveedor. La
confirmación sigue siendo humana.

## Límites de la demo pública

La demo puede conversar y consultar un PMS externo, pero no crear reservas allí. Su autorización de
escritura exige `PMS_ADAPTER=http`, `PMS_BOOKING_PATH=/api/v1/bookings` y una de estas bases exactas:
`http://pms-mock:8200`, `http://localhost:8200` o `http://127.0.0.1:8200` (se admite una barra final).
No se aceptan rutas alternativas, credenciales en la URL ni destinos externos. Es una lista local de
destinos conocidos, no una prueba universal de que cualquier servidor sea un sandbox: no sustituyas
el servicio de esas direcciones por un PMS real. Además, las herramientas exigen disponibilidad simulada.

`GET /api/demo/status` informa `sandbox` y la capacidad efectiva `autonomous_booking`; conserva
`mode=full` si ese es el modo configurado, aunque el destino impida reservar. La voz conserva su política
asistida y no crea reservas. Estas restricciones no cambian la autenticación de la API del panel.

Texto, voz y reinicio comparten un bloqueo por sesión dentro de la aplicación: se toma antes de cargar
historial o revisar el cupo, y se conserva hasta guardar el turno. Reiniciar espera al turno activo y luego
borra su historial; otras sesiones pueden avanzar independientemente. Los bloqueos sin usuarios se liberan
mediante referencias débiles, sin mantener una entrada permanente por visitante.
**Esto solo coordina un proceso**: no es un bloqueo distribuido ni garantiza exclusión entre varios workers
o réplicas. Mantén un único proceso para esta demo; antes de escalar, implementa coordinación compartida
para turnos, reinicios y límites de uso.
