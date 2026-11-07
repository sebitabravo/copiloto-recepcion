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
  append(...nodes) { for (const node of nodes) { node.remove(); node.parentElement = this; this.children.push(node); } }
  appendChild(node) { this.append(node); }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(x => x !== this); }
  replaceChildren(...nodes) { this.children = []; this.ownText = ''; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  async emit(name) { if (this.disabled) return; for (const fn of this.listeners[name] || []) await fn({preventDefault() {}}); }
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
    body: new Element(), documentElement: {scrollHeight: 1000}, addEventListener() {},
    querySelectorAll: selector => selector === '[data-scenario]' ? scenarios : [],
    querySelector: selector => selector === '.demo-grid' ? grid : scenarios.find(el => selector === `[data-scenario="${el.dataset.scenario}"]`)
  };
  // Skip decorative scrolling only; chat and all scenario handlers execute unchanged.
  ids.delete('topbar'); ids.delete('hero-stage');
  const pendingTimers = [];
  const window = {
    COPILOTO_CONFIG: options.config || {}, matchMedia: () => ({matches: !options.animate}), crypto: {randomUUID: () => '12345678-1234-1234-1234-123456789012'},
    sessionStorage: {getItem() {}, setItem() {}}, addEventListener() {},
    setInterval() {}, clearTimeout() {},
    setTimeout: options.manualTimers ? (fn, ms) => { if (ms < 90000) pendingTimers.push(fn); return 1; }
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
  return {get, scenarios, sent, requests, settle, document, window,
    flushTimers: () => { while (pendingTimers.length) pendingTimers.shift()(); },
    scripts: () => document.body.querySelectorAll('script'),
    async send(text) { get('message-input').value = text; await get('chat-form').emit('submit'); await settle(); }};
}

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
  assert.equal(ui.get('actions-panel').hidden, false);
  const text = ui.get('messages').textContent;
  for (const value of ['Huésped Ficticio', 'Suite Jardín', 'suite', '2027-03-15', '2027-03-18', '3 noches', '2 adultos', '1 niños', '240.000']) assert.ok(text.includes(value), value);
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
  assert.match(ui.get('timeline').textContent, /Suite Jardín.*queda 1.*80.000.*240.000/);
  assert.match(ui.get('timeline').textContent, /Reserva #7 creada en el PMS simulado/);
  assert.equal(ui.get('actions-panel').hidden, false);
  await ui.get('toggle-actions').emit('click');
  assert.equal(ui.get('actions-panel').hidden, true);
  assert.match(ui.get('toggle-actions').textContent, /Ver acciones/);
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
