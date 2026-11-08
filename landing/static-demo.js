/* Versión estática de /demo (portfolio sin backend: Vercel, Netlify, GitHub Pages).
 *
 * Sustituye window.fetch SOLO para /api/*: la interfaz real (demo-shared/guest/inbox) corre igual contra
 * un servidor simulado en el navegador con el MISMO contrato que copiloto (solicitudes, tomar, responder,
 * cerrar, inventario de prueba). El estado vive en localStorage, así que el chat en una pestaña y la
 * bandeja en otra del mismo sitio comparten el caso. No hay IA, ni PMS, ni Chatwoot, ni datos de nadie:
 * el canal se rotula «WhatsApp simulado · versión estática» y el flujo es guiado, con textos preparados.
 */
(() => {
  'use strict';
  if (window.__STATIC_DEMO__) return;
  const KEY = 'copiloto-static-demo-v2';
  const HOTEL = 'Hostería Demo Villarrica';
  const TZ = 'America/Santiago';
  const SHIFT = {start: '08:00', end: '22:00'};
  const MONTHS = {ene: 1, enero: 1, feb: 2, febrero: 2, mar: 3, marzo: 3, abr: 4, abril: 4, may: 5, mayo: 5,
    jun: 6, junio: 6, jul: 7, julio: 7, ago: 8, agosto: 8, sep: 9, sept: 9, septiembre: 9, oct: 10, octubre: 10,
    nov: 11, noviembre: 11, dic: 12, diciembre: 12};
  const MONTH_RE = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join('|');
  const SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const DAYS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
  const LONG_DAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const LONG_MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
    'octubre', 'noviembre', 'diciembre'];
  const MENU = ['Ubicación', 'Consultar fechas', 'Preguntas frecuentes', 'Hablar con recepción'];
  const FAQ = [
    [/donde|ubicaci|direcci|como llego|llegar/, 'Cerca de la costanera de Villarrica. Estamos a dos cuadras del lago y a 10 minutos caminando del centro.', 'ubicacion'],
    [/check.?in|check.?out|hora de llegada/, 'El check-in es desde las 15:00 y el check-out hasta las 11:00.', 'checkin'],
    [/desayun/, 'El desayuno está incluido y se sirve de 8:00 a 10:30.', 'desayuno'],
    [/estaciona|parking|auto/, 'Hay estacionamiento sin costo dentro de la hostería, sujeto a espacio.', 'estacionamiento'],
    [/mascota|perro|gato/, 'No recibimos mascotas por ahora. Si viajas con un perro de asistencia, recepción te orienta.', 'mascotas'],
    [/wifi|internet/, 'Todas las habitaciones tienen WiFi sin costo.', 'wifi']
  ];
  const LABELS = {pendiente: 'Pendiente de recepción', en_atencion: 'En atención', respondida: 'Respondida', cerrada: 'Cerrada'};
  const REASONS = {commercial: 'Consulta de fechas', human_requested: 'Pidió hablar con recepción'};
  const realFetch = window.fetch.bind(window);
  window.__STATIC_DEMO__ = {key: KEY};

  // ---------- estado compartido entre pestañas ----------
  const empty = () => ({conversations: {}, requests: [], events: [], seq: {msg: 0, req: 0}});
  function load() {
    try { return JSON.parse(window.localStorage.getItem(KEY)) || empty(); } catch (_) { return empty(); }
  }
  function save(db) { try { window.localStorage.setItem(KEY, JSON.stringify(db)); } catch (_) { /* memoria */ } }
  let memory = null;
  const read = () => (memory = load());
  const write = () => save(memory);

  const now = () => Date.now() / 1000;
  const norm = text => String(text).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[–—]/g, '-').replace(/\s+/g, ' ').trim();
  const localParts = epoch => {
    const parts = new Intl.DateTimeFormat('en-CA', {timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23', weekday: 'short'}).formatToParts(new Date(epoch * 1000));
    const get = type => parts.find(part => part.type === type).value;
    return {y: +get('year'), m: +get('month'), d: +get('day'), h: +get('hour'), min: +get('minute')};
  };
  function inShift(scenario) {
    if (scenario === 'open' || scenario === 'closed') return scenario === 'open';
    const {h, min} = localParts(now());
    const minutes = h * 60 + min;
    return minutes >= 8 * 60 && minutes < 22 * 60;
  }
  function nextOpening() {
    const local = localParts(now());
    let day = new Date(Date.UTC(local.y, local.m - 1, local.d));
    if (local.h * 60 + local.min >= 8 * 60) day = new Date(day.getTime() + 86400000);
    return `08:00 del ${LONG_DAYS[day.getUTCDay()]} ${day.getUTCDate()} de ${LONG_MONTHS[day.getUTCMonth()]}`;
  }
  const iso = date => date.toISOString().slice(0, 10);
  const short = value => { const d = new Date(`${value}T12:00:00Z`); return `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${SHORT[d.getUTCMonth()]}`; };
  function nextDate(day, month) {
    const today = localParts(now());
    for (const year of [today.y, today.y + 1]) {
      const date = new Date(Date.UTC(year, month - 1, day));
      if (date.getUTCMonth() !== month - 1) return null;
      if (iso(date) >= `${today.y}-${String(today.m).padStart(2, '0')}-${String(today.d).padStart(2, '0')}`) return date;
    }
    return null;
  }

  // '20-22 nov', '20 al 22 de noviembre', '20/11 al 22/11' → {checkin, checkout} | {inverted} | null
  function parseStay(text) {
    const plain = norm(text);
    let a; let b;
    const numeric = [...plain.matchAll(/(\d{1,2})\/(\d{1,2})/g)];
    const ranged = plain.match(new RegExp(`(\\d{1,2})(?:\\s*(?:de\\s+)?(${MONTH_RE})\\b)?\\s*(?:al|a|hasta|-)\\s*(\\d{1,2})\\s*(?:de\\s+)?(${MONTH_RE})\\b`));
    if (numeric.length >= 2) {
      a = nextDate(+numeric[0][1], +numeric[0][2]);
      b = a && new Date(Date.UTC(a.getUTCFullYear(), +numeric[1][2] - 1, +numeric[1][1]));
    } else if (ranged) {
      const endMonth = MONTHS[ranged[4]];
      const startMonth = ranged[2] ? MONTHS[ranged[2]] : endMonth;
      a = nextDate(+ranged[1], startMonth);
      b = a && new Date(Date.UTC(a.getUTCFullYear() + (endMonth < startMonth ? 1 : 0), endMonth - 1, +ranged[3]));
    } else return null;
    if (!a || !b) return null;
    if (b <= a) return {inverted: true, checkin: iso(a), checkout: iso(b)};
    if ((b - a) / 86400000 > 30) return null;
    return {checkin: iso(a), checkout: iso(b)};
  }
  function parseGuests(text, data) {
    const plain = norm(text);
    const adults = plain.match(/(\d)\s*adult/);
    if (adults && +adults[1] >= 1 && +adults[1] <= 4) data.adults = +adults[1];
    if (/sin nin|no viajan nin|ningun nin/.test(plain)) data.children = 0;
    const kids = plain.match(/(\d)\s*nin/);
    if (kids && +kids[1] <= 3) data.children = +kids[1];
  }

  // ---------- motor guiado (mismas reglas, textos del servidor) ----------
  function conversation(db, sessionId, create) {
    if (!db.conversations[sessionId] && create) {
      db.conversations[sessionId] = {id: -(Object.keys(db.conversations).length + 1), step: 'start', data: {},
        messages: [], created_at: now()};
    }
    return db.conversations[sessionId] || null;
  }
  function add(db, conv, role, body, extra = {}) {
    db.seq.msg += 1;
    const message = {id: db.seq.msg, role, body, created_at: now(), options: extra.options || null,
      author: extra.author || null, kind: extra.kind || null};
    conv.messages.push(message);
    return message;
  }
  const say = (db, conv, text, options) => add(db, conv, 'assistant', text, {options});
  const openRequest = (db, conv) => db.requests.filter(r => r.conversation_id === conv.id && r.status !== 'cerrada').pop();
  const event = (db, conv, kind, payload = {}) => db.events.push({conversation_id: conv.id, kind, ts: now(), payload});

  function summary(db, conv) {
    const d = conv.data;
    const nights = Math.round((new Date(d.checkout) - new Date(d.checkin)) / 86400000);
    conv.step = 'confirm';
    say(db, conv, ['Revisa tu solicitud antes de enviarla:', `• Llegada: ${short(d.checkin)}`,
      `• Salida: ${short(d.checkout)} (${nights} ${nights === 1 ? 'noche' : 'noches'})`,
      `• Huéspedes: ${d.adults} ${d.adults === 1 ? 'adulto' : 'adultos'}, ${d.children} ${d.children === 1 ? 'niño' : 'niños'}`,
      '', 'Si algo no está bien, corrígelo antes de enviar.'].join('\n'),
    ['Enviar a recepción', 'Corregir fechas', 'Corregir huéspedes']);
  }
  function afterDates(db, conv) {
    const d = conv.data;
    if (!d.checkin) { conv.step = 'ask_dates'; say(db, conv, '¿Cuáles son tus fechas de llegada y salida? Por ejemplo «20 al 22 de noviembre».'); }
    else if (!d.adults) { conv.step = 'ask_adults'; say(db, conv, '¿Cuántos adultos viajan? (1 a 4)', ['1 adulto', '2 adultos', '3 adultos', '4 adultos']); }
    else if (d.children == null) { conv.step = 'ask_children'; say(db, conv, '¿Viajan niños?', ['Sin niños', '1 niño', '2 niños']); }
    else summary(db, conv);
  }
  function dates(db, conv, text) {
    parseGuests(text, conv.data);
    const stay = parseStay(text);
    if (stay && stay.inverted) {
      say(db, conv, `La salida (${short(stay.checkout)}) tiene que ser después de la llegada (${short(stay.checkin)}). ¿Me escribes de nuevo llegada y salida?`);
      return;
    }
    if (!stay) { say(db, conv, 'No logré entender las fechas. Escríbeme llegada y salida, por ejemplo «20 al 22 de noviembre».'); return; }
    Object.assign(conv.data, stay);
    afterDates(db, conv);
  }
  function handoff(db, conv, reason, scenario) {
    const shift = inShift(scenario);
    db.seq.req += 1;
    const t = now();
    const d = conv.data;
    const request = {id: db.seq.req, code: `VLL-${String(db.seq.req).padStart(3, '0')}`, conversation_id: conv.id,
      channel: 'demo', channel_label: 'WhatsApp simulado · versión estática', reason, reason_label: REASONS[reason],
      in_shift: shift, commercial_at: d.commercial_at || t, created_at: t, checkin: d.checkin || null,
      checkout: d.checkout || null, adults: d.adults ?? null, children: d.children ?? null, status: 'pendiente',
      reservation_status: 'pendiente_confirmacion', reservation_label: 'Pendiente de confirmación', assignee: null,
      taken_at: null, first_answer_at: null, last_guest_at: null, breached_at: null, closed_at: null, updated_at: t};
    db.requests.push(request);
    conv.step = 'handed_off';
    event(db, conv, 'request_created', {request_id: request.id, code: request.code, in_shift: shift});
    if (!shift) event(db, conv, 'night_capture', {complete: Boolean(d.checkin)});
    add(db, conv, 'note', ['Pre-información del copiloto (versión estática)', `Solicitud: ${request.code}`,
      `Fechas: ${d.checkin ? `${d.checkin} → ${d.checkout}` : 'sin fechas capturadas'}`,
      `Huéspedes: ${d.adults ? `${d.adults} adultos, ${d.children ?? '?'} niños` : 'sin huéspedes capturados'}`,
      `Motivo: ${REASONS[reason]}`].join('\n'));
    const pending = d.checkin ? ' · Disponibilidad por verificar: recepción revisa los cupos y te confirma.' : '';
    say(db, conv, shift
      ? `Solicitud enviada a recepción. Te responderán por aquí.\n\nN.º ${request.code}${pending}`
      : `Solicitud guardada: N.º ${request.code}. Recepción atiende de 08:00 a 22:00 (hora de Chile) y te responderá por aquí desde las ${nextOpening()}.`);
  }
  function guided(db, conv, text, scenario) {
    const plain = norm(text);
    if (conv.step === 'start') {
      say(db, conv, `Hola, soy el asistente virtual de ${HOTEL}. Te oriento con la ubicación, preguntas frecuentes y fechas; una persona de recepción revisa los cupos y confirma cada reserva. Es un chat de prueba con datos ficticios: no escribas datos personales reales.`);
      conv.step = 'menu';
    }
    const faq = FAQ.find(([pattern]) => pattern.test(plain));
    if (conv.step === 'confirm') {
      if (/enviar|^si\b|confirmo|listo/.test(plain)) return handoff(db, conv, 'commercial', scenario);
      if (/corregir fechas/.test(plain)) { delete conv.data.checkin; delete conv.data.checkout; conv.step = 'ask_dates'; return say(db, conv, 'Dale. ¿Cuáles son las fechas correctas de llegada y salida?'); }
      if (/corregir huespedes/.test(plain)) { delete conv.data.adults; delete conv.data.children; return afterDates(db, conv); }
      parseGuests(text, conv.data);
      const stay = parseStay(text);
      if (stay && !stay.inverted) Object.assign(conv.data, stay);
      return summary(db, conv);
    }
    if (/recepcion|persona|humano/.test(plain) && !/horario de recepcion/.test(plain)) return handoff(db, conv, 'human_requested', scenario);
    if (plain === 'preguntas frecuentes') { conv.step = 'menu'; return say(db, conv, 'Elige un tema o escríbeme tu pregunta:', ['Horario de check-in', 'Desayuno', 'Estacionamiento', 'Mascotas']); }
    if (plain === 'ubicacion') { conv.data.seen_location = true; return say(db, conv, 'Ubicación: Cerca de la costanera de Villarrica. A dos cuadras del lago y a 10 minutos caminando del centro (dato ficticio).'); }
    if (conv.step === 'ask_dates') return dates(db, conv, text);
    if (conv.step === 'ask_adults') { parseGuests(/adult/.test(plain) ? text : `${plain} adultos`, conv.data); return afterDates(db, conv); }
    if (conv.step === 'ask_children') {
      if (/^\d$/.test(plain)) conv.data.children = +plain; else parseGuests(text, conv.data);
      return afterDates(db, conv);
    }
    if (faq && plain !== 'consultar fechas') {
      event(db, conv, 'faq_answered', {faq_id: faq[2], inbound_ts: now()});
      if (faq[2] === 'ubicacion') conv.data.seen_location = true;
      return say(db, conv, faq[1]);
    }
    if (/consultar fechas|reserv|disponib|fechas/.test(plain) || parseStay(text)) {
      conv.data.commercial_at = conv.data.commercial_at || now();
      conv.step = 'ask_dates';
      if (!conv.data.seen_location) { conv.data.seen_location = true; say(db, conv, 'Antes de tus fechas, te cuento dónde estamos: Cerca de la costanera de Villarrica. A dos cuadras del lago (dato ficticio).'); }
      if (parseStay(text)) return dates(db, conv, text);
      return say(db, conv, '¿Para qué fechas? Escríbeme llegada y salida, por ejemplo «20 al 22 de noviembre» o «20/11 al 22/11».');
    }
    return say(db, conv, 'No estoy seguro de haberte entendido. Puedes usar los botones de abajo o escribir «recepción».');
  }

  // ---------- vistas (mismo contrato que el servidor) ----------
  function guestRequest(db, conv) {
    const request = db.requests.filter(r => r.conversation_id === conv.id).pop();
    if (!request) return null;
    const label = request.status === 'pendiente'
      ? (request.in_shift ? 'Enviada a recepción · te responderán por aquí' : `Guardada · recepción responde desde las ${nextOpening()}`)
      : request.status === 'en_atencion' ? `${request.assignee} de recepción está atendiendo tu solicitud`
        : request.status === 'respondida' ? `Respondida por ${request.assignee} · recepción`
          : 'Atención cerrada · puedes escribir una nueva consulta';
    return {code: request.code, status: request.status, label, assignee: request.assignee, in_shift: request.in_shift,
      open: request.status !== 'cerrada'};
  }
  function snapshot(db, conv, after = 0) {
    if (!conv) return {conversation_id: null, step: null, messages: [], request: null, handled_by: 'asistente', quick_replies: []};
    const request = guestRequest(db, conv);
    const handledBy = request && request.open ? 'recepcion' : 'asistente';
    const visible = conv.messages.filter(m => m.role !== 'note');
    const last = visible[visible.length - 1];
    return {conversation_id: conv.id, step: conv.step, messages: visible.filter(m => m.id > after), request,
      handled_by: handledBy, quick_replies: handledBy === 'asistente' && last && last.role === 'assistant' && last.options ? last.options : []};
  }
  function measurement(r) {
    if (!r.in_shift) return {state: 'fuera_de_turno', elapsed_s: null, target_s: 180, label: 'Fuera de turno: no cuenta para la meta de primera respuesta'};
    const clock = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    if (r.first_answer_at) {
      const s = Math.floor(r.first_answer_at - r.commercial_at);
      return {state: s < 180 ? 'cumplida' : 'vencida', elapsed_s: s, target_s: 180, label: `Primera respuesta en ${clock(s)} (${s < 180 ? 'dentro' : 'fuera'} de la meta)`};
    }
    const s = Math.floor(now() - r.commercial_at);
    return s >= 180 ? {state: 'vencida', elapsed_s: s, target_s: 180, label: `Sin respuesta pertinente tras ${clock(s)}: meta vencida`}
      : {state: 'en_curso', elapsed_s: s, target_s: 180, label: `Esperando primera respuesta · ${clock(s)}`};
  }
  function requestView(db, r, me) {
    const conv = Object.values(db.conversations).find(c => c.id === r.conversation_id);
    const nights = r.checkin ? Math.round((new Date(r.checkout) - new Date(r.checkin)) / 86400000) : null;
    const open = r.status !== 'cerrada';
    const preview = conv ? [...conv.messages].reverse().find(m => m.role !== 'note') : null;
    return {...r, nights, status_label: LABELS[r.status], measurement: measurement(r), contact_name: 'Huésped demo',
      preview: preview ? preview.body : null, messages: conv ? conv.messages : [],
      events: db.events.filter(e => e.conversation_id === r.conversation_id && e.ts >= r.commercial_at - 0.001),
      faq: db.events.filter(e => e.conversation_id === r.conversation_id && e.kind === 'faq_answered')
        .map(e => ({faq_id: e.payload.faq_id, latency_s: 0, met: true})),
      actions: {take: open && !r.assignee, reply: open && r.assignee === me, close: open && r.assignee === me,
        inventory: open && Boolean(r.checkin)}};
  }

  // ---------- rutas ----------
  const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {status, headers: {'content-type': 'application/json'}}));
  const staffName = () => { try { return window.sessionStorage.getItem('copiloto-static-staff'); } catch (_) { return null; } };
  const order = {pendiente: 0, en_atencion: 1, respondida: 2, cerrada: 3};

  function route(method, path, query, body) {
    const db = read();
    const me = staffName();
    if (path === '/api/demo/status') {
      return json({engine: 'static', hotel: {name: HOTEL, channel_label: 'WhatsApp simulado · versión estática'}, menu: MENU,
        shift: {start: SHIFT.start, end: SHIFT.end, timezone: TZ, in_shift: inShift(''), override: null, next_opening: nextOpening()},
        privacy_url: '', ai_enabled: false, mode: 'off', model: null, max_message_chars: 400, messages_per_session: 30});
    }
    if (path === '/api/demo/conversation') {
      return json(snapshot(db, conversation(db, query.get('session_id'), false), +(query.get('after') || 0)));
    }
    if (path === '/api/demo/chat' && method === 'POST') {
      const conv = conversation(db, body.session_id, true);
      conv.done = conv.done || [];
      if (body.client_message_id && conv.done.includes(body.client_message_id)) {
        return json({...snapshot(db, conv), reply: '', mode: 'duplicate', events: [], duplicate: true});
      }
      if (body.client_message_id) conv.done.push(body.client_message_id);
      const before = db.seq.msg;
      const request = openRequest(db, conv);
      const text = String(body.message || '').slice(0, 400);
      add(db, conv, 'guest', text);
      if (request) {
        request.last_guest_at = now();
        if (request.status === 'respondida') request.status = 'en_atencion';
      } else guided(db, conv, text, body.shift);
      write();
      const snap = snapshot(db, conv, before);
      return json({...snap, reply: snap.messages.filter(m => m.role === 'assistant').map(m => m.body).join('\n\n'),
        mode: request ? 'human' : 'guided', events: [{type: 'guided'}], duplicate: false, usage: {messages_left: null}});
    }
    if (path === '/api/demo/reset' && method === 'POST') {
      const conv = conversation(db, body.session_id, false);
      if (conv) {
        db.requests = db.requests.filter(r => r.conversation_id !== conv.id);
        delete db.conversations[body.session_id];
        write();
      }
      return json({status: 'ok'});
    }
    if (path === '/api/demo/session' && method === 'POST') {
      try { window.sessionStorage.setItem('copiloto-static-staff', (body && body.name) || 'Recepción (demo)'); } catch (_) { /* */ }
      return Promise.resolve(new Response(null, {status: 204}));
    }
    if (path.startsWith('/api/panel/') && !me) return json({detail: 'Sesión del panel requerida'}, 401);
    if (path === '/api/panel/requests') {
      const items = db.requests.map(r => requestView(db, r, me))
        .sort((a, b) => order[a.status] - order[b.status] || (a.status === 'cerrada' ? b.id - a.id : a.commercial_at - b.commercial_at));
      const selected = items.find(r => r.id === +query.get('selected')) || null;
      return json({now: now(), me, target_s: 180, amber_s: 120,
        shift: {start: SHIFT.start, end: SHIFT.end, in_shift: inShift(''), next_opening: nextOpening()}, requests: items, selected});
    }
    const match = path.match(/^\/api\/panel\/requests\/(\d+)(?:\/(take|reply|close|inventory))?$/);
    if (match) {
      const r = db.requests.find(item => item.id === +match[1]);
      if (!r) return json({detail: 'Solicitud no encontrada'}, 404);
      const conv = Object.values(db.conversations).find(c => c.id === r.conversation_id);
      const action = match[2];
      const conflict = detail => json({detail, request: requestView(db, r, me)}, 409);
      if (action === 'take') {
        if (r.assignee && r.assignee !== me) return conflict(`Ya la tomó ${r.assignee}`);
        if (!r.assignee) { Object.assign(r, {assignee: me, taken_at: now(), status: r.status === 'pendiente' ? 'en_atencion' : r.status}); event(db, conv, 'request_taken', {assignee: me}); }
      } else if (action === 'reply') {
        if (r.assignee !== me) return conflict(r.assignee ? `La atiende ${r.assignee}` : 'Toma la solicitud antes de responder');
        const text = String(body.body || '').trim().slice(0, 1000);
        if (!text) return json({detail: 'La respuesta debe tener entre 1 y 1000 caracteres'}, 400);
        conv.done = conv.done || [];
        if (body.client_id && conv.done.includes(`staff:${body.client_id}`)) return json({duplicate: true, message: null, request: requestView(db, r, me)});
        if (body.client_id) conv.done.push(`staff:${body.client_id}`);
        const message = add(db, conv, 'staff', text, {author: me, kind: body.kind === 'ack' ? 'ack' : 'answer'});
        if (body.kind === 'ack') event(db, conv, 'human_ack', {author: me});
        else {
          if (!r.first_answer_at) { r.first_answer_at = now(); event(db, conv, 'human_first_reply', {author: me}); }
          r.status = 'respondida';
        }
        write();
        return json({duplicate: false, message, request: requestView(db, r, me)});
      } else if (action === 'close') {
        Object.assign(r, {status: 'cerrada', closed_at: now()});
        conv.step = 'start';
        conv.data = {};
        event(db, conv, 'request_closed', {request_id: r.id});
      } else if (action === 'inventory') {
        if (!r.checkin) return conflict('La solicitud no tiene fechas: pídeselas al huésped');
        const t = localParts(now());
        const readAt = `${t.y}-${String(t.m).padStart(2, '0')}-${String(t.d).padStart(2, '0')}T${String(t.h).padStart(2, '0')}:${String(t.min).padStart(2, '0')}:00`;
        let result;
        if (body && body.simulate_down) result = {ok: false, reason: 'El inventario no respondió (caída simulada)'};
        else if (r.checkin < '2026-11-01' || r.checkout > '2027-04-01') result = {ok: false, reason: 'Sin dato de inventario para esas fechas: cupo desconocido'};
        else {
          const busy = r.checkin <= '2026-11-21' && r.checkout > '2026-11-20';
          const offers = [{code: 'doble', name: 'Habitación Doble', available_units: busy ? 1 : 3, nightly_price_clp: 58000}];
          if (!busy && (r.adults || 1) <= 2) offers.push({code: 'twin', name: 'Habitación Twin', available_units: 2, nightly_price_clp: 54000});
          result = {ok: true, source: 'Inventario de prueba (ficticio)', read_at: readAt, simulated: true, offers};
        }
        add(db, conv, 'note', result.ok ? `Inventario de prueba · lectura ${readAt.slice(11, 16)}: ${result.offers.map(o => `${o.name}: ${o.available_units} libre(s)`).join(', ')}. Preliminar: no bloquea cupos.`
          : `Inventario de prueba sin dato (${result.reason}). Cupo desconocido: no informar disponibilidad.`, {author: me});
        write();
        return json({...result, request: requestView(db, r, me)});
      }
      write();
      return json(requestView(db, r, me));
    }
    return json({detail: 'No disponible en la versión estática'}, 404);
  }

  window.fetch = (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    if (!url.pathname.startsWith('/api/')) return realFetch(input, init);
    let body = {};
    try { body = init.body ? JSON.parse(init.body) : {}; } catch (_) { body = {}; }
    return route((init.method || 'GET').toUpperCase(), url.pathname, url.searchParams, body);
  };

  // Sincroniza las pestañas: la bandeja de otra pestaña ve el mensaje nuevo en su próximo sondeo.
  window.addEventListener('storage', event => { if (event.key === KEY) memory = null; });
})();
