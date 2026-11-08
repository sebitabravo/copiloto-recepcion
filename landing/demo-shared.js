/* Piezas compartidas por el chat del huésped y la bandeja de recepción de /demo.
   Sin dependencias: API con tiempo límite, llaves de idempotencia, formatos y render del hilo.
   Todo texto del servidor entra como textContent: nada se interpreta como HTML. */
(() => {
  'use strict';
  const config = window.COPILOTO_CONFIG || {};
  const TZ = 'America/Santiago';

  // Demo por LAN: si la página no corre en localhost pero la config sí apunta ahí, se usa el host de la
  // página conservando el puerto (y el protocolo, para no mezclar http dentro de https).
  function resolveUrl(raw) {
    try {
      const url = new URL(String(raw), location.href);
      const local = host => host === 'localhost' || host === '127.0.0.1';
      if (!local(location.hostname) && local(url.hostname)) {
        url.hostname = location.hostname;
        url.protocol = location.protocol;
      }
      return url.toString().replace(/\/+$/, '');
    } catch (_) { return String(raw).replace(/\/+$/, ''); }
  }
  const configured = typeof config.copilotoUrl === 'string' && config.copilotoUrl !== '';
  const base = configured ? resolveUrl(config.copilotoUrl) : (config.staticDemo ? '' : resolveUrl('http://localhost:8100'));

  class ApiError extends Error {
    constructor(status, message, data) { super(message); this.status = status; this.data = data || {}; }
  }

  function friendly(status, data) {
    if (status === 0) return 'No pudimos conectar con el servidor de la demo. Revisa la conexión y reintenta.';
    if (status === 401) return 'La sesión de recepción venció. Vuelve a entrar a la bandeja.';
    if (status === 409) return (data && data.detail) || 'La solicitud cambió mientras tanto. Ya se actualizó.';
    if (status === 429) return 'Se alcanzó un límite temporal de la demo. Espera unos segundos y reintenta.';
    if (status === 400 || status === 422) return (data && data.detail) || 'Revisa el texto: no se pudo enviar.';
    return 'El servidor de la demo no respondió bien. Reintenta en unos segundos.';
  }

  async function api(path, {method = 'GET', body, staff = false, timeout = 15000} = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const options = {method, cache: 'no-store', signal: controller.signal,
      // El huésped nunca manda la cookie de recepción: cada rol viaja con su propia credencial.
      credentials: staff ? 'include' : 'omit'};
    if (body !== undefined) {
      options.headers = {'Content-Type': 'application/json'};
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(base + path, options);
    } catch (_) {
      throw new ApiError(0, controller.signal.aborted ? 'El servidor tardó demasiado. Reintenta.' : friendly(0));
    } finally { clearTimeout(timer); }
    let data = {};
    if (response.status !== 204) {
      try { data = await response.json(); } catch (_) { data = {}; }
    }
    if (!response.ok) throw new ApiError(response.status, friendly(response.status, data), data);
    return data;
  }

  // Llave de idempotencia por acción: [A-Za-z0-9-]{8,64}. Un reintento reutiliza la misma.
  function newId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
    else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  }

  const store = {
    get(area, key) { try { return window[area].getItem(key); } catch (_) { return null; } },
    set(area, key, value) { try { window[area].setItem(key, value); } catch (_) { /* sigue en memoria */ } }
  };

  const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const timeFormat = new Intl.DateTimeFormat('es-CL', {hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: TZ});
  const dateTimeFormat = new Intl.DateTimeFormat('es-CL',
    {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: TZ});

  const time = epoch => (epoch ? timeFormat.format(new Date(epoch * 1000)) : '');
  const dateTime = epoch => (epoch ? dateTimeFormat.format(new Date(epoch * 1000)).replace('.', '') : '');
  const isoParts = iso => { const [y, m, d] = String(iso).split('-').map(Number); return {y, m, d}; };

  // '2026-11-20','2026-11-22' → '20–22 nov'; meses distintos → '30 dic – 2 ene'.
  function stayRange(checkin, checkout) {
    if (!checkin || !checkout) return null;
    const a = isoParts(checkin);
    const b = isoParts(checkout);
    if (a.m === b.m && a.y === b.y) return `${a.d}–${b.d} ${MONTHS[a.m - 1]}`;
    return `${a.d} ${MONTHS[a.m - 1]} – ${b.d} ${MONTHS[b.m - 1]}`;
  }

  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  function guests(request) {
    if (request.adults == null) return null;
    const kids = request.children == null ? 'niños sin informar' : plural(request.children, 'niño', 'niños');
    return `${plural(request.adults, 'adulto', 'adultos')} · ${kids}`;
  }

  // Resumen de una línea para la lista: fechas y adultos, o el motivo si aún no hay datos.
  function summary(request) {
    const stay = stayRange(request.checkin, request.checkout);
    if (!stay) return request.reason_label || 'Sin datos de estadía';
    return request.adults ? `${stay} · ${plural(request.adults, 'adulto', 'adultos')}` : stay;
  }

  function clock(seconds) {
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
  }

  const TONES = {pendiente: 'amber', en_atencion: 'blue', respondida: 'green', cerrada: 'grey'};
  const tone = status => TONES[status] || 'grey';

  // Espera en vivo: el servidor manda elapsed_s; se suma lo que pasó desde esa lectura.
  function liveElapsed(measurement, fetchedAt, now = Date.now()) {
    if (!measurement || measurement.elapsed_s == null) return null;
    if (measurement.state !== 'en_curso' && measurement.state !== 'vencida') return measurement.elapsed_s;
    return measurement.elapsed_s + Math.max(0, (now - fetchedAt) / 1000);
  }

  function waitTone(seconds, amber, red) {
    if (seconds == null) return '';
    if (seconds >= red) return 'red';
    if (seconds >= amber) return 'amber';
    return '';
  }

  // Una línea en blanco separa ideas: cada idea es una burbuja (como escribe una persona).
  const splitParagraphs = text => String(text).split(/\n[ \t]*\n/).map(part => part.trim()).filter(Boolean);

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  // Texto corto para un enlace: «Abrir en Google Maps» en vez de la URL completa.
  function linkLabel(url) {
    if (/^https:\/\/www\.google\.[a-z.]+\/maps/i.test(url)) return 'Abrir en Google Maps';
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch (_) { return url; }
  }

  // Párrafo con las URL http(s) como enlaces seguros: nodos de texto y <a>, nunca HTML del servidor.
  function richParagraph(text) {
    const paragraph = el('p');
    const value = String(text);
    let last = 0;
    for (const match of value.matchAll(/https?:\/\/[^\s<>"']+/g)) {
      if (match.index > last) paragraph.append(document.createTextNode(value.slice(last, match.index)));
      const link = el('a', '', linkLabel(match[0]));
      link.href = match[0];
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      paragraph.append(link);
      last = match.index + match[0].length;
    }
    if (last < value.length) paragraph.append(document.createTextNode(value.slice(last)));
    return paragraph;
  }

  /* Mensaje del hilo. `view`: 'guest' (el huésped no ve notas internas) o 'staff'.
     Orientación igual en ambas vistas: el huésped a la derecha, asistente y recepción a la izquierda. */
  function messageNodes(message, view, previousRole) {
    const nodes = [];
    if (message.role === 'note') {
      if (view !== 'staff') return nodes;
      const note = el('div', 'memo');
      note.append(el('b', '', 'Nota interna · solo recepción'), el('p', '', message.body));
      nodes.push(note);
      return nodes;
    }
    const parts = message.role === 'assistant' ? splitParagraphs(message.body) : [String(message.body)];
    parts.forEach((part, index) => {
      const outgoing = message.role === 'guest';
      const continued = index > 0 || previousRole === message.role;
      const bubble = el('article', `chat-bubble ${outgoing ? 'out' : 'in'} ${message.role}${continued ? ' cont' : ''}`);
      bubble.dataset.id = message.id;
      if (!continued || (message.role === 'staff' && index === 0)) {
        if (message.role === 'assistant') bubble.append(el('span', 'who', 'Asistente virtual'));
        if (message.role === 'staff') bubble.append(el('span', 'who', `${message.author || 'Recepción'} · Recepción`));
        if (message.role === 'guest' && view === 'staff') bubble.append(el('span', 'who', 'Huésped'));
      }
      bubble.append(message.role === 'guest' ? el('p', '', part) : richParagraph(part));
      if (index === parts.length - 1) {
        const meta = el('span', 'meta');
        if (view === 'staff' && message.kind === 'ack') meta.append(el('span', 'tag', 'acuse'));
        meta.append(el('time', '', time(message.created_at)));
        if (outgoing) meta.append(el('span', 'ticks', '✓✓'));
        bubble.append(meta);
      }
      nodes.push(bubble);
    });
    return nodes;
  }

  window.DemoShared = {
    api, ApiError, newId, store, time, dateTime, stayRange, guests, summary, clock, tone, liveElapsed,
    waitTone, splitParagraphs, el, messageNodes, base
  };
})();
