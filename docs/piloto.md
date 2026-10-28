# Piloto con recepción: guion y medición

Este documento es el instructivo para probar el copiloto con una recepción real. No es una
demostración: es una prueba con criterios de éxito escritos antes de empezar, para que el resultado no
se interprete a gusto de quien lo miró.

## Qué se quiere averiguar

1. ¿La persona de recepción entiende, sin explicación previa, qué llegó y qué debe hacer?
2. ¿El copiloto resuelve consultas sin sumarle trabajo?
3. ¿La captura fuera de horario produce solicitudes completas?

## Hipótesis y umbral

| Hipótesis | Umbral para dar por buena | De dónde sale |
|---|---|---|
| H1 · La IA resuelve la mayoría de las preguntas frecuentes sin intervención | ≥ 60 % de las conversaciones no requieren respuesta humana durante el turno | EVA 2, R1 y R4 |
| H2 · Recepción responde dentro de la ventana comercial | ≥ 90 % de las consultas comerciales del turno con primera respuesta humana bajo 180 s | EVA 2, R1 |
| H3 · La noche deja de perderse | ≥ 1 solicitud nocturna completa por semana | EVA 2, R4 |

Si H2 no se cumple, el problema puede ser del hotel y no del sistema: recepción sin dotación no
responde en tres minutos ni con el mejor software. Eso también es un resultado.

## Diseño

- **Línea base**: una semana con el sistema apagado o en modo observación, para tener con qué comparar.
- **Piloto**: dos semanas con el copiloto activo.
- **Turno humano**: el horario real de recepción del hotel. Fuera de ese horario, el copiloto captura
  y avisa; no se cuenta como incumplimiento de H2.
- **Datos**: ficticios o de reservas de prueba. Nunca datos personales reales de huéspedes.

Una consulta es **comercial** si menciona fechas, personas, tarifas o intención de reservar. Un saludo
no cuenta.

## Participantes

| Rol | Qué hace |
|---|---|
| Recepcionista (1–2) | Usa el panel y responde como en un día normal |
| Gerencia | Autoriza el piloto y revisa el informe final |
| Facilitador | Cronometra, observa y anota; no ayuda salvo que se lo pidan |

## Guion de la sesión (45 minutos)

| Min | Actividad |
|---|---|
| 0–5 | Contexto: qué se va a probar y qué no. Se aclara que nada de lo que digan se toma como evaluación personal |
| 5–12 | Recorrido libre del panel: cola, resumen del turno, detalle. Se anota qué miran primero |
| 12–30 | Cinco tareas con guion (abajo). El facilitador no corrige; solo observa y anota |
| 30–38 | Preguntas abiertas: qué sobra, qué falta, qué no se entiende |
| 38–45 | Cierre: se acuerdan los cambios prioritarios y se fija fecha de la segunda vuelta |

## Cinco tareas con criterio de éxito

| # | Tarea | Éxito si… |
|---|---|---|
| 1 | «Llegó una consulta anoche. Encárgate de ella» | Encuentra la conversación en la cola en menos de 30 s y describe qué pidió el huésped |
| 2 | «Una persona contestó a las 14:10. ¿Se respondió a tiempo?» | Identifica el estado del cronómetro y lo explica con sus palabras |
| 3 | «Deja constancia de algo para el turno siguiente» | Escribe una nota y la encuentra después de recargar |
| 4 | «Confirma esta reserva» | Entiende que la confirmación ocurre en el PMS, no en el panel, y llega al botón |
| 5 | «¿Cómo estuvo el turno?» | Lee el resumen del turno y nombra dos cifras sin ayuda |

## Guion de mensajes para probar el canal

Enviar desde un teléfono, en este orden, con pausas para que recepción reaccione:

1. «Hola, ¿tienen habitación para el sábado?» — prueba de FAQ y disponibilidad.
2. «Somos 2 adultos y un niño» — captura de datos.
3. «¿Cuánto sale la doble con jacuzzi?» — consulta de tarifa.
4. «Perfecto, quiero reservarla» — debe pedir confirmación explícita, no crear sola.
5. «Prefiero hablar con una persona» — debe derivar con el contexto armado.

## Qué registrar

Una fila por observación, aunque parezca menor:

| Campo | Ejemplo |
|---|---|
| Tarea | 2 |
| Tiempo | 41 s |
| Dificultad | alta |
| Tropiezo observado | «buscó el botón en el lugar equivocado» |
| Frase textual | «esto lo haría más rápido por WhatsApp» |
| Cambio propuesto | mover el botón de confirmar arriba |
| Severidad | bloqueante / importante / cosmético |

## Criterios de avance y de detención

**Avanzar** si se cumplen las tres: H2 alcanzado o explicado por falta de dotación, ninguna tarea
bloqueante, y recepción puede explicar qué confirma el copiloto y qué confirma una persona.

**Detener y ajustar** si: recepción confirma algo por error, el copiloto promete disponibilidad sin
lectura del PMS, o dos participantes distintos no entienden el mismo concepto.

## Cómo se mide

El sistema mide solo; el facilitador mide a las personas.

```bash
PANEL_TOKEN=... python scripts/pilot_report.py --days 14 --csv piloto.csv
```

Reporta latencia de FAQ contra la meta de 10 s, cumplimiento comercial contra 90 %, captura nocturna,
conversión, costo por consulta, respuestas de IA, reservas creadas y guardrails activados.

Lo que el script **no** puede decir: si recepción entendió, si el botón estaba donde se busca, o si la
fila de la cola se leyó como «urgente». Eso sale de la sesión y de la tabla de observaciones.

## Ética y datos

- Datos ficticios o de reservas de prueba; nunca datos personales reales.
- Se avisa a recepción que el piloto mide el sistema, no su desempeño.
- La grabación de la sesión, si la hay, se pide por escrito y se borra con la retención acordada.
- El copiloto nunca confirma reservas: si alguien cree lo contrario, es un hallazgo del piloto.

## Después del piloto

1. Informe de dos páginas: hipótesis, números, observaciones y decisión.
2. Cambios priorizados por severidad, no por gusto.
3. Segunda vuelta con las mismas tareas, para comparar.
