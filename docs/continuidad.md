# Continuidad: qué funciona cuando se acaban la IA y la voz

El copiloto funciona en tres niveles. Cada nivel depende solo del anterior.

| Nivel | Qué incluye | Servicios de pago | Costo mensual extra |
|---|---|---|---|
| 1. Sin IA ni voz | Flujo guiado (botones y números), FAQ verificadas del hotel, derivación a recepción con nota, cronómetro de 180 s, panel y métricas | Ninguno | 0 |
| 2. Con IA (texto) | Lo anterior + asistente conversacional con herramientas (disponibilidad, derivación) | Modelo de lenguaje | Según consumo |
| 3. Con voz | Lo anterior + respuestas habladas y tarjeta de voz en la landing. Voz del navegador por defecto (sin costo); ElevenLabs solo si se configura | Ninguno, o ElevenLabs opcional | 0, o plan Starter si se activa ElevenLabs |

## Qué pasa cuando se acaba cada servicio

- **Se acaba la IA** (clave inválida, saldo en cero o error del proveedor): el asistente cae al flujo guiado. Está cubierto por pruebas (`test_llm_outage_degrades_to_the_guided_menu`).
- **Se acaba la cuota de voz** (ElevenLabs responde 401, 402, 429 o 5xx): la respuesta llega en texto y la tarjeta muestra "sin audio por ahora". La conversación no se corta.
- **Tope interno de voz** (`VOICE_CHARS_PER_HOUR`, `VOICE_CHARS_PER_MONTH`): mismo comportamiento, sin llamadas al proveedor.
- **Sin ElevenLabs configurado:** la voz la pone el navegador (`speechSynthesis`), gratis. El servidor responde con el texto y no llama a ningún proveedor de voz.

## Cómo cerrar sin romper la demo

1. Pon `AI_MODE=off` en `.env` y borra `LLM_API_KEY` y `ELEVENLABS_API_KEY`. Queda el nivel 1.
2. Corre `make up` y prueba: un saludo, una FAQ, una pregunta sin dato (debe decir "No tengo ese dato publicado" y dar el contacto) y la derivación con "recepción".
3. Revisa en el panel de ElevenLabs cuánto le queda al plan antes del corte.

## Presupuesto y cifras con fuente

- **ElevenLabs Starter, verificado con la API el 4 nov 2026:** 40 000 caracteres por mes, 0 usados, reinicio reportado el 4 de cada mes. Endpoint: `GET /v1/user/subscription`.
- **Conflicto entre fuentes:** la página de precios describe el Starter con 30 000 créditos al mes. La API reporta 40 000 caracteres. Confirma el número en el panel de tu cuenta antes de presentar. El tope mensual del copiloto (30 000) queda por debajo de ambos.
- **Flash v2.5:** cuesta menos créditos por carácter que Multilingual v2 en la API. La multiplicación exacta no quedó confirmada en la documentación.
- **DeepSeek:** el precio del caché de contexto cambia según la fuente consultada y no quedó verificado en la página oficial. Carga un saldo chico y revisa el consumo real en el panel.

## Optimizaciones ya implementadas

- **Caché de audio por texto:** la misma frase, en el mismo idioma, se sintetiza una sola vez (`AUDIO_CACHE_MAX` = 200 entradas en memoria). Se pierde al reiniciar el proceso.
- **Saludo cacheado** por idioma, sintetizado una vez.
- **Topes** por respuesta (450 caracteres), por hora y por mes.
- **Respuestas cortas para la voz:** máximo tres frases, sin listas ni enlaces.
- **Voz solo a pedido:** nada se sintetiza en segundo plano.

## Pendiente (no implementado)

- Audio pregrabado persistente para las FAQ fijas: una vez generado, no se vuelve a pagar.
- Piper como respaldo local: implementado como opción (`PIPER_MODEL_PATH`); sin probar en el servidor real. Ver `docs/voz.md`.
