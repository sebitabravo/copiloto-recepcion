# Guion de la sesión con usuarios · EVA 3

**Instrumento 3.1.2.3 · Ficha de planificación del testeo**
Asignatura: Innovación y Emprendimiento III · FGIE03
Unidad 3: Prototipado y testeo

## 1. Qué se prueba

El prototipo funcional del copiloto de recepción, en dos roles:

| Rol | Qué usa | Qué se observa |
|---|---|---|
| Huésped | Demo pública en `http://localhost:8080` (chat web con interfaz estilo WhatsApp) | Si entiende la respuesta, si confía, si percibe que puede reservar |
| Recepción | Bandeja de Chatwoot `http://localhost:3000` y panel `http://localhost:8100/panel` | Si entiende qué llegó, qué debe hacer y en cuánto tiempo |

Se prueba la **propuesta de valor**, no la interfaz sola: ubicación primero, respuesta rápida, disponibilidad
con sello de hora y confirmación humana.

## 2. Participantes

| Grupo | Cantidad | Perfil | Reclutamiento |
|---|---|---|---|
| Huéspedes | 3 | Personas que hayan buscado o reservado alojamiento en los últimos 12 meses | Compañeros de sección u otras personas fuera del equipo |
| Recepción | 3 | Personas sin experiencia en hotelería; se les explica el rol de recepcionista | Compañeros de sección |
| Facilitador | 1 | Lee el guion, no ayuda en las tareas | Integrante del equipo |
| Observador | 1 | Registra tiempos, errores y comentarios | Integrante del equipo |

Nadie del equipo puede participar como usuario: sesga el resultado.

## 3. Antes de empezar

- [ ] Stack levantado y verificado con `make demo` (7 comprobaciones en verde).
- [ ] Modelo local cargado y precalentado (la primera respuesta tarda más).
- [ ] Un solo turno humano activo (`SHIFT_START`/`SHIFT_END`) para que la derivación se vea.
- [ ] Cronómetro, formularios impresos y consentimiento listos.
- [ ] Datos ficticios: nunca datos personales reales de huéspedes ni de los participantes.

**Consentimiento (leer en voz alta):**

> Esta es una prueba de un prototipo académico. No es el sitio oficial de ningún hotel y todos los
> datos son ficticios. Voy a cronometrar la tarea y tomar notas, no grabo audio ni video. Puedes
> detenerte en cualquier momento sin dar explicaciones. ¿Aceptas participar?

## 4. Tareas

Cada participante hace su bloque completo. El facilitador no corrige ni sugiere: si la persona se
bloquea, registra el bloqueo y deja pasar 60 segundos antes de dar la pista mínima.

### Bloque huésped (10 minutos por persona)

| # | Tarea | Guion para la persona | Éxito |
|---|---|---|---|
| H1 | Entender qué es | «Abre esta página y dime qué crees que hace este servicio. No hagas clic todavía.» | Explica en una frase que es un asistente para consultar y reservar |
| H2 | Consultar disponibilidad | «Pregunta si hay habitación para dos adultos el 12 de noviembre, por dos noches.» | Recibe fechas, personas y una respuesta con hora de lectura del PMS |
| H3 | Distinguir confirmación de disponibilidad | «¿Ya tienes la reserva? ¿Qué falta?» | Responde que falta la confirmación de recepción |
| H4 | Pedir una persona | «Ahora pide hablar con alguien.» | El copiloto deriva y avisa que recepción responde |

### Bloque recepción (12 minutos por persona)

| # | Tarea | Guion para la persona | Éxito |
|---|---|---|---|
| R1 | Entender qué llegó | «Abre esta bandeja. Sin leer el chat completo, dime qué pide esta persona y qué datos ya tienes.» | Nombra fechas, personas y estado en menos de 30 s |
| R2 | Priorizar | «Tienes dos conversaciones. ¿Cuál atiendes primero y por qué?» | Usa el cronómetro o la etiqueta, no el azar |
| R3 | Confirmar | «Confirma la pre-reserva en el PMS.» | La confirma con el token y verifica el estado |
| R4 | Cerrar el turno | «Deja una nota para el turno siguiente y revisa el resumen del turno.» | Nota con autor y resumen leído en voz alta |

## 5. Registro por tarea

Una fila por tarea y participante. Este es el registro que alimenta el criterio 3.1.2.

| Campo | Cómo se registra |
|---|---|
| Tiempo | Segundos desde que termina el guion hasta que la persona dice «listo» |
| Resultado | Logrado / Logrado con ayuda / No logrado |
| Pista dada | Ninguna / Mínima / Explicación completa |
| Dificultad percibida | Escala 1 (muy fácil) a 5 (muy difícil), preguntada al terminar |
| Qué confundió | Textual: qué elemento o frase generó duda |
| Cambio sugerido | Textual: qué cambiaría la persona |
| Nota del observador | Solo hechos observables, sin interpretación |

Plantilla: `docs/eva3/testeo/registro-sesion.md`.

## 6. Preguntas de cierre (5 minutos)

1. ¿Qué fue lo primero que entendiste del servicio?
2. ¿Confiarías en esta respuesta para decidir una reserva? ¿Por qué?
3. ¿Qué te habría hecho falta para responder sin preguntar nada?
4. Si esto fuera real, ¿lo usarías? ¿Qué tendría que pasar para que sí?

Registrar respuestas textuales, sin resumir.

## 7. Criterios de la sesión

| Resultado | Lectura | Qué se hace después |
|---|---|---|
| 5 de 6 personas completan H2 y R1 sin ayuda | La propuesta se entiende | Se documenta como validada en iteración 1 |
| 3 a 4 de 6 | Hay fricción localizada en un paso | Se ajusta ese paso y se repite la tarea con dos personas nuevas (segunda iteración) |
| Menos de 3 | La propuesta no se entiende | Se revisa el mensaje de entrada antes de seguir; no se culpa al usuario |

La segunda iteración es obligatoria para el criterio 3.1.2: se repite el bloque con los ajustes aplicados
y al menos dos participantes nuevos, y se registra igual.

## 8. Riesgos y cómo se controlan

| Riesgo | Control |
|---|---|
| El facilitador explica de más | Guion escrito, pistas contadas y cronometradas |
| El participante adivina que es una demo académica | Se dice desde el inicio; igual se prueba la comprensión del mensaje |
| La IA local tarda y contamina el tiempo | Se anota qué flujo respondió (guiado o IA) en cada tarea |
| Datos reales de terceros | Solo datos ficticios, definidos en el guion |
