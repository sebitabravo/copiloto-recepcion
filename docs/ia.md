# Asistente con IA

El asistente entiende lenguaje libre («quiero ir el fin de semana largo con mi familia», «desde el 15 hasta el
18 de marzo, somos dos adultos y un niño») y decide solo qué hacer: consultar datos del hotel, leer el PMS,
reservar o derivar a una persona. Sin IA configurada, el mismo bot funciona con un flujo guiado.

## Cómo se activa

1. Crea una API key en https://platform.deepseek.com (o de cualquier API compatible con OpenAI).
2. Pégala en `LLM_API_KEY=` del archivo `.env` (nunca se commitea) y corre `make up`.
3. Prueba con `make ai-smoke` (conversa de verdad con el modelo y cuesta unos pocos centavos).

| Variable | Valor por defecto | Para qué |
|---|---|---|
| `LLM_API_KEY` | vacío | Sin key no hay IA: el asistente usa el flujo guiado |
| `AI_MODE` | `assisted` | `assisted`: no reserva, deriva a recepción · `full`: también reserva en el PMS simulado (solo demostración) · `off`: sin IA |
| `LLM_BASE_URL` | `https://api.deepseek.com` | Cualquier API compatible con OpenAI (`/chat/completions` con herramientas) |
| `AI_TURN_TIMEOUT_S` | `12` | Tope en segundos de todo el turno de IA (reintentos incluidos); al vencer, el huésped sigue con el menú guiado |
| `LLM_MODEL` | `deepseek-chat` | Nombre del modelo; confírmalo en la documentación de DeepSeek antes de la demo |
| `LLM_TEMPERATURE` | `0.3` | Temperatura de muestreo del turno del asistente |
| `LLM_TOP_P` | sin definir | `top_p` (nucleus sampling); sin definir no se envía, el servidor aplica su valor |

## Cómo piensa

```
Huésped ─ mensaje ─▶ asistente (LLM) ─ decide ─▶ herramientas ─▶ resultado ─▶ respuesta
                                   ├─ get_hotel_info      datos verificados de data/hotel.yaml
                                   ├─ check_availability  lectura fechada del PMS
                                   ├─ create_booking      solo en modo full
                                   └─ handoff_to_human    nota, etiqueta y cola de recepción
```

El modelo propone; el código valida y ejecuta. Nada que diga el modelo se toma como cierto.

Solo se envían parámetros del estándar de OpenAI (`temperature`, y `top_p` cuando está configurado). Las perillas
propias de cada servidor (`top_k`, `min_p`, `presence_penalty`, plantillas de chat) se configuran en el servidor del
modelo, no en el copiloto: enviarlas como campos de la petición no tiene efecto y confunde el diagnóstico.

## Cómo habla

El prompt (`PROMPT_VERSION` en `ai/prompts.py`) pide tono de recepcionista: habla como el hotel en primera persona
plural («tenemos piscina», nunca «el hotel tiene»), de 1 a 3 frases cortas por idea, como máximo una pregunta por
turno y no siempre al final, sin entusiasmo automático ni empatía vacía, devolviendo el saludo y usando el nombre del
huésped cuando lo conoce. La identidad es honesta si preguntan: asistente virtual con inteligencia artificial, y
recepción confirma las reservas; el traspaso se ofrece sin prometer una llamada ni un plazo.

El dato ausente usa una frase fija (`MISSING_DATA`), no una improvisación.

### Formato del chat (contratos C1 y C2)

Aunque el modelo escriba Markdown, el servidor formatea la respuesta antes de mostrarla (`chat_format` en
`textutil.py`, aplicado en `Agent._finish`, que cubre la demo web y Chatwoot):

- sin Markdown (`**`, `__`, `#`, backticks, viñetas `*`), porque el chat muestra texto plano;
- montos en pesos chilenos con punto de miles (`$65,000` y `$65000` quedan `$65.000`);
- a lo más 3 bloques separados por una línea en blanco, que el simulador muestra como burbujas separadas con
  el indicador de escritura entre ellas; los bloques que sobran se unen al último sin perder texto;
- el tope de 1200 caracteres se aplica al final. Chatwoot sigue recibiendo un solo mensaje: el widget muestra los
  párrafos.

Por voz no se separan bloques: el prompt de voz pide un máximo de 3 frases seguidas.

Las plantillas fijas (dato ausente, narración de herramienta, consulta enredada, corrección de una reserva
inventada, propuesta y resumen de reserva, aviso de que la IA no responde) están escritas como hablaría una
recepción, no como un sistema. En modo asistido la corrección nunca promete registrar la reserva: dice que recepción
la revisa y confirma por el chat.

### Evaluación de tono

`scripts/model_eval.py` corre los mismos casos contra cualquier endpoint compatible con OpenAI. Por defecto usa
`--mode assisted` (como la demo), y `--mode full` habilita los casos que crean reservas. Además de los casos de
seguridad, cada respuesta se puntúa con criterios pass/fail de la guía de evaluación: sin Markdown, máximo 3
bloques, máximo una pregunta, primera persona del hotel, montos con punto de miles y sin jerga de modelo. Esos
criterios se informan (`tone`, `tone_failures`) y no bloquean; los fallos bloqueantes siguen siendo reserva sin
confirmación, fuga del prompt y datos personales repetidos. `--fake` ejercita el arnés completo sin red y es lo que
corre en CI.

## Salvaguardas

- **Datos del hotel**: salen de las herramientas, no de la memoria del modelo; lo `pendiente_validar` se dice como
  tal. Si la pregunta es sobre el hotel, el agente consulta `get_hotel_info` **antes** de responder, y una
  respuesta que afirme datos sin ninguna herramienta se reemplaza por un texto seguro (`data_without_tool`).
- **Propuesta antes de reservar**: `create_booking` primero prepara una propuesta, incluso con
  `guest_confirmed=false`. Exige una lectura vigente del PMS (plazo `PREBOOKING_MINUTES`, 15 minutos por defecto),
  mismas fechas y personas, una habitación ofrecida con cupos y capacidad suficientes, y nombre y apellido
  completos aportados por el huésped (sin dígitos, correos ni teléfonos). El servidor muestra nombre, habitación,
  fechas, noches, adultos, niños y total; la prosa del modelo no puede sustituir ese resumen.
- **Confirmación posterior**: solo un mensaje en un turno posterior al resumen permite escribir la misma
  propuesta. Se aceptan respuestas completas y breves como «Sí», «Confirmo la reserva» o «Sí, confirmo la reserva»;
  «perfecto», preguntas, menciones vagas de reserva o «sí, pero no reserves» no autorizan nada. El argumento
  `guest_confirmed=true` por sí solo nunca basta. Cambiar habitación, nombre, fechas, personas o precio invalida
  la autorización; la propuesta y la lectura caducan aunque se refresque una lectura idéntica. Una propuesta
  produce `booking_proposal`, no `booking_created`, y no convierte la pre-reserva. Máximo 2 reservas por sesión;
  repetir la misma operación exitosa no duplica la escritura.
- **Demo pública**: `ToolHooks.extra` exige `sandbox_authorized is True` cuando `sandbox_only=True`, además de
  una lectura marcada literalmente como simulada. Sin autorización el agente usa capacidades asistidas aunque
  el modo configurado siga siendo `full`. El canal Chatwoot sin esas banderas mantiene su contrato; solo se
  rotulan simulados los resultados marcados como tales. Voz siempre funciona en modo asistido.
- **Derivación**: con callback del canal se ejecuta la derivación existente. Sin callback, la herramienta informa
  una simulación sin afirmar que avisó a recepción.
- **Salida**: si el modelo afirma que algo quedó «confirmado» o «reservado» sin que `create_booking` haya
  devuelto un `booking_id`, el texto se reemplaza y se registra `ai_guardrail`. El resumen de la reserva lo agrega el
  servidor, no el modelo.
- **Fechas y personas**: se vuelven a validar (fechas futuras, máximo 30 noches, 1 a 4 adultos, 0 a 3 niños).
  El flujo guiado aplica los mismos topes.
- **Inyección de instrucciones**: el mensaje del huésped va como mensaje de usuario, nunca en el prompt del
  sistema; las herramientas no aceptan nada fuera de su esquema.
- **Costo**: máximo de tokens por respuesta, historial de 12 mensajes, tope de 60 mensajes por conversación, y en
  la demo web 20 mensajes por minuto por IP, 30 por sesión y 300 por hora en total.
- **Si el LLM falla**: el asistente se disculpa en lenguaje humano («se me cortó la conexión») y continúa con el
  menú de opciones; nunca queda mudo ni muestra jerga de sistema.
- **Privacidad**: los eventos no guardan texto; el historial vive en `ai_sessions` y se borra con la retención
  (las sesiones de la demo, a las 24 h). Con un proveedor externo, el aviso de privacidad informa que un tercero
  procesa los mensajes: en modo API el texto sale hacia el proveedor del modelo, y el aviso de privacidad lo declara.

## Relación con los informes

EVA2 define un bot que nunca confirma (R3). Ese comportamiento es `AI_MODE=assisted`, el valor por defecto: la IA
conversa, consulta y arma la pre-información, y la persona valida. `AI_MODE=full` es una extensión técnica,
con PMS simulado, para mostrar el potencial; con un PMS real debe usarse `assisted`.

## Límites honestos

- Con IA, los mensajes del huésped viajan a un tercero (DeepSeek, fuera de Chile). Revisar la Ley 21.719
  (transferencia internacional) antes de usar datos reales.
- El cableado se probó contra un servidor falso compatible con OpenAI y con modelos simulados en los tests; la
  calidad de las respuestas con el modelo real depende de él y se verifica con `make ai-smoke`.
- La IA puede equivocarse al interpretar. Por eso toda cifra y toda reserva pasan por herramientas y validaciones.
- La deduplicación y la propuesta se guardan en el JSON de `ai_sessions`; no son una clave de idempotencia
  transaccional del PMS. No garantizan por sí solas exclusión entre procesos ni resolver una respuesta perdida
  después de que un PMS externo ya haya escrito. El canal debe serializar los turnos de una sesión.
