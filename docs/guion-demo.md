# Guion de la demo en vivo (EVA 3)

Cinco a siete minutos. Un solo caso de principio a fin, visto desde los dos roles: el huésped consulta,
el copiloto prepara la solicitud, recepción la toma con el contexto y responde en el mismo hilo.

Todo es de prueba: **Hostería Demo Villarrica** es un alojamiento ficticio; ubicación, cupos y
conversaciones son simulados. El asistente nunca confirma una reserva.

## Un día antes

Elige un arranque y pruébalo completo una vez:

```bash
make demo-local LIMPIO=1      # sin Docker: copiloto con uv (:8100) y portada (:8080)
```

o, con Docker:

```bash
make up                       # landing, copiloto y PMS simulado (sin Chatwoot)
```

Después:

```bash
make test        # pytest de copiloto y PMS
make ui-test     # pruebas de la interfaz de /demo (node --test)
```

Si algo falla, no se presenta: primero se arregla. El recorrido completo está automatizado en
`copiloto/tests/test_demo_requests.py` (caso canónico, fechas invertidas, reintentos, fuera de turno, meta
vencida, inventario desconocido).

## Treinta minutos antes

1. Arranca con escenario limpio: `make demo-local LIMPIO=1` (o `make reset` + `make up` en Docker).
2. Abre **dos ventanas** del navegador, una al lado de la otra:
   - Huésped: `http://localhost:8080/demo.html?vista=huesped` (o `/demo?vista=huesped` con Docker).
     Si puedes, en el modo teléfono de las herramientas de desarrollo.
   - Recepción: `http://localhost:8080/demo.html?vista=recepcion`. Entra como **Sofía**.
3. En la ventana del huésped, en **Turno de recepción**, elige **Simular en turno** (la demo usa la hora de
   Chile; fuera de 08:00–22:00 el caso sería «fuera de turno»).
4. Si una sola pantalla es más cómoda, usa `/demo` en **Vista partida**: chat a la izquierda y bandeja a la
   derecha, mismos datos.

## Recorrido (orden sugerido)

| # | Qué haces | Qué señalas |
|---|---|---|
| 1 | Huésped escribe **«¿Dónde queda la hostería?»** | Respuesta aprobada: «Cerca de la costanera de Villarrica». La ubicación y las FAQ se responden **antes** de pedir datos de estadía. El saludo es un mensaje propio; la FAQ se mide aparte (meta < 10 s). |
| 2 | Toca **Consultar fechas** y escribe **«22 al 20 de noviembre · 2 adultos»** | Error entendible: la salida debe ser posterior a la llegada. Los 2 adultos quedan guardados. |
| 3 | Escribe **«20–22 nov»** y toca **Sin niños** | El bot solo pidió lo que faltaba. Aparece el **resumen** con «Enviar a recepción» y «Corregir». |
| 4 | Toca **Enviar a recepción** | «Solicitud enviada a recepción. Te responderán por aquí.» con su número (VLL-…) y «Disponibilidad por verificar». Desde ahora el bot deja de contestar este hilo. |
| 5 | Ventana de recepción: aparece la solicitud **Pendiente de recepción** | ID, fechas, huéspedes, canal, motivo, ingreso, tiempo de espera en vivo y la nota interna de pre-información. Datos faltantes se ven como «Pendiente». |
| 6 | **Tomar solicitud** | Responsable: Sofía. Estado: **En atención**. El reloj **no** se reinicia: corre desde que entró la consulta. |
| 7 | **Consultar inventario** (Verificar cupo) | Inventario **de prueba**, con origen y hora de lectura, «preliminar»: Habitación Doble, 1 libre. No bloquea cupos. |
| 8 | **Usar respuesta sugerida** → **Enviar respuesta** | El huésped ve el mensaje firmado «Sofía · Recepción» en el mismo hilo. Recepción ve **Respondida**; la **Reserva** sigue **Pendiente de confirmación**: responder no reserva. |
| 9 | Recarga ambas ventanas (F5) | El mismo caso, con el mismo responsable y los mismos estados: todo viene del servidor. |

## Medición (cómo mostrarla)

En la ficha, **Medición de esta solicitud**:

- **Primera respuesta**: tiempo desde el **ingreso de la consulta comercial** (hora del servidor) hasta la
  primera respuesta marcada como «Respuesta (cuenta para la meta)». Meta: < 180 s en turno.
- Un **acuse** («Ya te reviso») se envía al huésped pero **no** detiene el reloj: la pertinencia la declara
  quien responde y queda visible en el hilo.
- La lista de eventos (ingreso, solicitud creada, asignación, primera respuesta) permite recalcular el tiempo a
  mano. Si vence la meta sin respuesta pertinente, aparece «Meta vencida» y queda registrado.
- FAQ: latencia de cada respuesta aprobada desde el ingreso del mensaje (meta < 10 s).

## Ruta fuera de turno

1. En la ventana del huésped elige **Simular fuera de turno** y toca **Empezar como otro huésped** (el caso
   anterior sigue en la bandeja).
2. Toca **Hablar con recepción** (o haz una consulta de fechas completa y envíala).
3. El huésped lee: «Solicitud guardada: N.º VLL-…. Recepción atiende de 08:00 a 22:00 (hora de Chile) y te
   responderá por aquí desde las 08:00 del …».
4. En recepción la solicitud aparece con la marca **Fuera de turno**; su medición dice «no cuenta para la meta».

## Separación entre consulta y reserva

Repite al cerrar: el **estado de atención** (Pendiente de recepción → En atención → Respondida) y el **estado
de reserva** (Pendiente de confirmación) son cosas distintas. El asistente orienta y captura; recepción verifica
cupos por su procedimiento y confirma explícitamente. La escritura en un PMS real es fase 3.

## Respaldos

| Si pasa esto | Haz esto |
|---|---|
| El servidor no responde | La página lo dice y ofrece reintentar. Revisa la terminal de `make demo-local`. |
| Se corta la red al enviar | La burbuja queda «no enviado»; **Reintentar** reenvía con la misma llave: no se duplica. |
| No hay servidor disponible | Versión estática: `make static-demo` y abre `dist/demo.html` en un servidor local. Mismo recorrido con datos preparados, rotulado «versión estática». |
| La bandeja pide nombre otra vez | Es una sesión nueva de recepción: escribe «Sofía». |

## Después

`make demo-local LIMPIO=1` deja el escenario limpio otra vez. En Docker, `make reset` borra los volúmenes
(pide confirmación).

## Integraciones opcionales (fuera del recorrido de 5 minutos)

Siguen disponibles para quien despliegue el stack completo; no son necesarias para la demo:

- WhatsApp con OpenWA y el puente `wa_bridge`: [docs/whatsapp-demo.md](whatsapp-demo.md) (`make wa-up`).
- Conector del PMS Beds24 con `pms_bridge`: [docs/conector-pms.md](conector-pms.md) (`make bridge`).
- Modelo local con llama.cpp: [docs/ia-local.md](ia-local.md) (`make model`).
