# Consentimiento y retención: datos y audio del canal de WhatsApp

Este documento describe qué datos trata el copiloto, para qué, cuánto tiempo y cómo se borran. **No es un análisis legal ni declara cumplimiento de la Ley 21.719.** Antes de usar el canal con huéspedes reales, una persona competente debe revisarlo. Ver el criterio de AgroVoz en `docs/validacion-operativa.md`: un flag técnico no reemplaza un consentimiento documentado.

## Qué se trata

| Dato | Dónde | Finalidad | Cuánto se conserva |
|---|---|---|---|
| Texto de mensajes escritos | Chatwoot y copiloto | Responder la consulta del huésped | Chatwoot: su política. Copiloto: la variable `RETENTION_DAYS` del entorno; si no está definida, `privacy.retention_days` de `data/hotel.yaml` (90 días por defecto) |
| Número de WhatsApp (chat_id) | Puente (`wa_bridge`) y Chatwoot | Enviar la respuesta a la misma persona | Puente: mapeo 90 días sin actividad. Chatwoot: su política |
| **Nota de voz (audio)** | Solo en memoria y en un directorio temporal del contenedor | Transcribirla | **Se borra al terminar la transcripción**, aunque esta falle |
| Texto transcrito de la nota | Igual que un mensaje escrito | Responder la consulta | Igual que el texto escrito |
| Aviso de notas de voz (fecha) | Puente, tabla `voice_notice` | No repetir el aviso a la misma persona | 90 días sin actividad |
| Deduplicación de eventos | Puente, tabla `processed` | Evitar respuestas duplicadas | 30 días |

## Aviso e información previa

- El saludo de la demo y el aviso de privacidad ya informan el tratamiento de datos (`copiloto/src/copiloto/flow.py`).
- La primera vez que el huésped envía una nota de voz, recibe antes de la transcripción un aviso: la nota se transcribe en el hotel y el audio se borra; puede escribir su consulta en su lugar. El aviso se envía una sola vez por huésped (`VOICE_NOTICE`).
- **Limitación honesta:** el aviso informa, pero no pide una aceptación explícita. Para cumplir con un consentimiento documentado haría falta un paso de aceptación con registro de versión, fecha y canal. Esta versión no lo implementa.

## Lo que no se hace

- No se guarda audio, ni en disco persistente ni en la base de datos.
- No se usa el audio ni la transcripción para entrenar modelos.
- No se conserva el texto del aviso con versión; el historial de cambios está en git.

## Cómo se borra

- Audio: automático, al terminar la transcripción (`wa_bridge/src/wa_bridge/transcribe.py`). Está probado en `wa_bridge/tests/test_voice_notes.py`.
- Mapeos, dedupe y avisos: `store.purge_mappings` y `store.purge_processed` al arrancar el puente. El copiloto purga sus datos cada 24 horas.
- Pedido de borrado de un huésped: **manual**. Hay que borrar el contacto y las conversaciones en Chatwoot y las filas de su chat_id en la base del puente. No hay un botón ni un proceso automatizado.
- Respaldos (`scripts/backup.sh`): incluyen la base del puente. Los respaldos no se purgan solos: el hotel debe definir su plazo. La sesión de OpenWA no se respalda.

## Pendiente antes de producción

- Revisión legal de la base de tratamiento y del aviso.
- Paso de aceptación explícita con registro si el hotel lo exige.
- Procedimiento y plazo para pedidos de borrado y para los respaldos.
- Confirmar en el servidor real que el directorio temporal del contenedor es efímero (`tmpfs /tmp` en compose).
