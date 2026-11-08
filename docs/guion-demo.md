# Guion de la demo en vivo (EVA 3)

Cinco a siete minutos. Un solo caso de principio a fin, visto desde los dos roles y con la misma marca de la
portada: el huésped consulta al **Hotel Boutique Bordeluz**, el copiloto lee el **PMS simulado** con hora de
lectura y deriva con contexto; recepción toma la solicitud y responde en el mismo hilo.

Datos de prueba: los huéspedes son ficticios y los cupos y precios del PMS son simulados. El asistente nunca
confirma una reserva y nunca usa el número real del hotel.

## Un día antes

Elige un arranque y pruébalo completo una vez:

```bash
make demo-local LIMPIO=1      # sin Docker: portada (:8080), copiloto (:8100) y PMS simulado (:8200)
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
vencida, PMS caído).

## Treinta minutos antes

1. Arranca con escenario limpio: `make demo-local LIMPIO=1` (o `make reset` + `make up` en Docker).
2. Abre la portada (`http://localhost:8080`) y deja lista la pestaña: el recorrido parte en **Probar la demo**.
3. Para presentar en **dos ventanas**, una al lado de la otra:
   - Huésped: `http://localhost:8080/demo?vista=huesped` (si puedes, en modo teléfono).
   - Recepción: `http://localhost:8080/demo?vista=recepcion`. Entra como **Sofía**.
4. En la ventana del huésped, en **Turno de recepción**, elige **Simular en turno** (la demo usa la hora de
   Chile; fuera de 08:00–22:00 el caso sería «fuera de turno»).
5. En una sola pantalla basta con `/demo` en **Vista partida**: el mismo marco del hero de la portada, con el
   chat a la izquierda y la bandeja a la derecha.

## Recorrido (orden sugerido)

| # | Qué haces | Qué señalas |
|---|---|---|
| 0 | En la portada, **Probar la demo** | Misma marca, mismos colores y el mismo marco `copiloto.bordeluz.demo` del hero, ahora en vivo. |
| 1 | Huésped escribe **«¿Dónde queda el hotel?»** | Ubicación primero (paso 01 de la portada): sector Molco, con enlace al mapa. El saludo es un mensaje propio; la ubicación y las FAQ se miden aparte (meta < 10 s). |
| 2 | Toca **Consultar fechas** y escribe **«22 al 20 de noviembre · 2 adultos»** | Error entendible: la salida debe ser posterior a la llegada. Los 2 adultos quedan guardados. |
| 3 | Escribe **«20–22 nov»** y toca **Sin niños** | El bot pidió solo lo que faltaba. El resumen trae la **lectura del PMS con su hora** (paso 03 de la portada), marcada como preliminar, y los botones «Enviar a recepción» y «Corregir». |
| 4 | Toca **Enviar a recepción** | «Solicitud enviada a recepción. Te responderán por aquí.» con su número (BDL-…). Desde ahora el bot deja de contestar este hilo (paso 04: deriva con contexto). |
| 5 | Ventana de recepción: la solicitud llega **Pendiente de recepción** | ID, fechas, huéspedes, canal, motivo, ingreso y espera en vivo con la pastilla de riesgo de la portada (ok → riesgo → fuera de meta). La nota interna es la misma «Pre-información del copiloto» del panel ilustrado en la portada. |
| 6 | **Tomar solicitud** | Responsable: Sofía. Estado: **En atención**. El reloj **no** se reinicia: corre desde que entró la consulta. |
| 7 | **Consultar el PMS** (Verificar cupo) | Lectura fresca del PMS simulado, con hora y «preliminar». No bloquea cupos. |
| 8 | **Usar respuesta sugerida** → **Enviar respuesta** | La sugerencia sale de esa lectura. El huésped ve el mensaje firmado «Sofía · Recepción» en el mismo hilo. Recepción ve **Respondida**; la **Reserva** sigue **Pendiente de confirmación**: responder no reserva (paso 05). |
| 9 | Recarga ambas ventanas (F5) | El mismo caso, con el mismo responsable y los mismos estados: todo viene del servidor. |

## Medición (cómo mostrarla)

En la ficha, **Medición de esta solicitud**:

- **Primera respuesta**: tiempo desde el **ingreso de la consulta comercial** (hora del servidor) hasta la
  primera respuesta marcada como «Respuesta (cuenta para la meta)». Meta: < 180 s en turno.
- Un **acuse** («Ya te reviso») se envía al huésped pero **no** detiene el reloj: la pertinencia la declara
  quien responde y queda visible en el hilo.
- La lista de eventos (ingreso, lectura del PMS, solicitud creada, asignación, primera respuesta) permite
  recalcular el tiempo a mano. Si vence la meta sin respuesta pertinente, aparece «Meta vencida» y queda
  registrado.
- Ubicación y FAQ: latencia de cada respuesta aprobada desde el ingreso del mensaje (meta < 10 s).

## Ruta fuera de turno

1. En la ventana del huésped elige **Simular fuera de turno** y toca **Empezar como otro huésped** (el caso
   anterior sigue en la bandeja).
2. Toca **Hablar con recepción** (o haz una consulta de fechas completa y envíala).
3. El huésped lee: «Solicitud guardada: N.º BDL-…. Recepción atiende de 08:00 a 22:00 (hora de Chile) y te
   responderá por aquí desde las 08:00 del …».
4. En recepción la solicitud aparece con la marca **Fuera de turno**; su medición dice «no cuenta para la meta».

## PMS sin respuesta (opcional)

En la ficha, marca **Simular caída** y toca **Consultar el PMS**: la bandeja dice «Cupo desconocido» y propone
un seguimiento honesto. Para mostrarlo desde el huésped, arranca con `SIMULATE_DOWN=1` en el PMS: el resumen dice
que no pudo consultar y la solicitud entra como «Cupos sin verificar».

## Separación entre consulta y reserva

Repite al cerrar: el **estado de atención** (Pendiente de recepción → En atención → Respondida) y el **estado
de reserva** (Pendiente de confirmación) son cosas distintas. El asistente orienta, lee el PMS y captura;
recepción verifica cupos y confirma la reserva en el PMS con su token. La escritura en un PMS real es fase 3.

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
