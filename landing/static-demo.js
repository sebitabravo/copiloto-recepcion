/* Modo estático: la demo responde sin backend.
 *
 * Sustituye window.fetch para los endpoints de /api/*, así que la interfaz real (demo.js,
 * console.js, voice.js) se ejecuta igual y no se entera de que no hay servidor. El propósito es
 * publicar el portfolio en hosting estático (Vercel, Netlify, GitHub Pages): no hay IA, ni PMS,
 * ni Chatwoot, ni datos de nadie.
 *
 * Los textos salen de data/hotel.yaml para no contradecir el producto real.
 */
(() => {
  'use strict';
  if (window.__STATIC_DEMO__) return;
  window.__STATIC_DEMO__ = { replies: 0 };

  const AVISO = 'Demostración simulada: respuestas preparadas en el navegador, sin servidor. Datos ficticios.';
  const CONVERSATION_ID = -1;
  const state = { messages: [], handoff: false, staff: [] };

  const respuestas = [
    [/piscina|spa|servicio/i, 'Tenemos piscina temperada todo el año y desayuno incluido. El spa se reserva en recepción.'],
    [/lleg|ubicaci|donde|dónde|direcci/i, 'Estamos en el sector Molco, camino Villarrica-Pucón Km 12.5, frente a la playa Calfuray: a 12,5 km de Villarrica y de Pucón.'],
    [/horario|check-?in|entrada/i, 'El check-in es desde las 15:00 y el check-out hasta las 12:00. Si llegas antes, guardamos tu equipaje.'],
    [/precio|tarifa|valor|cu[aá]nto/i, 'Los valores van desde $75.000 por noche según habitación y temporada. Recepción confirma la tarifa exacta.'],
    [/disponib|fecha|reserv/i, 'Puedo revisar disponibilidad con tus fechas. Las reservas de esta demo son simuladas y no se crea ninguna.'],
    [/persona|humano|recepcion|recepción|hablar/i, 'Te derivo a una persona del equipo. En esta demo la derivación es simulada: no avisa a nadie.']
  ];

  const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: {'content-type': 'application/json'}
  }));
  const empty = status => Promise.resolve(new Response(null, {status}));

  function responder(texto) {
    const encontrado = respuestas.find(([pattern]) => pattern.test(texto));
    return encontrado ? encontrado[1] : 'Puedo ayudarte con ubicación, servicios, horarios y disponibilidad. ¿Qué necesitas saber?';
  }

  function turnoGuest(texto) {
    const reply = responder(texto);
    const handoff = /persona|humano|recepcion|recepción/i.test(texto);
    state.messages.push({id: state.messages.length + 1, role: 'guest', body: texto, created_at: Date.now() / 1000});
    state.messages.push({id: state.messages.length + 1, role: 'assistant', body: reply, created_at: Date.now() / 1000});
    if (handoff) state.handoff = true;
    window.__STATIC_DEMO__.replies += 1;
    return {
      reply,
      mode: 'guided',
      events: handoff ? [{type: 'handoff', reason: 'Solicitud del huésped', simulated: true}] : [],
      quick_replies: ['¿Cómo llego?', '¿Tienen piscina?', 'Quiero hablar con una persona'],
      usage: {messages_left: Math.max(30 - window.__STATIC_DEMO__.replies, 0)},
      conversation_id: CONVERSATION_ID
    };
  }

  function conversacion() {
    return {
      conversation_id: CONVERSATION_ID,
      step: state.handoff ? 'handed_off' : 'ai',
      messages: state.messages
    };
  }

  function cola() {
    if (!state.messages.length) return {now: Date.now() / 1000, amber_s: 120, red_s: 180, conversations: []};
    if (!state.staff.length) {
      return {now: Date.now() / 1000, amber_s: 120, red_s: 180, conversations: [{
        conversation_id: CONVERSATION_ID,
        step: state.handoff ? 'handed_off' : 'ai',
        contact_name: 'Huésped demo',
        running: state.handoff,
        waiting_s: state.handoff ? 95 : null,
        needs_human: state.handoff,
        prebooking: null,
        prebooking_expires_at: null,
        updated_at: Date.now() / 1000,
        source: 'demo'
      }]};
    }
    const ultimaPersona = state.staff[state.staff.length - 1];
    return {now: Date.now() / 1000, amber_s: 120, red_s: 180, conversations: [{
      conversation_id: CONVERSATION_ID,
      step: 'handed_off',
      contact_name: 'Huésped demo',
      running: false,
      waiting_s: null,
      needs_human: false,
      prebooking: null,
      prebooking_expires_at: null,
      updated_at: ultimaPersona.created_at,
      source: 'demo'
    }]};
  }

  function detalle() {
    const last = state.messages[state.messages.length - 1];
    return {
      conversation_id: CONVERSATION_ID,
      contact_name: 'Huésped demo',
      step: state.handoff ? 'handed_off' : 'ai',
      data: {},
      room_name: null,
      prebooking: null,
      sla: state.handoff ? {started_at: (last ? last.created_at : Date.now() / 1000) - 95, stopped_at: state.staff.length ? Date.now() / 1000 : null, amber_s: 120, red_s: 180} : null,
      now: Date.now() / 1000,
      pms_url: null,
      notes: [],
      messages: state.messages
    };
  }

  const handlers = [
    [/\/api\/demo\/status/, () => ({
      ai_enabled: false, mode: 'off', model: null, sandbox: true, autonomous_booking: false,
      voice: false, tts: 'browser', max_message_chars: 400, messages_per_session: 30,
      disclaimer: AVISO
    })],
    [/\/api\/demo\/session/, () => null],
    [/\/api\/demo\/greeting/, () => ({text: 'Hola, bienvenido a Hotel Bordeluz. Soy el asistente de recepción de esta demostración.', quick_replies: []})],
    [/\/api\/demo\/chat/, (url, init) => turnoGuest(JSON.parse(init.body || '{}').message || '')],
    [/\/api\/demo\/conversation/, () => conversacion()],
    [/\/api\/demo\/reset/, () => { state.messages.length = 0; state.staff.length = 0; state.handoff = false; window.__STATIC_DEMO__.replies = 0; return {status: 'ok', conversation_id: null, step: null, messages: []}; }],
    [/\/api\/demo\/voice\/greeting/, () => ({text: 'Hola, estás llamando al Hotel Bordeluz. Esta demostración no reproduce audio real.', language: 'es', audio_b64: null, voice_error: 'demo_sin_audio'})],
    [/\/api\/demo\/voice/, (url, init) => ({...turnoGuest(JSON.parse(init.body || '{}').message || ''), spoken: '', audio_b64: null, voice_error: 'demo_sin_audio', spoken_language: 'es'})],
    [/\/api\/panel\/queue/, () => cola()],
    [/\/api\/panel\/[^/]+\/reply/, (url, init) => {
      const body = JSON.parse(init.body || '{}').body || '';
      const message = {id: state.messages.length + 1, role: 'staff', body, created_at: Date.now() / 1000};
      state.messages.push(message);
      state.staff.push(message);
      return {message};
    }],
    [/\/api\/panel\/[^/]+\/note/, () => ({id: 1, author: 'Recepción (demo)', body: 'Nota de demostración.', created_at: Date.now() / 1000})],
    [/\/api\/panel\/[^/]+/, () => detalle()],
    [/\/metricas\/data\.json/, () => ({
      window_days: 7, conversations: state.messages.length ? 1 : 0, ai_replies: window.__STATIC_DEMO__.replies,
      handoffs: state.handoff ? 1 : 0, bookings: 0, cost_per_conversation_clp: 0
    })]
  ];

  const real = window.fetch.bind(window);
  window.fetch = function (input, init = {}) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const handler = handlers.find(([pattern]) => pattern.test(url));
    if (!handler) return real(input, init);
    const body = handler[1](url, init);
    if (body === null) return /demo\/session/.test(url) && (init.method || 'GET').toUpperCase() === 'POST' ? empty(204) : json({demo: true, name: 'Recepción (demo)'});
    return json(body);
  };

  // Aviso visible: nunca se presenta como un servicio con backend.
  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.createElement('div');
    banner.id = 'static-demo-banner';
    banner.setAttribute('role', 'note');
    banner.style.cssText = 'position:sticky;top:0;z-index:60;padding:8px 16px;background:#8d5a2b;color:#fffaf2;font:600 12px/1.4 system-ui,sans-serif;text-align:center';
    banner.textContent = AVISO;
    document.body.prepend(banner);
    // Sin backend no hay aviso de privacidad servido por el copiloto: se oculta el enlace roto.
    document.querySelectorAll('#privacy-link').forEach(link => { link.removeAttribute('href'); link.hidden = true; });
  });
})();
