// Asistente de la demo publicado en Vercel: llama a DeepSeek con los hechos aprobados del hotel.
//
// La clave vive del lado servidor (`LLM_API_KEY` en el proyecto de Vercel), nunca en el navegador.
// Sin clave responde 503 y la página sigue con el guion estático, así la demo nunca queda muda.
//
// Guardrails (los mismos del servicio `copiloto`): habla como el hotel en primera persona, no inventa
// datos, no confirma reservas, una sola pregunta por turno y texto plano sin Markdown.
import hotel from '../_hotel.json' with {type: 'json'};

const MAX_MESSAGE = 400;
const MAX_REPLY = 700;
const TIMEOUT_MS = 9000;

const SYSTEM = `Eres el asistente de recepción de ${hotel.name}, en español de Chile, por chat.
Hablas como el hotel, en primera persona plural: «tenemos piscina», «estamos frente a la playa».
Nunca digas «tienen» ni «el hotel cuenta con» al hablar del hotel.

REGLAS
1. Responde en 1 a 3 frases cortas. Texto plano, sin Markdown, sin listas numeradas.
2. Haz como máximo una pregunta por turno y no termines siempre preguntando.
3. Solo puedes afirmar lo que está en DATOS. Si el dato no está, dilo y ofrece consultarlo con recepción.
4. Nunca confirmas reservas: reúnes los datos y una persona de recepción confirma cupo y precio.
5. No pidas RUT, tarjeta, teléfono ni correo: basta el nombre.
6. Si piden hablar con una persona, dilo y ofrece pasar la solicitud a recepción.
7. Si preguntan si eres una persona o una IA, responde con honestidad que eres el asistente virtual.
8. Montos en pesos chilenos con punto de miles: $80.000.

DATOS (fuente única, no inventes fuera de aquí)
${JSON.stringify({ubicacion: hotel.location, politicas: hotel.policies, servicios: hotel.faqs.map(f => f.answer)}, null, 1)}`;

export const config = {maxDuration: 30};

function plain(text) {
  return String(text)
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function buildMessages(message, history = []) {
  const turns = Array.isArray(history)
    ? history.slice(-8)
      .filter(entry => entry && typeof entry.text === 'string' && entry.text.trim())
      .map(entry => ({role: entry.role === 'guest' ? 'user' : 'assistant', content: String(entry.text).slice(0, MAX_MESSAGE)}))
    : [];
  return [{role: 'system', content: SYSTEM}, ...turns, {role: 'user', content: String(message).slice(0, MAX_MESSAGE)}];
}

export async function ask(message, history, {key = process.env.LLM_API_KEY, base = process.env.LLM_BASE_URL || 'https://api.deepseek.com', model = process.env.LLM_MODEL || 'deepseek-chat', fetchImpl = fetch} = {}) {
  if (!key) return {status: 503, body: 'La IA de esta demo no está configurada (falta LLM_API_KEY).'};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetchImpl(`${base.replace(/\/+$/, '')}/chat/completions`, {
      method: 'POST',
      headers: {'content-type': 'application/json', authorization: `Bearer ${key}`},
      body: JSON.stringify({
        model,
        messages: buildMessages(message, history),
        max_tokens: 300,
        temperature: 0.2,
        stream: false,
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      return {status: 502, body: `El modelo respondió ${response.status}.`};
    }
    const payload = await response.json();
    const reply = plain(payload?.choices?.[0]?.message?.content || '').slice(0, MAX_REPLY);
    if (!reply) return {status: 502, body: 'El modelo no devolvió texto.'};
    return {status: 200, body: {reply}};
  } catch (error) {
    return {status: error.name === 'AbortError' ? 504 : 502, body: `La IA no respondió a tiempo (${error.name}).`};
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
  const message = String(body.message || '').slice(0, MAX_MESSAGE).trim();
  if (!message) {
    res.status(400).json({detail: 'Falta el mensaje'});
    return;
  }
  const result = await ask(message, body.history);
  if (result.status !== 200) {
    res.status(result.status).json({detail: result.body});
    return;
  }
  res.status(200).json(result.body);
}
