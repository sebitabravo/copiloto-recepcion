# Canal de WhatsApp para la demo

El copiloto atiende por WhatsApp con el mismo flujo, el mismo AgentBot y el mismo cronómetro de SLA que el widget web. El canal usa **OpenWA**, un gateway **no oficial** (WhatsApp Web automatizado), con un **número dedicado** a la demo.

## Advertencia

OpenWA no es la API oficial de Meta. WhatsApp puede suspender un número que automatiza su servicio web (sus términos lo prohíben). Por eso:

- Usa un número dedicado solo al bot. Nunca el número real del hotel ni uno personal.
- Es un canal de **demo**. Para producción, el camino es Meta Cloud API con un número +56 del hotel y el inbox "WhatsApp Cloud" de Chatwoot; el copiloto no cambia porque solo habla con Chatwoot.
- La imagen de OpenWA está fijada a `0.27.1` por digest. Las versiones anteriores a 0.26 tienen avisos de seguridad publicados.
- El proyecto `open-wa.org` / `rmyndharis/OpenWA` no es el histórico `open-wa/wa-automate-nodejs` (otra licencia, otro mantenedor). Esto usa el primero.

## Cómo funciona

```
huésped ─ WhatsApp ─ OpenWA ─ webhook firmado ─▶ wa-bridge ─ API pública ─▶ Chatwoot (inbox "WhatsApp demo")
                                                                              │ AgentBot
huésped ◀─ send-text ─ OpenWA ◀─ wa-bridge ◀─ webhook firmado ────────────────┘ copiloto + recepción
```

- Todo viaja por la red interna de Docker. No hace falta un dominio ni HTTPS público.
- El puente (`wa_bridge/`) solo reenvía mensajes `outgoing` y **públicos**. La nota privada de "SLA vencido" nunca llega al huésped (hay un test de regresión).
- Los mensajes que envía la propia sesión de OpenWA vuelven como eventos con `fromMe`; el puente los descarta para no crear un bucle.
- Una conversación resuelta no se reabre: el siguiente mensaje abre una nueva.
- Las respuestas salen de a una por huésped y ordenadas por id (el puente espera 0,4 s para reordenar lo que Chatwoot entrega en paralelo).
- Notas de voz, imágenes y grupos: el huésped recibe un aviso de que solo se leen textos; los grupos se ignoran.

## Antes de la demo: IA con DeepSeek (opcional)

1. Pega la clave en `LLM_API_KEY=` del archivo `.env` y verifica que diga `AI_MODE=assisted` (la IA conversa y consulta; recepción confirma, como dice EVA2).
2. Aplica el cambio con `make up` (recrea el copiloto con la clave nueva).
3. Sin clave, o si DeepSeek falla o tarda más de `AI_TURN_TIMEOUT_S` (12 s), el huésped sigue con el menú numerado: nunca queda sin respuesta.
4. Recarga un saldo chico en DeepSeek: el saldo prepago es el único tope de gasto (sin saldo responde 402 y el bot sigue con el menú).

## Levantar el canal

```bash
make up        # el stack base, si no está arriba
make wa-up     # OpenWA + puente + inbox "WhatsApp demo"
make wa-qr     # guía para vincular el teléfono dedicado y espera la sesión
```

`make wa-qr` crea y arranca la sesión `default` en OpenWA, abre el QR (Vista Previa) y espera a que lo escanees desde el teléfono dedicado (Ajustes → Dispositivos vinculados). Si el QR expira, Vista Previa lo recarga solo; si no, vuelve a correr `make wa-qr`. La sesión persiste en el volumen `openwa_data`. El panel de OpenWA (`http://localhost:2785/`, clave `OPENWA_API_KEY` de tu `.env`) sirve para ver el estado.

El puente solo atiende la sesión `default`: eventos de otra cuenta vinculada se ignoran y las respuestas salen siempre por esa sesión.

## Datos y respaldos

- El puente guarda el chat de WhatsApp (que incluye el teléfono) y su conversación de Chatwoot en `wa_bridge_state`. Al arrancar, el puente borra las claves de deduplicación de más de 30 días y los mapeos de huéspedes de más de 90 días (como la retención del copiloto). Los contactos y mensajes de Chatwoot, los respaldos y la sesión de OpenWA **no** se borran solos: el hotel debe definir cuándo eliminarlos.
- `make backup` incluye la base del puente cuando el canal está levantado. La sesión vinculada de OpenWA (`openwa_data`) **no** se respalda a propósito: es una credencial de la cuenta de WhatsApp; si se pierde, se vuelve a vincular con `make wa-qr`.
- Todo viaja por la red interna de Docker; el único puerto nuevo publicado es el panel de OpenWA en `127.0.0.1:2785`.

## Prueba sin teléfono

`make wa-e2e` reemplaza OpenWA por uno simulado y recorre el flujo real (orden de los mensajes, derivación, nota privada, respuesta humana, conversación resuelta, duplicados, ráfagas). `make wa-e2e SLA=1` agrega los 195 s del cronómetro. Si OpenWA ya tiene una sesión vinculada, la prueba se niega salvo `WA_E2E_FORCE=1`.

## Fallas y límites

- Si Chatwoot u OpenWA no responden, el puente reintenta 2 veces (1 s y 3 s). Si sigue fallando, lo deja en el log (`No se pudo entregar ...`) y **no** lo marca como entregado; no hay cola persistente, así que un mensaje que agotó los reintentos no se reenvía solo.
- No hay cola persistente: los webhooks se aceptan antes de entregar. Si el puente se reinicia en pleno envío o agota los reintentos, ese mensaje se pierde (queda en el log). Un reintento tras un timeout ambiguo de OpenWA puede duplicar un mensaje. Para producción, la entrega debe pasar por una cola durable.
- Los mapeos huésped-conversación se borran tras 90 días sin actividad (no desde su creación) y solo al arrancar el puente.
- Si recepción responde en Chatwoot y OpenWA no tiene sesión lista, Chatwoot muestra el mensaje pero el huésped no lo recibe. Revisa `make wa-qr` y los logs del puente antes de la demo.
- El puente no arranca si `CHATWOOT_ADMIN_TOKEN` o `CHATWOOT_WA_INBOX_SECRET` están vacíos: falla rápido en el arranque, porque con un secreto vacío cada webhook de Chatwoot respondería 401 y el canal quedaría muerto en silencio.

## Prueba de punta a punta (con el teléfono)

Desde **otro** teléfono, escríbele al número dedicado:

1. `Hola` → llega el saludo y el menú numerado.
2. Responde con un número → sigue el flujo.
3. Pide hablar con una persona → queda `pendiente de recepción` en Chatwoot y arranca el cronómetro.
4. Responde desde Chatwoot (usuario de recepción) → el mensaje llega al WhatsApp y el cronómetro se detiene.
5. Sin responder 180 s → la conversación queda con `sla-vencido` y la nota privada **no** llega al WhatsApp.
6. Manda una nota de voz → llega el aviso de solo texto.

Evidencia: `docker compose -f infra/docker-compose.yml --project-directory . --profile whatsapp logs --since=10m wa-bridge openwa`.

## Detener

`make wa-down` detiene OpenWA y el puente. La sesión vinculada se conserva; `make reset` la borra junto con el resto.

## Notas de voz

- Si `VOICE_NOTES=1`, la nota se transcribe aquí con Whisper local (`WHISPER_MODEL`, por defecto `small`). El audio se borra al terminar. Ver `docs/consentimiento-y-retencion.md`.
- Sin `VOICE_NOTES=1`, el huésped recibe el aviso de solo texto, como antes.
- **No verificado con OpenWA 0.27.1:** el puente espera el audio inline en `data.media.data` (base64). AgroVoz lo confirmó con tráfico real de su versión; la documentación de OpenWA no lo describe. Antes de la demo hay que enviar una nota real desde el teléfono dedicado y revisar en los logs del puente si llega el audio.
- Modelo: la primera nota descarga Whisper (cientos de MB) al volumen `wa_bridge_state`. Conviene hacer esa primera transcripción antes de la presentación.

