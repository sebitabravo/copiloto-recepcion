/* Versión estática de /demo (portfolio sin backend: Vercel, Netlify, GitHub Pages).
 *
 * Sustituye window.fetch SOLO para /api/*: la interfaz real (demo-shared/guest/inbox) corre igual contra
 * un servidor simulado en el navegador con el MISMO contrato que copiloto (solicitudes, tomar, responder,
 * cerrar, lectura del PMS simulado). El estado vive en localStorage, así que el chat en una pestaña y la
 * bandeja en otra de la misma corrida (?corrida=) comparten el caso; otras corridas quedan aisladas.
 * No hay IA, ni PMS, ni Chatwoot, ni datos de nadie:
 * el canal se rotula «WhatsApp simulado · versión estática» y el flujo es guiado, con textos preparados.
 */
(() => {
  'use strict';
  if (window.__STATIC_DEMO__) return;
  const KEY = 'copiloto-static-demo-v3';
  function newId() {
    if (window.DemoShared) return window.DemoShared.newId();
    const bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
    else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  }
  let activeRun = newId();
  const currentRun = () => new URL(window.location.href).searchParams.get('corrida') || activeRun;
  const stateKey = run => `${KEY}:${run}`;
  const staffKey = run => `${stateKey(run)}:staff`;
  const HOTEL = 'Hotel Boutique Bordeluz';
  const LOCATION = 'Estamos en el sector Molco, camino Villarrica-Pucón Km 12.5, frente a la playa Calfurray. Quedamos entre Villarrica y Pucón (12,5 km a cada una), a pocos metros de la playa.';
  // Parte del catálogo del PMS simulado (data/hotel.yaml) con cupos y tarifas ficticias.
  const ROOMS = [
    {code: 'single_doble_vista_jardin', name: 'Habitación Single Doble Vista Jardín', adults: 2, children: 0, price: 65000, units: 3},
    {code: 'doble_vista_piscina', name: 'Habitación Doble Vista Piscina', adults: 2, children: 1, price: 75000, units: 2},
    {code: 'doble_con_jacuzzi', name: 'Habitación Doble con Jacuzzi', adults: 2, children: 1, price: 80000, units: 2},
    {code: 'triple_vista_parcial_lago', name: 'Habitación Triple Vista Parcial Lago', adults: 3, children: 2, price: 90000, units: 2},
    {code: 'cuadruple_terraza_vista_al_lago', name: 'Habitación Cuádruple Terraza Vista al Lago', adults: 4, children: 3, price: 100000, units: 1}
  ];
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
  // Las mismas frases fijas del copiloto: un dato que no está en el catálogo se declara, no se inventa.
  const MISSING_DATA = 'Ese dato no lo tengo confirmado. Si quieres, lo consulto con recepción.';
  const IDENTITY = 'Soy el asistente virtual del hotel, una IA: te ayudo con la ubicación, los servicios y las '
    + 'fechas, y una persona de recepción confirma cada reserva.';
  const GREETING = /^(hola|holi|buenas|buen dia|buenos dias|buenas tardes|buenas noches|hey|ola|que tal)$/;
  // Derivar es una acción del huésped (hablar, pasar, atender con una persona), no una pregunta sobre el bot.
  const WANTS_HUMAN = /(hablar|hablo|pasar|comunicar|contactar|deriva|derivame|atienda|atiendan|atender|necesito|quiero|llama)/;
  const HUMAN_TARGET = /(persona|humano|recepci|agente|alguien real)/;
  const ASKS_IDENTITY = /(eres|es usted|sos|es un|es una)\s+(una\s+|un\s+)?(persona|humano|ia|inteligencia artificial|robot|bot|maquina|asistente virtual)/;
  const IDENTITY_TOPIC = /(eres|sos|es usted).*(ia|robot|bot|maquina|humano|persona)/;
  // Respuestas aprobadas: las mismas de data/hotel.yaml que usa el copiloto.
  const FAQ = [
    [/donde|ubicaci|direcci|como llego|llegar/, `Ubicación: ${LOCATION}`, 'ubicacion'],
    [/piscina|pileta|nadar/, 'Tenemos piscina temperada, disponible durante todo el año y incluida en tu estadía.', 'piscina'],
    [/check.?in|check.?out|hora de llegada/, 'El check-in es desde las 15:00 y el check-out hasta las 12:00. Early check-in o late check-out dependen de disponibilidad y tienen costo.', 'checkin'],
    [/desayun/, 'Todas las habitaciones incluyen desayuno continental (buffet en temporada alta), en un comedor con vista al lago.', 'desayuno'],
    [/estaciona|parking|auto/, 'Las habitaciones cuentan con estacionamiento.', 'estacionamiento'],
    [/mascota|perro|gato/, 'La política de mascotas no está publicada en nuestro sitio. Recepción te confirma si es posible.', 'mascotas'],
    [/wifi|internet/, 'Las habitaciones tienen WiFi, aire acondicionado y calefacción, baño privado en suite y televisor.', 'wifi']
  ];
  const LABELS = {pendiente: 'Pendiente de recepción', en_atencion: 'En atención', respondida: 'Respondida', cerrada: 'Cerrada'};
  const REASONS = {commercial: 'Consulta de fechas', human_requested: 'Pidió hablar con recepción'};
  // Con `aiChat` (lo escribe el build cuando hay LLM_API_KEY) la respuesta conversacional la da la
  // función de Vercel; el resto del flujo sigue siendo determinista y local. Se lee en cada turno
  // porque `config.js` se carga después de este archivo.
  const aiChatEnabled = () => (window.COPILOTO_CONFIG || {}).aiChat === true;
  const realFetch = window.fetch.bind(window);
  window.__STATIC_DEMO__ = {get key() { return stateKey(currentRun()); }};

  // ---------- estado compartido solo entre pestañas de la misma corrida ----------
  const empty = () => ({conversations: {}, requests: [], events: [], seq: {msg: 0, req: 0}});
  function load(key) {
    try { return JSON.parse(window.localStorage.getItem(key)) || empty(); } catch (_) { return empty(); }
  }
  function save(key, db) { try { window.localStorage.setItem(key, JSON.stringify(db)); } catch (_) { /* */ } }

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

  const money = value => `$${value.toLocaleString('es-CL')}`;
  function readAt() {
    const t = localParts(now());
    const pad = n => String(n).padStart(2, '0');
    return `${t.y}-${pad(t.m)}-${pad(t.d)}T${pad(t.h)}:${pad(t.min)}:00`;
  }
  // Lectura simulada del PMS: capacidad del catálogo y un cupo menos en las noches del 20 y 21 de noviembre.
  function reading(d) {
    const busy = d.checkin <= '2026-11-21' && d.checkout > '2026-11-20';
    const offers = ROOMS.filter(room => room.adults >= d.adults && room.children >= (d.children || 0))
      .map(room => ({code: room.code, name: room.name, available_units: room.units - (busy ? 1 : 0),
        nightly_price_clp: room.price}))
      .filter(offer => offer.available_units > 0);
    return {read_at: readAt(), offers};
  }
  function summary(db, conv) {
    const d = conv.data;
    const nights = Math.round((new Date(d.checkout) - new Date(d.checkin)) / 86400000);
    const pms = reading(d);
    d.read_at = pms.read_at;
    conv.step = 'confirm';
    const r = pms.read_at;
    const when = `${r.slice(11, 16)} del ${r.slice(8, 10)}-${r.slice(5, 7)}-${r.slice(0, 4)}`;
    const availability = pms.offers.length
      ? [`Disponible según lectura del PMS a las ${when} (PMS simulado):`,
        ...pms.offers.slice(0, 3).map(o => `• ${o.name.replace(/^Habitación /, '')}: ${money(o.nightly_price_clp)} por noche · quedan ${o.available_units}`),
        'Es una lectura preliminar: recepción confirma cupo y precio, y nada queda reservado todavía.'].join('\n')
      : `Según lectura del PMS a las ${when} no veo cupo para esas fechas y huéspedes. Recepción revisará alternativas.`;
    const stay = ['Revisa tu solicitud antes de enviarla:', `• Llegada: ${short(d.checkin)}`,
      `• Salida: ${short(d.checkout)} (${nights} ${nights === 1 ? 'noche' : 'noches'})`,
      `• Huéspedes: ${d.adults} ${d.adults === 1 ? 'adulto' : 'adultos'}, ${d.children} ${d.children === 1 ? 'niño' : 'niños'}`];
    say(db, conv, [stay.join('\n'), availability, 'Si algo no está bien, corrígelo antes de enviar.'].join('\n\n'),
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
    // `shift`: ¿recepción atiende al derivar? (mensaje al huésped). `intake`: turno al ingreso (decide la meta).
    const shift = inShift(scenario);
    const intake = conv.data.commercial_in_shift ?? shift;
    db.seq.req += 1;
    const t = now();
    const d = conv.data;
    const request = {id: db.seq.req, code: `BDL-${String(db.seq.req).padStart(3, '0')}`, conversation_id: conv.id,
      channel: 'demo', channel_label: 'WhatsApp simulado · versión estática', reason, reason_label: REASONS[reason],
      in_shift: shift, intake_in_shift: intake, commercial_at: d.commercial_at || t, created_at: t, checkin: d.checkin || null,
      checkout: d.checkout || null, adults: d.adults ?? null, children: d.children ?? null, status: 'pendiente',
      reservation_status: 'pendiente_confirmacion', reservation_label: 'Pendiente de confirmación', assignee: null,
      taken_at: null, first_answer_at: null, last_guest_at: null, breached_at: null, closed_at: null, updated_at: t};
    db.requests.push(request);
    conv.step = 'handed_off';
    event(db, conv, 'request_created', {request_id: request.id, code: request.code, in_shift: intake});
    if (!intake) event(db, conv, 'night_capture', {complete: Boolean(d.checkin), request_id: request.id});
    add(db, conv, 'note', ['Pre-información del copiloto (versión estática)', `Solicitud: ${request.code}`,
      `Fechas: ${d.checkin ? `${d.checkin} → ${d.checkout}` : 'sin fechas capturadas'}`,
      `Huéspedes: ${d.adults ? `${d.adults} adultos, ${d.children ?? '?'} niños` : 'sin huéspedes capturados'}`,
      `Motivo: ${REASONS[reason]}`].join('\n'));
    const pending = d.read_at ? ' · La lectura del PMS es preliminar: recepción confirma cupo y precio.'
      : d.checkin ? ' · Disponibilidad por verificar: recepción revisa los cupos y te confirma.' : '';
    say(db, conv, shift
      ? `Solicitud enviada a recepción. Te responderán por aquí.\n\nN.º ${request.code}${pending}`
      : `Solicitud guardada: N.º ${request.code}. Recepción atiende de 08:00 a 22:00 (hora de Chile) y te responderá por aquí desde las ${nextOpening()}.`);
  }
  function guided(db, conv, text, scenario) {
    const plain = norm(text);
    if (conv.step === 'start') {
      say(db, conv, `Hola, soy el asistente virtual de ${HOTEL}. Te oriento con la ubicación, preguntas frecuentes y fechas; una persona de recepción revisa los cupos y confirma cada reserva. Es un chat de prueba: no escribas datos personales reales.`);
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
    if (ASKS_IDENTITY.test(plain) || IDENTITY_TOPIC.test(plain)) return say(db, conv, IDENTITY);
    if (GREETING.test(plain)) return say(db, conv, 'Hola, bienvenido. ¿Te ayudo con la ubicación, alguna pregunta del hotel o las fechas de tu estadía?', MENU);
    // Escribir solo «recepción» o pulsar el botón del menú también es pedir a una persona.
    const humanAsked = ((WANTS_HUMAN.test(plain) && HUMAN_TARGET.test(plain)) || /^(la )?recepcion$/.test(plain)
      || /hablar con recepcion/.test(plain) || /persona real/.test(plain)) && !/horario de recepcion/.test(plain);
    if (humanAsked) return handoff(db, conv, 'human_requested', scenario);
    if (plain === 'preguntas frecuentes') { conv.step = 'menu'; return say(db, conv, 'Elige un tema o escríbeme tu pregunta:', ['Piscina', 'Desayuno', 'Horario de check-in', 'Estacionamiento']); }
    if (plain === 'ubicacion') { conv.data.seen_location = true; return say(db, conv, `Ubicación: ${LOCATION}`); }
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
      // Ingreso de la consulta comercial: su hora y su turno quedan fijos (el turno al derivar puede ser otro).
      if (!conv.data.commercial_at) { conv.data.commercial_at = now(); conv.data.commercial_in_shift = inShift(scenario); }
      conv.step = 'ask_dates';
      if (!conv.data.seen_location) { conv.data.seen_location = true; say(db, conv, `Antes de tus fechas, te cuento dónde estamos: ${LOCATION}`); }
      if (parseStay(text)) return dates(db, conv, text);
      return say(db, conv, '¿Para qué fechas? Escríbeme llegada y salida, por ejemplo «20 al 22 de noviembre» o «20/11 al 22/11».');
    }
    return say(db, conv, MISSING_DATA, MENU);
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
    if (!r.intake_in_shift) return {state: 'fuera_de_turno', elapsed_s: null, target_s: 180, label: 'Fuera de turno: no cuenta para la meta de primera respuesta'};
    const clock = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    if (r.first_answer_at) {
      const s = Math.floor(r.first_answer_at - r.commercial_at);
      return {state: s < 180 ? 'cumplida' : 'vencida', elapsed_s: s, target_s: 180, label: `Primera respuesta en ${clock(s)} (${s < 180 ? 'dentro' : 'fuera'} de la meta)`};
    }
    const s = Math.floor(now() - r.commercial_at);
    return s >= 180 ? {state: 'vencida', elapsed_s: s, target_s: 180, label: `Sin respuesta pertinente tras ${clock(s)}: meta vencida`}
      : {state: 'en_curso', elapsed_s: s, target_s: 180, label: `Esperando primera respuesta · ${clock(s)}`};
  }
  const owned = (r, operator) => Boolean(operator && r.assignee_id === operator);
  function requestView(db, r, operator) {
    const conv = Object.values(db.conversations).find(c => c.id === r.conversation_id);
    const nights = r.checkin ? Math.round((new Date(r.checkout) - new Date(r.checkin)) / 86400000) : null;
    const open = r.status !== 'cerrada';
    const preview = conv ? [...conv.messages].reverse().find(m => m.role !== 'note') : null;
    return {...r, nights, status_label: LABELS[r.status], measurement: measurement(r), contact_name: 'Huésped demo',
      preview: preview ? preview.body : null, messages: conv ? conv.messages : [],
      events: db.events.filter(e => e.conversation_id === r.conversation_id && e.ts >= r.commercial_at - 0.001),
      faq: db.events.filter(e => e.conversation_id === r.conversation_id && e.kind === 'faq_answered')
        .map(e => ({faq_id: e.payload.faq_id, latency_s: 0, met: true})),
      actions: {take: open && !r.assignee, reply: open && owned(r, operator), close: open && owned(r, operator),
        inventory: open && Boolean(r.checkin)}};
  }

  // ---------- rutas ----------
  const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {status, headers: {'content-type': 'application/json'}}));
  const staffSession = run => {
    try { return JSON.parse(window.sessionStorage.getItem(staffKey(run))); } catch (_) { return null; }
  };
  const order = {pendiente: 0, en_atencion: 1, respondida: 2, cerrada: 3};

  // Híbrido: las reglas mandan. Primero el menú y las respuestas aprobadas (FAQ); después el tramo
  // comercial (fechas, disponibilidad, propuesta, derivación), que tiene que ser determinista. Lo que
  // ninguna regla cubre lo responde el modelo, y si el modelo no está, cae en la frase de dato ausente.
  const MENU_COMMANDS = /^(ubicacion|consultar fechas|preguntas frecuentes|hablar con recepcion)$/;
  const COMMERCIAL = /consultar fechas|reserv|disponib|\bfechas\b|habitaci|recepcion|persona real/;
  const STEP_BUSY = new Set(['ask_dates', 'ask_adults', 'ask_children', 'confirm', 'handed_off']);
  function handledLocally(conv, text) {
    const plain = norm(text);
    if (STEP_BUSY.has(conv.step)) return true;
    if (MENU_COMMANDS.test(plain)) return true;
    if (FAQ.some(([pattern]) => pattern.test(plain))) return true;
    return COMMERCIAL.test(plain);
  }

  async function aiReply(conv, text) {
    const history = conv.messages.slice(-8).map(m => ({role: m.role === 'guest' ? 'guest' : 'assistant', text: m.body}));
    try {
      const response = await realFetch('/api/demo/chat', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({message: text, history}),
      });
      if (response.status === 429) return {busy: true};
      // 503 es «la IA no está configurada»: ahí manda el guion de siempre. 502/504 son del proveedor o
      // del tiempo: se avisa y se invita a repetir, nunca se dice que falta el dato.
      if (response.status === 503) return null;
      if (response.status >= 500) return {busy: true, retry: true};
      if (!response.ok) return null;
      const data = await response.json();
      if (typeof data.reply !== 'string' || !data.reply.trim()) return null;
      return {reply: data.reply.trim(), stay: data.stay || null, offers: data.offers || null,
        handoff: data.handoff || null};
    } catch (_) {
      return null;
    }
  }

  async function route(method, path, query, body, headers) {
    const headerRun = headers && (typeof headers.get === 'function' ? headers.get('X-Demo-Run')
      : Object.entries(headers).find(([name]) => name.toLowerCase() === 'x-demo-run')?.[1]);
    const run = body.run || query.get('run') || headerRun || currentRun();
    const key = stateKey(run);
    // Leer cada vez permite ver cambios de otra pestaña sin mantener una caché global entre corridas.
    const db = load(key);
    const write = () => save(key, db);
    const staff = staffSession(run);
    const me = staff && staff.name;
    const operator = staff && staff.operator;
    const view = r => requestView(db, r, operator);
    if (path === '/api/demo/status') {
      return json({engine: 'static', hotel: {name: HOTEL, channel_label: 'WhatsApp simulado · versión estática'}, menu: MENU,
        shift: {start: SHIFT.start, end: SHIFT.end, timezone: TZ, in_shift: inShift(''), override: null, next_opening: nextOpening()},
        privacy_url: '', ai_enabled: false, mode: 'off', model: null, max_message_chars: 400, messages_per_session: 30});
    }
    // La corrida también es el namespace del almacenamiento, no solo una etiqueta para la URL.
    if (path === '/api/demo/run' && method === 'POST') {
      activeRun = `estatica-${newId().replace(/-/g, '').slice(0, 16)}`;
      return json({run: activeRun, ttl_s: 86400}, 201);
    }
    if (path.startsWith('/api/demo/run/')) {
      activeRun = decodeURIComponent(path.slice('/api/demo/run/'.length));
      return json({run: activeRun});
    }
    if (path === '/api/demo/conversation') {
      return json(snapshot(db, conversation(db, query.get('session_id'), false), +(query.get('after') || 0)));
    }
    if (path === '/api/demo/chat' && method === 'POST') {
      const conv = conversation(db, body.session_id, true);
      const firstText = String(body.message || '').slice(0, 400);
      // Con IA configurada, la conversación la lleva el modelo: entiende las fechas como las dice una
      // persona («el próximo fin de semana», «en dos semanas») y devuelve la estadía normalizada.
      // Solo la derivación explícita se resuelve en local, porque crea la solicitud en la bandeja.
      const plainText = norm(body.message);
      // Crear la solicitud es una acción de estado: la hace el flujo local, no el modelo. Se dispara con
      // el botón «Enviar a recepción», con un «sí» cuando ya hay una estadía lista, o cuando el huésped
      // pide hablar con una persona.
      const sending = /^enviar a recepcion$/.test(plainText)
        || (conv.step === 'confirm' && /^(si|dale|ya|ok|okey|listo|enviar|enviar a recepcion|confirmo|perfecto)/.test(plainText));
      const wantsHuman = sending
        || (/^(la )?recepcion$/.test(plainText) || /hablar con recepcion/.test(plainText)
          || /persona real/.test(plainText)
          || (WANTS_HUMAN.test(plainText) && HUMAN_TARGET.test(plainText))) && !/horario de recepcion/.test(plainText);
      // Con la solicitud en recepción, el modelo igual responde dudas simples (sin tocarla); la derivación
      // explícita sigue siendo local.
      if (aiChatEnabled() && !wantsHuman) {
        // Primero se pide la respuesta; si llega, se guardan los turnos de una vez. Si no, sigue el guion.
        const answer = await aiReply(conv, firstText);
        if (answer && answer.busy) {
          // El modelo no contestó (ráfaga o caída): se dice con naturalidad y no se pierde el turno.
          const before = db.seq.msg;
          const line = answer.retry
            ? 'Uy, se me cortó la conexión un segundo. ¿Me lo repites?'
            : 'Uy, estoy viendo varias consultas a la vez. ¿Me lo repites en un momento?';
          add(db, conv, 'guest', firstText);
          add(db, conv, 'assistant', line, {options: MENU});
          write();
          return json({...snapshot(db, conv, before), reply: line,
            mode: 'busy', events: [{type: 'ai'}], duplicate: false, usage: {messages_left: null}});
        }
        if (answer) {
          const before = db.seq.msg;
          if (conv.step === 'start') {
            // Primer turno: la bienvenida y el aviso de privacidad salen igual que en el guion.
            say(db, conv, `Hola, soy el asistente virtual de ${HOTEL}. Te oriento con la ubicación, preguntas frecuentes y fechas; una persona de recepción revisa los cupos y confirma cada reserva. Es un chat de prueba: no escribas datos personales reales.`);
            conv.step = 'menu';
          }
          add(db, conv, 'guest', firstText);
          const abierta = openRequest(db, conv);
          if (abierta) {
            // Si recepción tiene la solicitud, el mensaje igual queda en el hilo que ella ve.
            abierta.last_guest_at = now();
            if (abierta.status === 'respondida') abierta.status = 'en_atencion';
          }
          // Con disponibilidad, el modelo ya contó las opciones y el precio: solo faltan los botones para
          // confirmar o corregir. Sin disponibilidad, el turno queda abierto con el menú.
          // Si ya hay una estadía registrada, los botones de confirmar siguen a mano aunque el turno
          // conteste otra cosa (una mascota, una duda): el huésped no pierde el «Enviar a recepción».
          const confirmar = (answer.offers || conv.step === 'confirm')
            ? ['Enviar a recepción', 'Corregir fechas', 'Corregir huéspedes']
            : MENU;
          add(db, conv, 'assistant', answer.reply, {options: confirmar});
          if (answer.stay) {
            Object.assign(conv.data, answer.stay);
            if (answer.offers) {
              conv.data.offers = answer.offers;
              conv.step = 'confirm';
            } else {
              summary(db, conv);
            }
          }
          if (answer.handoff) {
            // El modelo pidió pasar la solicitud: la crea el flujo local, con su número y su nota.
            if (answer.handoff.name) conv.data.name = answer.handoff.name;
            handoff(db, conv, 'human_requested', body.shift);
          }
          write();
          const snap = snapshot(db, conv, before);
          return json({...snap, reply: answer.reply, mode: 'ai', events: [{type: 'ai'}], duplicate: false,
            usage: {messages_left: null}});
        }
      }
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
      const identity = body.operator_key || (window.DemoShared && window.DemoShared.operatorKey())
        || operator || newId();
      try {
        window.sessionStorage.setItem(staffKey(run), JSON.stringify({name: body.name || 'Recepción (demo)', operator: identity}));
      } catch (_) { /* */ }
      return Promise.resolve(new Response(null, {status: 204}));
    }
    if (path.startsWith('/api/panel/') && !me) return json({detail: 'Sesión del panel requerida'}, 401);
    if (path === '/api/panel/requests') {
      const items = db.requests.map(view)
        // Mismo orden que el servidor: abiertas por espera (empate: la que llegó antes), cerradas al final.
        .sort((a, b) => order[a.status] - order[b.status]
          || (a.status === 'cerrada' ? b.id - a.id : a.commercial_at - b.commercial_at || a.id - b.id));
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
      const conflict = detail => json({detail, request: view(r)}, 409);
      if (action === 'take') {
        if (r.status === 'cerrada') return conflict('La solicitud está cerrada');
        if (r.assignee && !owned(r, operator)) return conflict(`Ya la tomó ${r.assignee}`);
        if (!r.assignee) { Object.assign(r, {assignee: me, assignee_id: operator, taken_at: now(), status: r.status === 'pendiente' ? 'en_atencion' : r.status}); event(db, conv, 'request_taken', {assignee: me}); }
      } else if (action === 'reply') {
        if (r.status === 'cerrada') return conflict('La solicitud está cerrada');
        if (!owned(r, operator)) return conflict(r.assignee ? `La atiende ${r.assignee}` : 'Toma la solicitud antes de responder');
        const text = String(body.body || '').trim().slice(0, 1000);
        if (!text) return json({detail: 'La respuesta debe tener entre 1 y 1000 caracteres'}, 400);
        conv.done = conv.done || [];
        if (body.client_id && conv.done.includes(`staff:${body.client_id}`)) return json({duplicate: true, message: null, request: view(r)});
        if (body.client_id) conv.done.push(`staff:${body.client_id}`);
        const message = add(db, conv, 'staff', text, {author: me, kind: body.kind === 'ack' ? 'ack' : 'answer'});
        if (body.kind === 'ack') event(db, conv, 'human_ack', {author: me});
        else {
          if (!r.first_answer_at) { r.first_answer_at = now(); event(db, conv, 'human_first_reply', {author: me}); }
          r.status = 'respondida';
        }
        write();
        return json({duplicate: false, message, request: view(r)});
      } else if (action === 'close') {
        if (!owned(r, operator)) return conflict(r.assignee ? `La atiende ${r.assignee}` : 'Toma la solicitud antes de cerrar');
        if (r.status === 'cerrada') return json(view(r));
        Object.assign(r, {status: 'cerrada', closed_at: now()});
        conv.step = 'start';
        conv.data = {};
        event(db, conv, 'request_closed', {request_id: r.id});
      } else if (action === 'inventory') {
        if (!r.checkin) return conflict('La solicitud no tiene fechas: pídeselas al huésped');
        let result;
        if (body && body.simulate_down) result = {ok: false, reason: 'el PMS no respondió (caída simulada)'};
        else {
          const pms = reading(r);
          result = {ok: true, source: 'PMS simulado', read_at: pms.read_at, simulated: true, offers: pms.offers};
        }
        const offersText = result.ok
          ? result.offers.map(o => `${o.name}: ${o.available_units} libre(s)`).join(', ') || 'sin cupo' : '';
        add(db, conv, 'note', result.ok
          ? `PMS simulado · lectura ${result.read_at.slice(11, 16)}: ${offersText}. Preliminar: no bloquea cupos.`
          : `Disponibilidad por verificar: PMS sin lectura (${result.reason}). No informar cupos al huésped.`, {author: me});
        write();
        return json({...result, request: view(r)});
      }
      write();
      return json(view(r));
    }
    return json({detail: 'No disponible en la versión estática'}, 404);
  }

  // La voz no se simula: `/api/demo/tts` siempre viaja a la función de Vercel (ElevenLabs). Si no está
  // configurada responde 503 y la llamada usa la voz del navegador.
  const PASS_THROUGH = new Set(['/api/demo/tts']);

  window.fetch = (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    if (!url.pathname.startsWith('/api/')) return realFetch(input, init);
    if (PASS_THROUGH.has(url.pathname)) return realFetch(input, init);
    let body = {};
    try { body = init.body ? JSON.parse(init.body) : {}; } catch (_) { body = {}; }
    return route((init.method || 'GET').toUpperCase(), url.pathname, url.searchParams, body, init.headers);
  };
})();
