// Voz de la demo publicada: texto a audio con ElevenLabs.
//
// La clave vive del lado servidor (`ELEVENLABS_API_KEY` y `ELEVENLABS_VOICE_ID`). Sin claves responde
// 503 y la pantalla de llamada usa la voz del navegador, que ya existe y no cuesta.
const MAX_CHARS = 400;
const TIMEOUT_MS = 9000;

export const config = {maxDuration: 30};

export async function speak(text, {
  key = process.env.ELEVENLABS_API_KEY,
  voice = process.env.ELEVENLABS_VOICE_ID,
  voiceEn = process.env.ELEVENLABS_VOICE_ID_EN,
  // Multilingual v2 es el modelo más natural en español; flash v2.5 es más rápido y algo más plano.
  model = process.env.ELEVENLABS_MODEL || 'eleven_multilingual_v2',
  language = 'es',
  fetchImpl = fetch,
} = {}) {
  const chosen = language === 'en' && voiceEn ? voiceEn : voice;
  if (!key || !chosen) return {status: 503, body: 'La voz no está configurada en esta demo.'};
  const clean = String(text || '').trim().slice(0, MAX_CHARS);
  if (!clean) return {status: 400, body: 'Falta el texto.'};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetchImpl(
      `https://api.elevenlabs.io/v1/text-to-speech/${chosen}?output_format=mp3_44100_128`,
      {
        method: 'POST',
        headers: {'content-type': 'application/json', 'xi-api-key': key},
        body: JSON.stringify({text: clean, model_id: model,
          // Voz natural y estable, con refuerzo del hablante para que suene clara en el teléfono.
          voice_settings: {stability: 0.45, similarity_boost: 0.8, style: 0.15, use_speaker_boost: true}}),
        signal: controller.signal,
      },
    );
    if (!response.ok) return {status: 502, body: `La voz respondió ${response.status}.`};
    const audio = Buffer.from(await response.arrayBuffer());
    return {status: 200, audio, contentType: 'audio/mpeg'};
  } catch (error) {
    return {status: error.name === 'AbortError' ? 504 : 502, body: `La voz no respondió a tiempo (${error.name}).`};
  } finally {
    clearTimeout(timer);
  }
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({detail: 'Método no permitido'});
    return;
  }
  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
  const result = await speak(body.text, {language: body.language === 'en' ? 'en' : 'es'});
  if (result.status !== 200) {
    res.status(result.status).json({detail: result.body});
    return;
  }
  res.statusCode = 200;
  res.setHeader('content-type', result.contentType);
  res.setHeader('cache-control', 'no-store');
  res.end(result.audio);
}
