import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../landing/demo.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../landing/demo.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../landing/demo.css', import.meta.url), 'utf8');
const indexHtml = readFileSync(new URL('../landing/index.html', import.meta.url), 'utf8');
const consoleSource = readFileSync(new URL('../landing/console.js', import.meta.url), 'utf8');

test('proposal-only tool trace does not claim booking registration', async () => {
  const ui = await app({}, [{
    reply: 'Propuesta pendiente de confirmación.',
    events: [{type: 'tool_call', name: 'create_booking', ok: true,
      summary: 'Propuesta pendiente de confirmación', arguments: {}}],
    quick_replies: []
  }]);
  await ui.send('Soy Camila Rojas');
  const trace = ui.get('timeline').textContent;
  assert.match(trace, /Propuesta pendiente de confirmación/);
  assert.doesNotMatch(trace, /Registró una reserva/);
});

// Minimal DOM fixture: real event handlers, tree queries and text rendering, no network.
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.listeners = {}; this.dataset = {};
    this.value = ''; this.hidden = false; this.disabled = false; this.className = '';
    this.attributes = {}; this.ownText = ''; this.style = {setProperty() {}};
    this.classList = {
      add: name => { this.className += ` ${name}`; },
      remove: name => { this.className = this.className.split(' ').filter(x => x !== name).join(' '); },
      toggle: (name, on) => on ? this.classList.add(name) : this.classList.remove(name)
    };
  }
  set textContent(value) { this.ownText = String(value); this.children = []; }
  get textContent() { return this.ownText + this.children.map(x => x.textContent).join(' '); }
  get lastElementChild() { return this.children.at(-1) || null; }
  getAttribute(key) { return key in this.attributes ? this.attributes[key] : null; }
  append(...nodes) {
    for (let node of nodes) {
      if (typeof node === 'string') { const text = new Element('#text'); text.textContent = node; node = text; }
      node.remove(); node.parentElement = this; this.children.push(node);
    }
  }
  appendChild(node) { this.append(node); }
  insertBefore(node, reference) {
    if (reference === null) { this.append(node); return node; }
    node.remove();
    const index = this.children.indexOf(reference);
    if (index < 0) throw new Error('NotFoundError: reference is not a child');
    node.parentElement = this; this.children.splice(index, 0, node); return node;
  }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(x => x !== this); }
  replaceChildren(...nodes) { this.children = []; this.ownText = ''; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  async emit(name, event = {}) { if (this.disabled) return; for (const fn of this.listeners[name] || []) await fn({preventDefault() {}, ...event}); }
  focus() { this.focusCalls = (this.focusCalls || 0) + 1; }
  contains(node) { return this === node || this.children.some(child => child.contains(node)); }
  matches(selector) { return selector.startsWith('.') ? this.className.split(' ').includes(selector.slice(1)) : this.tagName === selector; }
  querySelectorAll(selector) {
    const parts = selector.split(' ');
    const descendants = this.children.flatMap(node => [node, ...node.querySelectorAll('*')]);
    if (selector === '*') return descendants;
    return descendants.filter(node => node.matches(parts.at(-1)) && (parts.length === 1 || node.parentElement?.matches(parts[0])));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

async function app(status = {}, responses = [], options = {}) {
  const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
  const get = id => ids.get(id);
  get('actions-panel').hidden = true;
  for (const id of ['chat-error', 'status-error']) get(id).append(new Element('span'), new Element('button'));
  const scenarios = ['info', 'booking', 'human'].map(name => { const el = new Element('button'); el.dataset.scenario = name; return el; });
  const grid = new Element(); const sent = []; const requests = [];
  const document = {
    getElementById: get, createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag),
    createTextNode: text => { const node = new Element('#text'); node.textContent = text; return node; },
    body: new Element(), documentElement: {scrollHeight: 1000}, addEventListener() {},
    querySelectorAll: selector => selector === '[data-scenario]' ? scenarios : [],
    querySelector: selector => selector === '.demo-grid' ? grid : scenarios.find(el => selector === `[data-scenario="${el.dataset.scenario}"]`)
  };
  // Skip decorative scrolling only; chat and all scenario handlers execute unchanged.
  ids.delete('topbar'); ids.delete('hero-stage');
  const pendingTimers = []; const timerDelays = [];
  const window = {
    COPILOTO_CONFIG: options.config || {}, matchMedia: () => ({matches: !options.animate}), crypto: {randomUUID: () => '12345678-1234-1234-1234-123456789012'},
    sessionStorage: {getItem() {}, setItem() {}}, addEventListener() {},
    setInterval() {}, clearTimeout() {},
    setTimeout: options.manualTimers ? (fn, ms) => { if (ms < 90000) { pendingTimers.push(fn); timerDelays.push(ms); } return 1; }
      : (fn, ms) => { if (ms < 90000) queueMicrotask(fn); return 1; }
  };
  vm.runInNewContext(source, {window, document, Intl, Date, Uint8Array, AbortController, URL,
    location: options.location || {hostname: 'localhost', protocol: 'http:'},
    fetch: async (url, options) => {
      requests.push(url);
      const body = options.body && JSON.parse(options.body);
      let data = {ai_enabled: true, autonomous_booking: true, sandbox: true, ...status};
      if (url.endsWith('/chat')) { sent.push(body.message); data = responses.shift() || {reply: 'Réponse de test', events: [], quick_replies: []}; }
      return {ok: true, json: async () => data};
    }});
  const settle = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
  await settle();
  return {get, scenarios, sent, requests, settle, document, window, timerDelays,
    flushTimers: () => { while (pendingTimers.length) pendingTimers.shift()(); },
    scripts: () => document.body.querySelectorAll('script'),
    async send(text) { get('message-input').value = text; await get('chat-form').emit('submit'); await settle(); }};
}

// Burbujas del asistente que siguen al último mensaje del huésped.
const assistantBubbles = ui => {
  const items = ui.get('messages').children;
  const lastUser = items.findLastIndex(node => node.className.split(' ').includes('user'));
  return items.slice(lastUser + 1).filter(node => node.className.split(' ').includes('assistant'));
};
const descendants = node => node.querySelectorAll('*');

test('a reply splits on blank lines into at most three bubbles, rendered safely', async () => {
  const ui = await app({}, [{
    reply: 'Hola, *bienvenido*.\n\nTenemos piscina <img src=x onerror=alert(1)>\ny spa.\n\nTres.\n\nCuatro.',
    events: [], quick_replies: ['¿Cómo llego?']
  }]);
  await ui.send('Hola');
  const bubbles = assistantBubbles(ui);
  assert.equal(bubbles.length, 3);
  assert.match(bubbles[0].textContent, /Hola,/);
  // *texto* es negrita al estilo WhatsApp, sin asteriscos a la vista.
  const bold = descendants(bubbles[0]).filter(node => node.tagName === 'b');
  assert.deepEqual(bold.map(node => node.textContent), ['bienvenido']);
  assert.doesNotMatch(bubbles[0].textContent, /\*/);
  // El HTML del servidor queda como texto: ningún elemento <img> y el salto de línea se conserva.
  assert.ok(descendants(bubbles[1]).every(node => node.tagName !== 'img'));
  assert.match(bubbles[1].textContent, /<img src=x onerror=alert\(1\)>\ny spa\./);
  // Lo que sobra de tres ideas va en la última burbuja.
  assert.match(bubbles[2].textContent, /Tres\.\n\nCuatro\./);
  // Solo la primera lleva la punta; las respuestas rápidas cuelgan de la última.
  assert.deepEqual(bubbles.map(node => node.className.includes('continued')), [false, true, true]);
  assert.equal(bubbles[2].querySelectorAll('.quick-replies').length, 1);
  assert.equal(bubbles[0].querySelectorAll('.quick-replies').length, 0);
  // El lector de pantalla recibe la respuesta completa, en texto plano.
  assert.match(ui.get('assistant-announcement').textContent, /Hola, bienvenido\..*Cuatro\./s);
});

test('**markdown** bold and a reply without blank lines stay in one formatted bubble', async () => {
  const ui = await app({}, [{reply: 'La *Suite Jardín* cuesta **$80.000** por noche.\n2 * 3 no es negrita.', events: []}]);
  await ui.send('Precio');
  const bubbles = assistantBubbles(ui);
  assert.equal(bubbles.length, 1);
  const bold = descendants(bubbles[0]).filter(node => node.tagName === 'b').map(node => node.textContent);
  assert.deepEqual(bold, ['Suite Jardín', '$80.000']);
  assert.match(bubbles[0].textContent, /2 \* 3 no es negrita/);
});

test('bubbles arrive one after another with the typing indicator and a capped pause', async () => {
  const long = 'x'.repeat(400);
  const ui = await app({}, [{reply: `Primera idea.\n\nSegunda.\n\n${long}`, events: [], quick_replies: ['¿Cómo llego?']}],
    {animate: true, manualTimers: true});
  await ui.send('Hola');
  assert.equal(assistantBubbles(ui).length, 1, 'la segunda burbuja espera su pausa');
  assert.equal(ui.get('typing').hidden, false, 'el indicador de escritura aparece entre burbujas');
  assert.equal(ui.get('messages').lastElementChild, ui.get('typing'), 'y cae al final del historial');
  assert.equal(ui.get('messages').querySelectorAll('.quick-replies').length, 0, 'sin sugerencias hasta la última');
  ui.flushTimers(); await ui.settle();
  ui.flushTimers(); await ui.settle();
  assert.equal(assistantBubbles(ui).length, 3);
  assert.equal(ui.get('typing').hidden, true);
  const pauses = ui.timerDelays.slice(0, 2);
  assert.ok(pauses[0] > 0 && pauses[0] < pauses[1], `pausa proporcional al largo: ${pauses}`);
  assert.equal(pauses[1], 1200, 'tope de 1,2 s');
  assert.equal(assistantBubbles(ui)[2].querySelectorAll('.quick-replies').length, 1);
});

test('reduced motion shows every bubble at once, without typing pauses', async () => {
  const ui = await app({}, [{reply: 'Uno.\n\nDos.', events: []}], {manualTimers: true});
  await ui.send('Hola');
  assert.equal(assistantBubbles(ui).length, 2);
  assert.deepEqual(ui.timerDelays, []);
});

test('the welcome is two human bubbles and keeps the privacy note at the top of the chat', async () => {
  const assisted = await app({mode: 'assisted', autonomous_booking: false});
  const greeting = assistantBubbles(assisted);
  assert.equal(greeting.length, 2);
  assert.equal(greeting[0].textContent.split(' ').slice(0, -1).join(' ').trim(), 'Hola, bienvenido a Hotel Bordeluz.');
  assert.match(greeting[1].textContent, /^Soy el asistente de recepción, una IA: te ayudo con ubicación, servicios y disponibilidad\. Las reservas las confirma una persona del equipo\./);
  assert.doesNotMatch(assisted.get('messages').textContent, /no tengo permiso|con IA de Hotel/);
  assert.equal(greeting[1].querySelectorAll('.quick-replies').length, 1);
  // Aviso de privacidad antes de preguntar: dentro del historial, visible con IA.
  const note = assisted.get('ai-disclaimer');
  assert.equal(note.parentElement, assisted.get('messages'));
  assert.equal(note.hidden, false);
  const guided = await app({ai_enabled: false, autonomous_booking: false});
  assert.match(assistantBubbles(guided)[0].textContent, /^Hola, bienvenido a Hotel Bordeluz\./);
  assert.match(assistantBubbles(guided)[1].textContent, /sin IA/);
  // Reiniciar el historial conserva el aviso al inicio de la conversación.
  await assisted.send('hola'); await assisted.get('reset').emit('click'); await assisted.settle();
  assert.equal(assisted.get('ai-disclaimer').parentElement, assisted.get('messages'));
});

test('response time stays hidden until the server measured one', async () => {
  const ui = await app({}, [{reply: 'Sin medición', events: []}, {reply: 'Medida', events: [], usage: {llm_ms: 1234}}]);
  assert.equal(ui.get('response-time').hidden, true);
  await ui.send('uno');
  assert.equal(ui.get('response-time').hidden, true);
  await ui.send('dos');
  assert.equal(ui.get('response-time').hidden, false);
  assert.equal(ui.get('response-time').textContent, 'Respuesta en 1,23 s');
  assert.match(html, /<span id="response-time" hidden>/);
});

test('the booking capability appears in the trace only in full mode, with a one-row scenario label', async () => {
  for (const [status, hidden] of [[{mode: 'full'}, false], [{mode: 'assisted'}, true], [{ai_enabled: false}, true]]) {
    const ui = await app(status);
    assert.equal(ui.get('trace-booking').hidden, hidden, JSON.stringify(status));
  }
  assert.match(html, /<span class="scenario-label">Disponibilidad sin reservar<\/span>/);
  assert.match(source, /bookingLabel\.textContent = 'Disponibilidad sin reservar'/);
});

test('demo page carries canonical, Open Graph, Twitter, theme color and no fixed localhost links', () => {
  for (const pattern of [/<link rel="canonical" href="__PUBLIC_SITE_URL__\/demo">/, /property="og:locale" content="es_CL"/,
    /property="og:image" content="__PUBLIC_SITE_URL__\/og-image\.png"/, /name="twitter:card" content="summary_large_image"/,
    /name="theme-color"/, /rel="icon" href="\/favicon\.svg"/, /application\/ld\+json/]) assert.match(html, pattern);
  // C4: la URL pública sale de PUBLIC_SITE_URL, que Nginx sustituye al servir; nunca un host fijo.
  assert.match(readFileSync(new URL('../infra/landing/nginx.conf', import.meta.url), 'utf8'), /sub_filter "__PUBLIC_SITE_URL__"/);
  assert.equal(html.match(/__PUBLIC_SITE_URL__/g).length, 6, 'canonical, og:url, og:image, twitter:image y las dos del JSON-LD');
  assert.doesNotMatch(html, /localhost/);
  // Solo un aviso de modo demo: el antiguo «Demo con IA. Todo es ficticio» ya no se repite en la columna.
  assert.doesNotMatch(html, /Todo es ficticio/);
});

test('voice talk button keeps its microphone icon and labels itself for assistive tech', async () => {
  const voice = readFileSync(new URL('../landing/voice.js', import.meta.url), 'utf8');
  const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
  const icon = new Element('svg');
  ids.get('voice-talk').append(icon);
  const window = {COPILOTO_CONFIG: {}, SpeechRecognition: function Recognition() {},
    sessionStorage: {getItem() {}, setItem() {}}, setInterval() { return 1; }, clearInterval() {},
    setTimeout() { return 1; }, clearTimeout() {}};
  vm.runInNewContext(voice, {window, document: {getElementById: id => ids.get(id), createElement: tag => new Element(tag)}, AbortController,
    fetch: async url => ({ok: true, json: async () => (url.includes('greeting') ? {text: 'Hola.'} : {voice: true})})});
  await ids.get('voice-start').emit('click');
  for (let i = 0; i < 100; i++) await Promise.resolve();
  const talk = ids.get('voice-talk');
  assert.equal(talk.hidden, false);
  assert.deepEqual(talk.children, [icon], 'el icono no se reemplaza por texto');
  assert.equal(talk.attributes['aria-label'], 'Tocar para hablar');
  assert.equal(ids.get('voice-state').textContent, 'Tu turno: toca el micrófono o escribe abajo.');
});

async function consoleApp(conversations, snapshot = {}, options = {}) {
  const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
  const body = new Element('body');
  const get = id => ids.get(id) || body.querySelectorAll('*').find(node => node.id === id || node.getAttribute('id') === id);
  const tablist = new Element();
  tablist.append(...['huesped', 'recepcion', 'admin'].map(name => get(`tab-${name}`)));
  body.append(tablist, get('panel-huesped'), get('panel-recepcion'), get('panel-admin'));
  const container = get('recepcion-console');
  get('panel-recepcion').append(container);
  // Explicitly exercise both sides of the A/B seam, independent of the checked-in HTML.
  ids.delete('reception-tools');
  if (options.toolsHost) { const host = new Element(); host.id = 'reception-tools'; container.append(host); }
  container.append(get('recepcion-summary'), get('recepcion-state'), get('recepcion-detail'));
  if (!options.detachedQueue) container.append(get('recepcion-queue'));
  get('recepcion-detail').append(get('recepcion-back'), get('recepcion-detail-body'));
  const requests = []; const intervals = new Map(); const pollDelays = []; const stored = [];
  let timerId = 0;
  const window = {COPILOTO_CONFIG: {}, localStorage: {getItem() { return options.mode === false ? '0' : null; }, setItem(...args) { stored.push(args); }},
    setInterval(fn, delay) { pollDelays.push(delay); intervals.set(++timerId, fn); return timerId; },
    clearInterval(id) { intervals.delete(id); }};
  const document = {body, getElementById: get, createElement: tag => new Element(tag), querySelectorAll: () => []};
  vm.runInNewContext(consoleSource, {window, document, Intl, Date,
    fetch: async (url, init = {}) => {
      const request = {path: new URL(url).pathname, ...init, method: init.method || 'GET'};
      requests.push(request);
      if (options.respond) {
        const response = await options.respond(request, requests);
        if (response) return response;
      }
      const data = url.endsWith('/api/panel/queue') ? {conversations, amber_s: 120, red_s: 180} :
        url.includes('/api/panel/') ? snapshot : {demo: options.available !== false};
      return {ok: true, status: 200, json: async () => data};
    }});
  const settle = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
  await settle();
  if (options.enter !== false) { await get('tab-recepcion').emit('click'); await settle(); }
  return {get, settle, container, requests, intervals, pollDelays, stored,
    async change(id, value, event = 'input') { get(id).value = value; await get(id).emit(event); await settle(); },
    async click(id) { await get(id).emit('click'); await settle(); },
    async poll() { for (const fn of intervals.values()) fn(); await settle(); }};
}

test('reception queue names anonymous visitors, reads long waits in hours and summarizes risk', async () => {
  const ui = await consoleApp([
    {conversation_id: 7, contact_name: 'cool-mountain-791', waiting_s: 38296, step: 'handed_off'},
    {conversation_id: 8, contact_name: 'Camila Rojas', waiting_s: 150},
    {conversation_id: 9, contact_name: '', waiting_s: 30},
    {conversation_id: 10, contact_name: 'Huésped Demo', waiting_s: null}
  ], {contact_name: 'cool-mountain-791', sla: {started_at: 1000, red_s: 180}, now: 39296, step: 'handed_off', data: {}});
  const queue = ui.get('recepcion-queue');
  assert.equal(queue.hidden, false);
  const names = queue.querySelectorAll('b').map(node => node.textContent);
  assert.deepEqual(names, ['Visitante web · 791', 'Camila Rojas', 'Conversación 9', 'Huésped Demo']);
  const waits = queue.querySelectorAll('.risk').map(node => node.textContent);
  assert.deepEqual(waits, ['10 h 38 min', '2:30', '0:30', '—']);
  assert.doesNotMatch(queue.textContent, /638:16|cool-mountain/);
  const summary = ui.get('recepcion-summary');
  assert.equal(summary.hidden, false);
  assert.equal(summary.textContent, '4 conversaciones 1 vencida 1 por vencer 1 en plazo');
  // El detalle usa el mismo nombre y una insignia de SLA legible.
  await queue.querySelectorAll('button')[0].emit('click');
  await ui.settle();
  const detail = ui.get('recepcion-detail-body');
  assert.equal(summary.hidden, true);
  assert.match(detail.textContent, /Visitante web · 791/);
  assert.match(detail.querySelectorAll('.risk-badge')[0].textContent, /Plazo vencido: responder ya · 10 h 38 min/);
  assert.equal(detail.querySelectorAll('.console-notes-title').length, 1);
});

// Unsorted API order is deliberate: the UI must neither sort nor mutate these records.
const triageQueue = () => [
  {conversation_id: 41, contact_name: 'cool-mountain-791', waiting_s: 180, needs_human: true, step: 'handed_off'},
  {conversation_id: 9, contact_name: 'Camila Rojas', waiting_s: 120, step: 'ask_dates'},
  {conversation_id: 17, contact_name: 'Camila Soto', waiting_s: 181, needs_human: true, step: 'menu'},
  {conversation_id: 2, contact_name: 'En espera', waiting_s: 119, needs_human: true, step: 'pick_room'},
  {conversation_id: 88, contact_name: '', waiting_s: 0, needs_human: false},
  {conversation_id: 3, contact_name: '<img src=x onerror=alert(1)>', waiting_s: null, step: '<script>bad()</script>'}
];
const queueNames = ui => ui.get('recepcion-queue').querySelectorAll('b').map(node => node.textContent);
const allQueueNames = ['Visitante web · 791', 'Camila Rojas', 'Camila Soto', 'En espera', 'Conversación 88', '<img src=x onerror=alert(1)>'];
const fullSummary = '6 conversaciones 2 vencidas 1 por vencer 2 en plazo';
const assertReadOnly = ui => {
  assert.equal(ui.requests.filter(req => req.method === 'POST').length, 1, 'only the existing mocked session POST');
  assert.ok(ui.requests.every(req => (req.path === '/api/demo/session' && ['GET', 'POST'].includes(req.method)) ||
    (req.path.startsWith('/api/panel/') && req.method === 'GET')), 'no operational writes or unexpected endpoints');
  for (const req of ui.requests.filter(req => req.path.startsWith('/api/panel/'))) {
    assert.equal(req.method, 'GET'); assert.equal(req.body, undefined);
    assert.equal(req.credentials, 'include'); assert.equal(req.cache, 'no-store');
  }
};

test('triage controls have labels, live counts and API provenance in the optional host or fallback', async () => {
  for (const [toolsHost, detachedQueue] of [[false, false], [true, false], [false, true]]) {
    const ui = await consoleApp(triageQueue(), {}, {toolsHost, detachedQueue});
    const toolbar = ui.container.querySelector('.queue-toolbar');
    assert.ok(toolbar, 'reception gets a toolbar without requiring HTML changes');
    assert.equal(toolbar.hidden, false);
    assert.equal(toolbar.parentElement, toolsHost ? ui.get('reception-tools') : ui.container);
    const labels = toolbar.querySelectorAll('label');
    for (const [id, label] of [['queue-search', 'Buscar en la cola'], ['queue-filter', 'Prioridad']]) {
      assert.equal(labels.find(node => node.getAttribute('for') === id)?.textContent, label);
      const help = ui.get(ui.get(id).getAttribute('aria-describedby'));
      assert.match(help.textContent, /locales.*fuente: GET \/api\/panel\/queue.*orden del servidor/);
    }
    assert.equal(ui.get('queue-search').type, 'search');
    assert.deepEqual(ui.get('queue-filter').children.map(node => [node.value, node.textContent]),
      [['all', 'Todas'], ['human', 'Necesita una persona'], ['warn', 'Por vencer'], ['bad', 'Vencidas']]);
    assert.equal(ui.get('queue-refresh').textContent, 'Actualizar cola');
    assert.equal(ui.get('queue-refresh').type, 'button');
    const count = ui.get('queue-result-count');
    assert.equal(count.getAttribute('role'), 'status');
    assert.equal(count.getAttribute('aria-live'), 'polite');
    assert.equal(count.textContent, 'Mostrando 6 de 6 conversaciones');
    assert.deepEqual(queueNames(ui), allQueueNames);
    assertReadOnly(ui);
  }
});

test('search intersects human and exact SLA filters locally, preserving full totals, order and safe text', async () => {
  const sourceQueue = triageQueue(); const original = JSON.stringify(sourceQueue);
  const ui = await consoleApp(sourceQueue);
  const requestsBefore = ui.requests.length;
  for (const [filter, names] of [
    ['human', [allQueueNames[0], 'Camila Soto', 'En espera']],
    ['warn', ['Camila Rojas']], ['bad', [allQueueNames[0], 'Camila Soto']], ['all', allQueueNames]
  ]) {
    await ui.change('queue-filter', filter, 'change');
    assert.deepEqual(queueNames(ui), names, filter);
    assert.equal(ui.get('queue-result-count').textContent, `Mostrando ${names.length} de 6 conversaciones`);
    assert.equal(ui.get('recepcion-summary').textContent, fullSummary);
  }
  await ui.change('queue-search', '  CAMILA  ');
  assert.deepEqual(queueNames(ui), ['Camila Rojas', 'Camila Soto']);
  for (const [filter, name] of [['human', 'Camila Soto'], ['warn', 'Camila Rojas'], ['bad', 'Camila Soto']]) {
    await ui.change('queue-filter', filter, 'change');
    assert.deepEqual(queueNames(ui), [name]);
    assert.equal(ui.get('queue-result-count').textContent, 'Mostrando 1 de 6 conversaciones');
    assert.equal(ui.get('recepcion-summary').textContent, fullSummary);
  }
  await ui.change('queue-filter', 'all', 'change');
  for (const [query, name] of [['Visitante web', allQueueNames[0]], ['791', allQueueNames[0]], ['88', 'Conversación 88'],
    ['eligiendo habitación', 'En espera'], ['pick_room', 'En espera'], ['<img', allQueueNames[5]]]) {
    await ui.change('queue-search', query);
    assert.deepEqual(queueNames(ui), [name], query);
  }
  assert.equal(ui.get('recepcion-queue').querySelectorAll('img').length, 0);
  assert.equal(ui.get('recepcion-queue').querySelectorAll('script').length, 0);
  assert.match(ui.get('recepcion-queue').textContent, /<script>bad\(\)<\/script>/);
  await ui.change('queue-search', '');
  assert.deepEqual(queueNames(ui), allQueueNames);
  assert.equal(ui.get('queue-result-count').textContent, 'Mostrando 6 de 6 conversaciones');
  assert.equal(JSON.stringify(sourceQueue), original);
  assert.equal(ui.requests.length, requestsBefore, 'criteria changes never fetch or write');
  assertReadOnly(ui);
});

test('unmatched local criteria differ from an empty backend and keep refresh available', async () => {
  const ui = await consoleApp(triageQueue());
  await ui.change('queue-search', 'nadie coincide');
  assert.deepEqual(queueNames(ui), []);
  assert.equal(ui.get('queue-result-count').textContent, 'Mostrando 0 de 6 conversaciones');
  const empty = ui.container.querySelector('.queue-filter-empty');
  assert.equal(empty.hidden, false);
  assert.equal(empty.textContent, 'No hay coincidencias con esta búsqueda y filtro. Cambia los criterios para ver más conversaciones.');
  assert.equal(ui.get('recepcion-state').hidden, true);
  assert.equal(ui.get('recepcion-summary').textContent, fullSummary);
  await ui.change('queue-search', '');
  assert.equal(empty.hidden, true);
  assert.deepEqual(queueNames(ui), allQueueNames);
  const backend = await consoleApp([]);
  assert.equal(backend.get('recepcion-state').hidden, false);
  assert.equal(backend.get('recepcion-state').textContent, 'Sin conversaciones todavía. Cuando un huésped escriba, aparece acá.');
  assert.equal(backend.get('recepcion-queue').hidden, true);
  assert.equal(backend.container.querySelector('.queue-filter-empty').hidden, true);
  assert.equal(backend.container.querySelector('.queue-toolbar').hidden, false);
  assert.equal(backend.get('queue-result-count').textContent, 'Mostrando 0 de 0 conversaciones');
  assert.equal(backend.get('recepcion-summary').textContent, '0 conversaciones');
  const before = backend.requests.length;
  await backend.click('queue-refresh');
  assert.equal(backend.requests.length, before + 1);
  assertReadOnly(ui); assertReadOnly(backend);
});

test('detail/back and explicit refresh retain criteria and hide tools while loading or reading detail', async () => {
  let release; let defer = false;
  const conversations = triageQueue();
  const ui = await consoleApp(conversations, {
    contact_name: 'Camila Soto', step: 'menu', data: {}, notes: [{body: '<b>Nota segura</b>', author: 'Turno', created_at: 1000}]
  }, {respond: req => {
    if (defer && req.path === '/api/panel/queue') return new Promise(resolve => { release = resolve; });
  }});
  await ui.change('queue-search', 'Camila'); await ui.change('queue-filter', 'human', 'change');
  await ui.get('recepcion-queue').querySelector('button').emit('click'); await ui.settle();
  const toolbar = ui.container.querySelector('.queue-toolbar');
  assert.equal(toolbar.hidden, true);
  assert.equal(ui.get('recepcion-detail').hidden, false);
  assert.match(ui.get('recepcion-detail-body').textContent, /Camila Soto.*menú.*<b>Nota segura<\/b>/);
  assert.equal(ui.requests.at(-1).path, '/api/panel/17');
  await ui.click('recepcion-back');
  assert.equal(toolbar.hidden, false);
  assert.equal(ui.get('queue-search').value, 'Camila');
  assert.equal(ui.get('queue-filter').value, 'human');
  assert.deepEqual(queueNames(ui), ['Camila Soto']);
  defer = true;
  const refreshing = ui.click('queue-refresh');
  await ui.settle();
  assert.equal(toolbar.hidden, true);
  assert.equal(ui.get('recepcion-summary').hidden, true);
  assert.equal(ui.get('recepcion-queue').hidden, true);
  assert.equal(ui.get('recepcion-state').textContent, 'Consultando la cola de recepción…');
  release({ok: true, status: 200, json: async () => ({conversations: [...conversations,
    {conversation_id: 29, contact_name: 'Camila Nueva', needs_human: true, waiting_s: 30}], amber_s: 120, red_s: 180})});
  await refreshing; await ui.settle();
  assert.equal(toolbar.hidden, false);
  assert.deepEqual(queueNames(ui), ['Camila Soto', 'Camila Nueva']);
  assert.equal(ui.get('queue-result-count').textContent, 'Mostrando 2 de 7 conversaciones');
  assert.equal(ui.get('recepcion-summary').textContent, '7 conversaciones 2 vencidas 1 por vencer 3 en plazo');
  assert.equal(ui.get('queue-search').value, 'Camila'); assert.equal(ui.get('queue-filter').value, 'human');
  assertReadOnly(ui);
});

test('existing tab keys, deferred admin and single queue poll preserve triage criteria', async () => {
  const ui = await consoleApp(triageQueue(), {}, {enter: false});
  assert.equal(ui.get('admin-frame').getAttribute('src'), null);
  assert.equal(ui.intervals.size, 0);
  await ui.click('tab-recepcion'); await ui.click('tab-recepcion');
  assert.equal(ui.intervals.size, 1); assert.deepEqual(ui.pollDelays, [10000]);
  await ui.change('queue-filter', 'bad', 'change');
  await ui.poll();
  assert.deepEqual(queueNames(ui), [allQueueNames[0], 'Camila Soto']);
  assert.equal(ui.get('queue-filter').value, 'bad');
  await ui.click('tab-huesped');
  assert.equal(ui.intervals.size, 0);
  const before = ui.requests.length; await ui.poll(); assert.equal(ui.requests.length, before);
  await ui.get('tab-huesped').parentElement.emit('keydown', {key: 'End'}); await ui.settle();
  assert.equal(ui.get('tab-admin').getAttribute('aria-selected'), 'true');
  assert.equal(ui.get('tab-admin').focusCalls, 1);
  assert.equal(ui.get('panel-admin').hidden, false);
  assert.equal(ui.get('admin-frame').getAttribute('src'), 'http://localhost:8200/admin?demo=1');
  await ui.click('tab-recepcion');
  assert.equal(ui.intervals.size, 1);
  assert.deepEqual(queueNames(ui), [allQueueNames[0], 'Camila Soto']);
  await ui.get('recepcion-queue').querySelector('button').emit('click'); await ui.settle();
  const detailRequests = ui.requests.length; await ui.poll(); assert.equal(ui.requests.length, detailRequests);
  await ui.click('tab-huesped'); await ui.click('tab-recepcion');
  assert.equal(ui.requests.at(-1).path, '/api/panel/41', 'return to reception refreshes the selected detail');
  assertReadOnly(ui);
});

test('existing session gates and queue retry errors hide triage without bypassing access', async () => {
  const off = await consoleApp(triageQueue(), {}, {mode: false});
  assert.match(off.get('recepcion-state').textContent, /^Modo demo desactivado:/);
  assert.equal(off.container.querySelector('.queue-toolbar').hidden, true);
  assert.ok(off.requests.every(req => req.method === 'GET' && !req.path.startsWith('/api/panel/')));
  const disabled = await consoleApp(triageQueue(), {}, {available: false});
  assert.equal(disabled.get('demo-mode-switch').disabled, true);
  assert.match(disabled.get('demo-banner-text').textContent, /^Demo deshabilitada en el servidor:/);
  let ready;
  const starting = await consoleApp(triageQueue(), {}, {respond: req => {
    if (req.path === '/api/demo/session' && req.method === 'POST') return new Promise(resolve => { ready = resolve; });
  }});
  assert.equal(starting.get('recepcion-state').textContent, 'Preparando la sesión de recepción…');
  assert.equal(starting.container.querySelector('.queue-toolbar').hidden, true);
  assert.ok(starting.requests.every(req => !req.path.startsWith('/api/panel/')));
  ready({ok: true, status: 200}); await starting.settle();
  assert.deepEqual(queueNames(starting), allQueueNames);
  assertReadOnly(starting);
  for (const [status, message] of [[403, 'Demo deshabilitada en el servidor:'], [404, 'Demo deshabilitada en el servidor:'],
    [429, 'Límite temporal de la demo alcanzado.'], [500, 'No se pudo conectar con el servidor de recepción.'], [0, 'No se pudo conectar con el servidor de recepción.']]) {
    let fail = true;
    const ui = await consoleApp(triageQueue(), {}, {respond: req => {
      if (fail && req.path === '/api/demo/session' && req.method === 'POST') {
        if (!status) throw new Error('mock offline');
        return {ok: false, status};
      }
    }});
    assert.ok(ui.get('recepcion-state').textContent.startsWith(message), status);
    assert.equal(ui.container.querySelector('.queue-toolbar').hidden, true);
    assert.ok(ui.requests.every(req => !req.path.startsWith('/api/panel/')));
    fail = false;
    await ui.get('recepcion-state').querySelector('button').emit('click'); await ui.settle();
    assert.deepEqual(queueNames(ui), allQueueNames);
  }
  for (const [status, message] of [[401, 'Sin sesión de recepción:'], [403, 'Sin sesión de recepción:'],
    [429, 'Límite temporal de la demo alcanzado.'], [500, 'La cola no respondió bien (código 500).'], [0, 'Sin conexión con el servidor de recepción.']]) {
    let fail = true;
    const ui = await consoleApp(triageQueue(), {}, {respond: req => {
      if (fail && req.path === '/api/panel/queue') {
        if (!status) throw new Error('mock offline');
        return {ok: false, status};
      }
    }});
    assert.ok(ui.get('recepcion-state').textContent.startsWith(message), status);
    assert.equal(ui.container.querySelector('.queue-toolbar').hidden, true);
    assert.equal(ui.get('recepcion-queue').hidden, true);
    fail = false;
    await ui.get('recepcion-state').querySelector('button').emit('click'); await ui.settle();
    assert.equal(ui.container.querySelector('.queue-toolbar').hidden, false);
    assert.deepEqual(queueNames(ui), allQueueNames);
    assert.ok(ui.requests.filter(req => req.path.startsWith('/api/panel/')).every(req => req.method === 'GET'));
  }
  const ui = await consoleApp(triageQueue());
  await ui.change('queue-search', 'Camila'); await ui.click('demo-mode-switch');
  assert.equal(ui.container.querySelector('.queue-toolbar').hidden, true);
  assert.equal(ui.intervals.size, 0);
  assert.deepEqual(ui.stored, [['copiloto.demo', '0']]);
  await ui.click('demo-mode-switch');
  assert.equal(ui.container.querySelector('.queue-toolbar').hidden, false);
  assert.equal(ui.get('queue-search').value, 'Camila');
  assert.deepEqual(queueNames(ui), ['Camila Rojas', 'Camila Soto']);
});

test('guided availability stops before room selection, name or confirmation', async () => {
  const ui = await app();
  await ui.scenarios[1].emit('click'); await ui.settle();
  assert.equal(ui.sent.length, 3);
  assert.ok(ui.sent.every(text => !/confirma|Camila|Jacuzzi/i.test(text)));
  assert.match(ui.get('scenario-status').textContent, /elige.*nombre.*propuesta.*confirma/i);
});

test('the availability script is available in every mode and never books on its own', async () => {
  // Es una consulta que se detiene antes de reservar: no depende del permiso de reserva autónoma.
  for (const status of [{mode: 'full', autonomous_booking: false}, {mode: 'assisted', autonomous_booking: false},
    {ai_enabled: false, autonomous_booking: false}, {mode: 'full', autonomous_booking: true}]) {
    const ui = await app(status);
    assert.equal(ui.scenarios[1].disabled, false);
    await ui.scenarios[1].emit('click'); await ui.settle();
    assert.equal(ui.sent.length, 3);
    assert.ok(ui.sent.every(text => !/confirma/i.test(text)));
  }
});

test('server proposal is visible in chat before an explicit one-shot confirmation', async () => {
  const proposal = {type: 'booking_proposal', guest_name: 'Huésped Ficticio', room_name: 'Suite Jardín', room_code: 'suite',
    checkin: '2027-03-15', checkout: '2027-03-18', nights: 3, adults: 2, children: 1, total_clp: 240000, simulated: true};
  const ui = await app({}, [{reply: 'Revisa la propuesta.', events: [proposal], quick_replies: ['Sí, confirmo la reserva']}]);
  await ui.send('Mi nombre ficticio es Huésped Ficticio');
  assert.equal(ui.sent.length, 1);
  assert.equal(ui.get('actions-panel').hidden, true);
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'false');
  const text = ui.get('messages').textContent;
  for (const value of ['Huésped Ficticio', 'Suite Jardín', 'suite', '2027-03-15', '2027-03-18', '3 noches', '2 adultos', '1 niños', '240.000']) assert.ok(text.includes(value), value);
  await ui.get('toggle-actions').emit('click');
  assert.equal(ui.get('actions-panel').hidden, false);
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'true');
  assert.equal(ui.get('timeline-empty').hidden, true);
  assert.equal(ui.get('timeline').textContent, 'Turno 1 · acciones del asistente');
  await ui.get('toggle-actions').emit('click');
  assert.equal(ui.get('actions-panel').hidden, true);
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'false');
  const buttons = ui.get('messages').querySelectorAll('button').filter(el => el.textContent === 'Sí, confirmo la reserva');
  assert.equal(buttons.length, 1);
  await buttons[0].emit('click'); await ui.settle(); await buttons[0].emit('click'); await ui.settle();
  assert.deepEqual(ui.sent, ['Mi nombre ficticio es Huésped Ficticio', 'Sí, confirmo la reserva']);
});

test('handoff and tool details do not promise notification or expose credentials', async () => {
  const ui = await app({}, [{reply: 'Solicitud simulada.', events: [
    {type: 'handoff', reason: 'Consulta especial', simulated: true},
    {type: 'tool_call', name: 'handoff_to_human', ok: true, arguments: {reason: 'Consulta especial', token: 'PRIVATE', nested: {password: 'PRIVATE'}}}
  ]}]);
  await ui.send('Recepción');
  assert.match(ui.get('timeline').textContent, /no se notificó/i);
  assert.match(ui.get('timeline').textContent, /Chatwoot/);
  assert.doesNotMatch(ui.get('timeline').textContent, /PRIVATE|Se avisa|Pidió ayuda a recepción/);
});

test('reset only clears chat history and preserves independent voice controls', async () => {
  const ui = await app();
  await ui.send('¿Cómo llego?'); await ui.get('reset').emit('click'); await ui.settle();
  assert.equal(ui.requests.filter(url => url.endsWith('/reset')).length, 1);
  assert.equal(ui.get('messages').querySelectorAll('.user').length, 0);
  assert.match(html, /historial.*PMS/);
  for (const id of ['voice-demo', 'voice-start', 'voice-talk', 'voice-hangup', 'voice-form', 'voice-typed-input', 'voice-log']) assert.ok(ui.get(id), id);
  assert.match(html, /src="voice\.js(?:\?v=[^"]+)?" defer/);
  assert.match(css, /\.voice-controls/);
  assert.doesNotMatch(css, /\n\s*nav a:not\(\.nav-cta\)/);
});

test('existing information scenario and normal chat remain available without AI', async () => {
  const ui = await app({ai_enabled: false, autonomous_booking: false});
  await ui.scenarios[0].emit('click'); await ui.settle();
  assert.deepEqual(ui.sent, ['¿Cómo llego al hotel?', '¿Tienen piscina y qué otros servicios ofrecen?']);
  await ui.send('¿Cuál es el horario de check-in?');
  assert.equal(ui.sent.length, 3);
});

test('quick replies cannot offer confirmation without a server proposal', async () => {
  const ui = await app({}, [{reply: 'Bonjour', events: [], quick_replies: ['Sí, confirmo la reserva', '¿Cómo llego?']}]);
  await ui.send('Hola');
  assert.deepEqual(ui.get('messages').querySelectorAll('button').map(el => el.textContent), ['¿Cómo llego?']);
  assert.equal(ui.sent.length, 1);
});

test('existing availability results, booking tickets and optional trace remain usable', async () => {
  const ui = await app({}, [{reply: 'Resultado de demostración', events: [
    {type: 'tool_call', name: 'check_availability', ok: true, arguments: {checkin: '2027-03-15', checkout: '2027-03-18'},
      result: {noches: 3, lectura: '15:00', opciones: [{nombre: 'Suite Jardín', cupos: 1, precio_noche_clp: 80000, total_clp: 240000}]}},
    {type: 'booking_created', booking_id: 7, room_name: 'Suite Jardín', checkin: '2027-03-15', checkout: '2027-03-18', nights: 3, adults: 2, children: 0, total_clp: 240000}
  ]}]);
  await ui.send('Consulta');
  assert.match(ui.get('messages').textContent, /Resultado de demostración/);
  assert.equal(ui.get('actions-panel').hidden, true);
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'false');
  assert.match(html, /id="toggle-actions"[^>]*aria-controls="actions-panel"/);
  await ui.get('toggle-actions').emit('click');
  assert.equal(ui.get('actions-panel').hidden, false);
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'true');
  assert.match(ui.get('timeline').textContent, /Suite Jardín.*queda 1.*80.000.*240.000/);
  assert.match(ui.get('timeline').textContent, /Reserva #7 creada en el PMS simulado/);
  await ui.get('toggle-actions').emit('click');
  assert.equal(ui.get('actions-panel').hidden, true);
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'false');
  assert.match(ui.get('toggle-actions').textContent, /Ver traza técnica/);
  assert.equal(ui.scripts().length, 0, 'Chatwoot SDK stays unloaded during simulator use');
});

test('chatwoot sdk gets the resolved base url, normalized without a trailing slash', async () => {
  const runArgs = [];
  const ui = await app({}, [], {config: {websiteToken: 'tok', chatwootUrl: 'http://localhost:3000'},
    location: {hostname: '192.168.1.50', protocol: 'https:'}});
  const clicking = ui.get('open-chat').emit('click');
  await ui.settle();
  const script = ui.scripts()[0];
  assert.equal(script.src, 'https://192.168.1.50:3000/packs/js/sdk.js');
  ui.window.chatwootSDK = {run: args => runArgs.push({...args})};
  script.onload();
  await clicking;
  assert.deepEqual(runArgs, [{websiteToken: 'tok', baseUrl: 'https://192.168.1.50:3000'}]);
});

test('focus returns to the composer when a keyboard-activated quick reply had it', async () => {
  const ui = await app({}, [{reply: 'Hola', quick_replies: []}]);
  const quickReply = ui.get('messages').querySelectorAll('button')[0];
  ui.document.activeElement = quickReply;
  await ui.send('hola');
  assert.equal(ui.get('message-input').focusCalls, 1);
  // Si el foco estaba fuera de la conversación, no se roba.
  const other = await app({}, [{reply: 'Hola', quick_replies: []}]);
  other.document.activeElement = other.get('open-chat');
  await other.send('hola');
  assert.equal(other.get('message-input').focusCalls, undefined);
});

test('the composer stays usable while the trace animates, but a second turn waits', async () => {
  const ui = await app({}, [
    {reply: 'primera', events: [{type: 'tool_call', name: 'get_hotel_info', ok: true, arguments: {}}]},
    {reply: 'segunda', events: [], quick_replies: []}
  ], {animate: true, manualTimers: true});
  await ui.send('uno');
  assert.equal(ui.get('message-input').disabled, false, 'la traza no bloquea el composer');
  await ui.send('dos');
  assert.deepEqual(ui.sent, ['uno'], 'no puede arrancar un turno simultáneo durante la traza');
  ui.flushTimers();
  await ui.settle();
  assert.equal(ui.get('send').disabled, false, 'la traza terminó y se puede enviar de nuevo');
  await ui.send('dos');
  assert.deepEqual(ui.sent, ['uno', 'dos']);
});

test('confirming a proposal does not mark it expired', async () => {
  const proposal = {type: 'booking_proposal', guest_name: 'Huésped Ficticio', room_name: 'Suite Jardín', room_code: 'suite',
    checkin: '2027-03-15', checkout: '2027-03-18', nights: 3, adults: 2, children: 1, total_clp: 240000, simulated: true};
  const ui = await app({}, [
    {reply: 'Revisa la propuesta.', events: [proposal], quick_replies: []},
    {reply: 'Reserva creada.', events: [{type: 'booking_created', booking_id: 9, room_name: 'Suite Jardín',
      checkin: '2027-03-15', checkout: '2027-03-18', nights: 3, adults: 2, children: 1, total_clp: 240000}], quick_replies: []}
  ]);
  await ui.send('Mi nombre es Huésped Ficticio');
  const confirmButtons = () => ui.get('messages').querySelectorAll('button')
    .filter(el => el.textContent === 'Sí, confirmo la reserva');
  assert.equal(confirmButtons().length, 1);
  await confirmButtons()[0].emit('click');
  await ui.settle();
  assert.doesNotMatch(ui.get('messages').textContent, /Propuesta vencida/);
  assert.equal(confirmButtons().length, 0, 'el botón se consume con la confirmación');
});

test('voice panel reuses the demo url resolver so a LAN visit reaches the copiloto', async () => {
  const voice = readFileSync(new URL('../landing/voice.js', import.meta.url), 'utf8');

  async function voiceRequests(resolver) {
    const requests = [];
    const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
    const window = {COPILOTO_CONFIG: {copilotoUrl: 'http://localhost:8100'},
      sessionStorage: {getItem() {}, setItem() {}}, ...(resolver ? {resolveDemoUrl: resolver} : {})};
    vm.runInNewContext(voice, {window, document: {getElementById: id => ids.get(id)},
      fetch: async url => { requests.push(url); return {ok: true, json: async () => ({voice: false})}; }});
    for (let i = 0; i < 100; i++) await Promise.resolve();
    return requests[0];
  }

  assert.equal(await voiceRequests(value => String(value).replace('localhost', '192.168.1.50')),
    'http://192.168.1.50:8100/api/demo/status');
  // Sin resolutor disponible (demo.js no cargó), la URL cruda sigue siendo el respaldo.
  assert.equal(await voiceRequests(null), 'http://localhost:8100/api/demo/status');
});

test('dead landing hooks disappear and the demo gate reads as a state', () => {
  // .how-visual ya no existe en ninguna página: el selector muerto no vuelve a demo.js.
  assert.doesNotMatch(source, /how-visual/);
  // El paralaje escribía --rx/--ry en #hero-stage, oculto en /demo y sin demo.js en /: nunca se ejecutaba.
  assert.doesNotMatch(source, /hero-stage|--rx|--ry/);
  // class="cta-section" no tenía regla: la portada no deja ganchos huérfanos.
  assert.doesNotMatch(indexHtml, /cta-section/);
  // El estado «sin sesión» de la consola es un estado visual, no texto suelto.
  assert.match(css, /\.console-state\.gate/);
  // La consola sondea GET /api/demo/session al cargar y deshabilita el interruptor si el servidor apagó la demo.
  assert.match(consoleSource, /\/api\/demo\/session/);
  assert.match(consoleSource, /demoSwitch\.disabled =/);
});
