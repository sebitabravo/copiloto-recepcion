import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../landing/demo.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../landing/index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../landing/demo.css', import.meta.url), 'utf8');

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
  focus() {}
  matches(selector) { return selector.startsWith('.') ? this.className.split(' ').includes(selector.slice(1)) : this.tagName === selector; }
  querySelectorAll(selector) {
    const parts = selector.split(' ');
    const descendants = this.children.flatMap(node => [node, ...node.querySelectorAll('*')]);
    if (selector === '*') return descendants;
    return descendants.filter(node => node.matches(parts.at(-1)) && (parts.length === 1 || node.parentElement?.matches(parts[0])));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

async function app(status = {}, responses = []) {
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
  const window = {
    COPILOTO_CONFIG: {}, matchMedia: () => ({matches: true}), crypto: {randomUUID: () => '12345678-1234-1234-1234-123456789012'},
    sessionStorage: {getItem() {}, setItem() {}}, addEventListener() {},
    setInterval() {}, setTimeout(fn, ms) { if (ms < 90000) queueMicrotask(fn); return 1; }, clearTimeout() {}
  };
  vm.runInNewContext(source, {window, document, Intl, Date, Uint8Array, AbortController,
    fetch: async (url, options) => {
      requests.push(url);
      const body = options.body && JSON.parse(options.body);
      let data = {ai_enabled: true, autonomous_booking: true, sandbox: true, ...status};
      if (url.endsWith('/chat')) { sent.push(body.message); data = responses.shift() || {reply: 'Réponse de test', events: [], quick_replies: []}; }
      return {ok: true, json: async () => data};
    }});
  const settle = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
  await settle();
  return {get, scenarios, sent, requests, settle, scripts: () => document.body.querySelectorAll('script'),
    async send(text) { get('message-input').value = text; await get('chat-form').emit('submit'); await settle(); }};
}

test('guided availability stops before room selection, name or confirmation', async () => {
  const ui = await app();
  await ui.scenarios[1].emit('click'); await ui.settle();
  assert.equal(ui.sent.length, 3);
  assert.ok(ui.sent.every(text => !/confirma|Camila|Jacuzzi/i.test(text)));
  assert.match(ui.get('scenario-status').textContent, /elige.*nombre.*propuesta.*confirma/i);
});

test('booking guidance uses effective capability, including full mode without permission', async () => {
  for (const status of [{mode: 'full', autonomous_booking: false}, {mode: 'assisted', autonomous_booking: false}, {ai_enabled: false, autonomous_booking: false}]) {
    const ui = await app(status);
    assert.equal(ui.scenarios[1].disabled, true);
    await ui.scenarios[1].emit('click');
    assert.deepEqual(ui.sent, []);
    assert.doesNotMatch(ui.get('messages').textContent, /reserva una habitación/);
  }
});

test('server proposal is visible in chat before an explicit one-shot confirmation', async () => {
  const proposal = {type: 'booking_proposal', guest_name: 'Huésped Ficticio', room_name: 'Suite Jardín', room_code: 'suite',
    checkin: '2027-03-15', checkout: '2027-03-18', nights: 3, adults: 2, children: 1, total_clp: 240000, simulated: true};
  const ui = await app({}, [{reply: 'Revisa la propuesta.', events: [proposal], quick_replies: ['Sí, confirmo la reserva']}]);
  await ui.send('Mi nombre ficticio es Huésped Ficticio');
  assert.equal(ui.sent.length, 1);
  assert.equal(ui.get('actions-panel').hidden, true);
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
  assert.match(html, /src="voice.js" defer/);
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
  assert.equal(ui.get('actions-panel').hidden, true);
  await ui.get('toggle-actions').emit('click');
  assert.equal(ui.get('actions-panel').hidden, false);
  assert.match(ui.get('toggle-actions').textContent, /Ocultar acciones/);
  assert.equal(ui.scripts().length, 0, 'Chatwoot SDK stays unloaded during simulator use');
});
