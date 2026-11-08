# Caso de estudio: copiloto de recepción para una pyme de alojamiento

Un asistente que atiende consultas de huéspedes por WhatsApp, consulta la disponibilidad en el PMS y
deja la reserva preparada para que una persona la confirme. Construido de punta a punta: canal,
bandeja, agente, herramientas, PMS simulado, métricas y demo pública.

---

## El problema

Un hotel boutique de Villarrica pierde ventas en la ventana de minutos posterior a la primera
consulta. El gerente lo describe así: **si no responden en tres minutos, la venta se pierde**. La
huésped, en cambio, tolera hasta un día.

Esa brecha —tres minutos contra un día— es el negocio. La consulta llega casi siempre por WhatsApp,
la cierra una persona, y en temporada alta el teléfono consume el 80% del tiempo de recepción. Las
consultas fuera de horario simplemente no se responden.

Hay además dos condiciones que definen la solución: el hotel no puede pagar una plataforma
propietaria por habitación, y la reserva no puede confirmarse sin revisar el inventario, porque
sin PMS integrado aparece la sobreventa.

## Qué construí

| Pieza | Función |
|---|---|
| Bandeja de recepción | Chatwoot recibe la conversación, la etiqueta y la asigna a un equipo |
| Copiloto | Responde FAQ, muestra la ubicación primero, consulta disponibilidad y deriva |
| Herramientas | Cuatro: `get_hotel_info`, `check_availability`, `create_booking`, `handoff_to_human` |
| PMS simulado | Fuente de disponibilidad y de pre-reservas auxiliares de 15 minutos |
| Modelo local | Comprensión de lenguaje libre sin costo por consulta |
| Panel de recepción | Cronómetro de 3 minutos y pre-información del huésped |
| Métricas | Latencia de FAQ, cumplimiento comercial, captura nocturna, conversión y costo |
| Demo pública | Landing con el canal simulado y la traza de herramientas en vivo |

Todo corre con `docker compose`: Postgres, Redis, Chatwoot, el copiloto en FastAPI, el PMS en
FastAPI, nginx y SQLite para el estado del agente.

## Tres decisiones que explican el resto

**El bot no confirma: la persona sí.** El agente reúne fechas, personas, habitación y nombre, y
deja una pre-reserva que vence en 15 minutos. La confirmación ocurre en el PMS, con una persona
mirando el inventario. Es la diferencia entre automatizar la conversación y automatizar la decisión.

**Los datos del hotel salen de una herramienta, no de la memoria del modelo.** Ubicación, servicios,
políticas y precios viven en un archivo de datos y se consultan antes de responder. Un modelo puede
redactar; no puede ser la fuente de un precio.

**El motor es local.** El modelo corre en el mismo equipo del hotel. No hay costo por consulta ni
datos de huéspedes viajando a un tercero, que es lo que la ley chilena de datos personales empuja a
resolver.

## Lo que falló, y qué cambió

Esta es la parte que normalmente no se publica. La dejé porque es la que enseña.

Construí una batería de doce conversaciones reproducibles para medir al agente. Cada corrida dejó
un defecto concreto:

| Corrida | Resultado | Defecto encontrado | Cambio |
|---|---|---|---|
| v2 | 9/12 | La derivación y las fechas dependían del modelo | Derivación determinista; relectura del PMS |
| v3 | 6/12 **bloqueante** | **Creó una reserva con un nombre que inventó** | El «sí» y el nombre se verifican en el texto del huésped |
| v4 | 9/12 | Respondió una dirección que no existe | Consulta previa obligatoria y guardrail de invención |
| v5 | 10/12 | Una regresión: mi propio guardrail bloqueaba respuestas válidas | El guardrail recuerda la conversación |
| v6 | 12/12 | Sin fallos | — |

El caso de la v3 es el que más me marcó. El modelo declaraba `guest_confirmed: true` en el
argumento de la herramienta, y el código le creía. La reserva se creaba con un huésped inventado.
La corrección fue dejar de confiar en el argumento: el consentimiento se comprueba sobre las
palabras del huésped, y una pregunta o un «no» no cuentan.

El segundo defecto apareció en operación, no en la batería. Pregunté «¿dónde están ubicados?» y el
copiloto respondió **«calle Santa Fe 1234, pleno centro de Santiago»**. Inventó una dirección
completa. De ahí salieron dos reglas: el agente consulta el hotel antes de responder, y una
respuesta que afirma datos sin herramienta se reemplaza por un texto seguro.

En la v5 me equivoqué en la dirección contraria: mi guardrail empezó a bloquear respuestas
correctas que reutilizaban una lectura anterior del PMS. Lo detectó la misma batería.

## Cómo se mide

```
make test    137 pruebas del copiloto · 25 del PMS
make e2e     4 escenarios sobre el stack real: FAQ, disponibilidad, fuera de turno, PMS caído
make demo    verifica los servicios, levanta el modelo y lo precalienta
scripts/model_eval.py    12 conversaciones contra cualquier modelo compatible
```

La prueba end-to-end comprueba lo que ve cada lado: que el huésped reciba respuesta en menos de un
segundo, que la ubicación aparezca antes de pedir datos, que la pre-reserva quede pendiente de
confirmación, que la conversación llegue etiquetada como `comercial` o `nocturna` al equipo de
recepción con una nota privada fechada, y que con el PMS caído el copiloto no prometa disponibilidad.

La landing pública también se mide. Lighthouse, móvil y escritorio:

```
Rendimiento 100 · Accesibilidad 100 · Buenas prácticas 100 · SEO 100
103 KB transferidos · Speed Index 1,2 s · CLS 0
```

La última optimización fue la más reveladora: la página pesaba 2,6 MB por el widget de Chatwoot,
que se cargaba en cada visita aunque nadie lo usara. Ahora baja solo al pulsar el botón del canal
real.

## Lo que este proyecto no resuelve

- **El canal es simulado.** La conversación de WhatsApp en la demo es una maqueta fiel; el canal
  real conectado es la bandeja de Chatwoot. Conectar WhatsApp oficial requiere un proveedor.
- **El PMS es simulado.** La integración real necesita un adaptador por hotel; la interfaz existe,
  pero cada PMS tiene su API.
- **La latencia con IA local ronda los 18 segundos.** El flujo guiado por reglas responde en 0,3 s,
  y es el que opera cuando el modelo no está disponible.
- **No hubo validación con usuarios todavía.** El testeo es técnico; falta la sesión con recepción y
  con huéspedes.

Declarar esto no resta: es la diferencia entre un prototipo que se entiende y una demo que se cae en
la primera pregunta incómoda.

## Stack

FastAPI · SQLite · PostgreSQL · Redis · Chatwoot · Docker Compose · nginx · llama.cpp (Qwen 2.5) ·
HTML, CSS y JavaScript sin framework · pytest · Lighthouse

## Reproducirlo

```bash
make up     # levanta el stack completo
make demo   # verifica todo y precalienta el modelo
```

Landing en `http://localhost:8080`, bandeja en `http://localhost:3000`, métricas en
`http://localhost:8100/metricas`.
