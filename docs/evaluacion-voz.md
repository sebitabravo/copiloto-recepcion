# Evaluación de la voz: ida y vuelta (WER)

Mide si lo que dice la voz del copiloto se entiende. Método: texto de respuesta → síntesis → transcripción → WER (tasa de error de palabras).

## Qué mide y qué no

- **Mide:** inteligibilidad de la voz de ElevenLabs (`eleven_flash_v2_5`, español) según Whisper local `small`, sobre respuestas reales del hotel.
- **No mide:** naturalidad (eso necesita escucha humana, MOS), la voz del navegador (que no corre en el servidor), audio de teléfono ni hablantes rurales. Para hablantes rurales hace falta una muestra con consentimiento, igual que en AgroVoz.

## Cómo correrla

```bash
cd copiloto
uv run --with faster-whisper --with "av==13.1.0" python ../scripts/voice_roundtrip.py --out <carpeta-fuera-del-repo>
```

La clave de ElevenLabs se lee del entorno y no se imprime. `av==13.1.0` es necesario: versiones más nuevas de `av` no aceptan el argumento que usa `faster-whisper`. El corpus se construye desde `data/hotel.yaml` y no lleva cifras: el WER no debe medir cómo se dicen los números.

## Resultado del 4 nov 2026

| Muestra | Palabras | WER |
|---|---:|---:|
| saludo | 35 | 0,029 |
| piscina | 13 | 0,000 |
| tinajas | 21 | 0,000 |
| desayuno | 17 | 0,059 |
| estacionamiento | 5 | 0,000 |
| wifi | 14 | 0,143 |
| **Total (corpus)** | **105** | **0,038** |

Qué errores hubo:
- "Wi-Fi" contra "WiFi": diferencia de escritura, no de comprensión.
- "Bordeluz" oído como "Bordeleuze": error real en un nombre propio.
- "vista al lago" oído como "vista a lago": error de preposición.

## Límites para no sobrevender

- Seis respuestas, con audio limpio sintetizado. Una muestra así no predice audio de teléfono ni de campo.
- Whisper reconoce voz sintética con mucha facilidad; la prueba real es con personas.
- La métrica no ajusta la ortografía. No se "corrigió" el WER para mejorar el número.
- Costo: 694 caracteres de ElevenLabs, alrededor del 2% del cupo mensual del plan Starter reportado por la API.

## Pendiente

- Escucha humana (MOS, escala 1 a 5) con 15 a 20 personas que hayan dado consentimiento.
- Medir la voz del navegador en el equipo de la presentación.
- WER con hablantes de Temuco o rurales, solo con muestras consentidas.
