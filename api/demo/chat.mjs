// Asistente de la demo publicado en Vercel: DeepSeek con los hechos del hotel y una herramienta para
// registrar la estadía. La clave vive del lado servidor (`LLM_API_KEY`), nunca en el navegador.
//
// El modelo entiende lenguaje natural —«el próximo fin de semana», «en dos semanas», «del 12 al 14»— y
// deja las fechas normalizadas con la herramienta; la página después muestra la disponibilidad real.
import hotel from '../_hotel.json' with {type: 'json'};
import inventory from '../_demo-inventory.json' with {type: 'json'};

const MAX_MESSAGE = 400;
const MAX_REPLY = 700;
const TIMEOUT_MS = 9000;
const ZONE = 'America/Santiago';

const TODAY = () => new Intl.DateTimeFormat('es-CL', {
  timeZone: ZONE, weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
}).format(new Date());
const TODAY_ISO = () => new Intl.DateTimeFormat('en-CA', {timeZone: ZONE}).format(new Date());

const SYSTEM = () => `Eres el asistente de recepción de ${hotel.name}, en Chile. Atiendes por chat y por voz.

CÓMO HABLAS
- Como una recepcionista real: cálida, breve, en primera persona plural («tenemos», «estamos»).
- Frases cortas y conectadas, sin listas ni viñetas, sin negritas, sin emojis.
- Nada de muletillas de robot: no digas «¿en qué puedo ayudarte hoy?», «estoy aquí para ayudarte»,
  «como asistente», «no dudes en preguntar». Saluda como saludaría una persona y sigue la charla.
- Una idea por mensaje y como máximo una pregunta por turno. No repitas lo que el huésped acaba de decir.
- Si el huésped escribe corto, responde corto. Si cuenta algo, acompáñalo sin exagerar.
- El huésped puede escribir como habla, con faltas de ortografía o sin tildes («piesa», «onde kedan»,
  «cuanto sale pa dos»). Entiende la intención, responde simple y nunca lo corrijas ni le pidas que
  escriba mejor.

FECHAS
- Hoy es ${TODAY()} (${TODAY_ISO()} en formato AAAA-MM-DD) en Chile. Interpreta tú las fechas naturales:
  «la siguiente semana», «el próximo viernes», «este fin de semana», «en dos semanas», «del 12 al 14».
  Si el huésped es vago («la siguiente semana»), propone tú fechas concretas y pide un «sí».
  No le pidas que escriba un formato ni le devuelvas la pregunta que acaba de responder.
- Si falta la salida o la cantidad de personas, pregunta lo mínimo necesario, de a una cosa.
- En cuanto tengas llegada, salida y cantidad de adultos, llama a registrar_estadia en ese mismo turno.
  No esperes el nombre, la edad de los niños ni la habitación: eso viene después o no hace falta.
- Si propones una fecha y el huésped dice «sí», «perfecto» o «me sirve», registra esa estadía en ese
  turno, sin volver a preguntar lo mismo.
- No inventes fechas: si falta la salida, pregúntala; si ya la tienes, úsala.

DATOS Y LÍMITES
- Solo afirmas lo que está en DATOS. Si no está, lo dices con naturalidad y ofreces consultarlo con recepción.
- Nunca confirmas una reserva: reúnes los datos y una persona de recepción confirma cupo y precio.
- La disponibilidad sí la puedes ver: usa consultar_disponibilidad con fechas y personas y responde con
  las opciones reales, el precio por noche y el total. Nunca digas que «recepción revisa la
  disponibilidad»: tú la consultas. Los cupos y precios son de un PMS simulado y la reserva la
  confirma una persona, eso sí se lo dices.
- No pides RUT, tarjeta, teléfono ni correo. Basta el nombre.
- Para pasar la solicitud a recepción necesitas el nombre del huésped: si no lo tienes, pídelo antes.
  Cuando lo tengas —o si el huésped pide hablar con una persona— llama a pasar_a_recepcion.
- Si el huésped pulsa «Enviar a recepción» o dice que quiere enviarlo, pide el nombre si falta y llama
  a pasar_a_recepcion en ese turno.
- Si preguntan si eres humano o una IA, responde con honestidad que eres el asistente virtual.
- Si la solicitud ya quedó con recepción, responde dudas simples («te contestan por acá», «el turno es
  de 08:00 a 22:00») y aclara que recepción sigue la conversación. No prometas llamadas, WhatsApp ni
  correos que este canal no puede hacer.
- Si mencionan una mascota, di que la política no está publicada y que recepción lo confirma.

DATOS (fuente única, no inventes fuera de aquí)
${JSON.stringify({ubicacion: hotel.location, politicas: hotel.policies, servicios: hotel.faqs.map(f => f.answer)}, null, 1)}`;

const TOOLS = [{
  type: 'function',
  function: {
    name: 'consultar_disponibilidad',
    description: 'Consulta la disponibilidad del PMS simulado para unas fechas y personas. Devuelve las '
      + 'habitaciones que caben, con precio por noche, total de la estadía y cupos.',
    parameters: {
      type: 'object',
      properties: {
        checkin: {type: 'string', description: 'Llegada en formato AAAA-MM-DD'},
        checkout: {type: 'string', description: 'Salida en formato AAAA-MM-DD'},
        adults: {type: 'integer', minimum: 1, maximum: 6},
        children: {type: 'integer', minimum: 0, maximum: 6},
      },
      required: ['checkin', 'checkout', 'adults'],
    },
  },
}, {
  type: 'function',
  function: {
    name: 'pasar_a_recepcion',
    description: 'Pasa la solicitud a recepción para que una persona confirme. Úsala cuando el huésped '
      + 'quiera cerrar el trámite con una persona, pida hablar con recepción o acepte que se envíe.',
    parameters: {
      type: 'object',
      properties: {
        nombre: {type: 'string', description: 'Nombre del huésped, si ya lo dijo'},
        motivo: {type: 'string', description: 'Motivo breve: consulta de fechas, reclamo, otro'},
      },
      required: [],
    },
  },
}, {
  type: 'function',
  function: {
    name: 'registrar_estadia',
    description: 'Registra las fechas y los huéspedes de la estadía, ya interpretados desde el lenguaje natural. '
      + 'La página usa estos datos para mostrar disponibilidad y precios.',
    parameters: {
      type: 'object',
      properties: {
        checkin: {type: 'string', description: 'Fecha de llegada en formato AAAA-MM-DD'},
        checkout: {type: 'string', description: 'Fecha de salida en formato AAAA-MM-DD'},
        adults: {type: 'integer', description: 'Cantidad de adultos, de 1 a 6', minimum: 1, maximum: 6},
        children: {type: 'integer', description: 'Cantidad de niños, de 0 a 6', minimum: 0, maximum: 6},
      },
      required: ['checkin', 'checkout', 'adults'],
    },
  },
}];

/** Las mismas 5 habitaciones que muestra la página: capacidad, precio y cupos del PMS simulado. */
export function offersFor({checkin, checkout, adults, children}, today = TODAY_ISO()) {
  const rooms = inventory.rooms || [];
  // El fin de semana del 20 al 22 de noviembre está ocupado en el guion de la demo (una unidad menos).
  const busy = checkin <= '2026-11-21' && checkout > '2026-11-20';
  const nights = Math.max(1, Math.round((Date.parse(`${checkout}T12:00:00Z`) - Date.parse(`${checkin}T12:00:00Z`)) / 86400000));
  return rooms
    .filter(room => room.adults >= adults && room.children >= (children || 0))
    .map(room => ({
      code: room.code,
      name: room.name.replace(/^Habitación /, ''),
      available_units: Math.max(0, room.units - (busy ? 1 : 0)),
      nightly_price_clp: room.price,
      total_clp: room.price * nights,
      nights,
    }))
    .filter(offer => offer.available_units > 0)
    .slice(0, 3);
}

export const config = {maxDuration: 30};

const WINDOW_MS = 60_000;
const PER_WINDOW = 20;
const hits = new Map();

export function allow(ip, now = Date.now()) {
  const key = ip || 'desconocido';
  const recent = (hits.get(key) || []).filter(at => now - at < WINDOW_MS);
  if (recent.length >= PER_WINDOW) {
    hits.set(key, recent);
    return false;
  }
  recent.push(now);
  hits.set(key, recent);
  if (hits.size > 500) hits.delete(hits.keys().next().value);
  return true;
}

const ISO = /^\d{4}-\d{2}-\d{2}$/;

// Valida y normaliza lo que propone el modelo: nunca se acepta una estadía imposible.
export function normalizeStay(args, today = new Date()) {
  const checkin = String(args?.checkin || '').trim();
  const checkout = String(args?.checkout || '').trim();
  const adults = Number(args?.adults);
  const children = Number(args?.children ?? 0);
  if (!ISO.test(checkin) || !ISO.test(checkout)) return null;
  const start = Date.parse(`${checkin}T12:00:00Z`);
  const end = Date.parse(`${checkout}T12:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  if (end - start > 60 * 86400000) return null;
  const days = Math.round((start - Date.parse(`${today.toISOString().slice(0, 10)}T12:00:00Z`)) / 86400000);
  if (days < -1) return null;
  if (!Number.isInteger(adults) || adults < 1 || adults > 6) return null;
  if (!Number.isInteger(children) || children < 0 || children > 6) return null;
  return {checkin, checkout, adults, children};
}

export function buildMessages(message, history = []) {
  const turns = Array.isArray(history)
    ? history.slice(-8)
      .filter(entry => entry && typeof entry.text === 'string' && entry.text.trim())
      .map(entry => ({role: entry.role === 'guest' ? 'user' : 'assistant', content: String(entry.text).slice(0, MAX_MESSAGE)}))
    : [];
  return [{role: 'system', content: SYSTEM()}, ...turns, {role: 'user', content: String(message).slice(0, MAX_MESSAGE)}];
}

function plain(text) {
  return String(text)
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^[-*]\s+/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

async function callModel(messages, {key, base, model, fetchImpl, signal}) {
  const response = await fetchImpl(`${base.replace(/\/+$/, '')}/chat/completions`, {
    method: 'POST',
    headers: {'content-type': 'application/json', authorization: `Bearer ${key}`},
    body: JSON.stringify({model, messages, tools: TOOLS, tool_choice: 'auto', max_tokens: 320, temperature: 0.3, stream: false}),
    signal,
  });
  if (!response.ok) return {error: `El modelo respondió ${response.status}.`};
  return {payload: await response.json()};
}

export async function ask(message, history, {
  key = process.env.LLM_API_KEY,
  base = process.env.LLM_BASE_URL || 'https://api.deepseek.com',
  model = process.env.LLM_MODEL || 'deepseek-chat',
  fetchImpl = fetch,
} = {}) {
  if (!key) return {status: 503, body: 'La IA de esta demo no está configurada (falta LLM_API_KEY).'};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const messages = buildMessages(message, history);
    let stay = null;
    let offers_ = null;
    let handoff = null;
    let reply = '';
    for (let round = 0; round < 2; round += 1) {
      const {payload, error} = await callModel(messages, {key, base, model, fetchImpl, signal: controller.signal});
      if (error) return {status: 502, body: error};
      const choice = payload?.choices?.[0]?.message || {};
      const calls = choice.tool_calls || [];
      if (calls.length) {
        messages.push({role: 'assistant', content: choice.content || '', tool_calls: calls});
        for (const call of calls) {
          let args = {};
          try { args = JSON.parse(call.function.arguments || '{}'); } catch (_) { args = {}; }
          const name = call.function?.name;
          if (name === 'consultar_disponibilidad') {
            const normalized = normalizeStay({...args, children: args.children ?? 0});
            if (!normalized) {
              messages.push({role: 'tool', tool_call_id: call.id, content: JSON.stringify({
                ok: false, error: 'fechas inválidas o en el pasado: interpreta de nuevo lo que dijo el huésped'})});
              continue;
            }
            stay = normalized;
            const offers = offersFor(normalized);
            offers_ = offers;
            const resumen = offers.length
              ? offers.map(o => `${o.name}: $${o.nightly_price_clp.toLocaleString('es-CL')} por noche, $${o.total_clp.toLocaleString('es-CL')} las ${o.nights} noches (quedan ${o.available_units})`).join('; ')
              : 'sin cupo para esa capacidad en esas fechas';
            messages.push({role: 'tool', tool_call_id: call.id, content: JSON.stringify({ok: true, ...normalized, offers, resumen})});
            continue;
          }
          if (name === 'registrar_estadia') {
            const normalized = normalizeStay(args);
            stay = normalized || stay;
            messages.push({role: 'tool', tool_call_id: call.id, content: JSON.stringify(normalized
              ? {ok: true, ...normalized}
              : {ok: false, error: 'fechas inválidas o en el pasado: pide de nuevo llegada y salida'})});
            continue;
          }
          if (name === 'pasar_a_recepcion') {
            handoff = {name: String(args.nombre || '').trim().slice(0, 60), reason: String(args.motivo || '').slice(0, 80)};
            messages.push({role: 'tool', tool_call_id: call.id, content: JSON.stringify({ok: true, pasa: 'recepción'})});
            continue;
          }
          messages.push({role: 'tool', tool_call_id: call.id, content: JSON.stringify({ok: false, error: 'herramienta desconocida'})});
        }
        continue;
      }
      reply = plain(choice.content || '').slice(0, MAX_REPLY);
      break;
    }
    if (!reply) return {status: 502, body: 'El modelo no devolvió texto.'};
    const body = {reply};
    if (stay) body.stay = stay;
    if (offers_) body.offers = offers_;
    if (handoff) body.handoff = handoff;
    return {status: 200, body};
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
  const ip = (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.socket?.remoteAddress;
  if (!allow(ip)) {
    res.status(429).json({detail: 'Demasiadas consultas seguidas: espera un momento.'});
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
