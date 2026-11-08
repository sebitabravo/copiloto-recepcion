// Carreras de la interfaz de /demo, con red controlada (cada respuesta llega cuando la prueba decide).
// 1. Bandeja: una carga atrasada del caso A no puede pisar la selección de B ni desviar el envío.
// 2. Huésped: una lectura atrasada del huésped anterior no entra en la vista nueva; el sondeo se recupera
//    de un 429 (respetando Retry-After) y de un error de red, con un solo ciclo activo.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {Node, createDocument, addById, controlledFetch, flush} from './lib/mini-dom.mjs';

const read = name => readFileSync(new URL(`../landing/${name}`, import.meta.url), 'utf8');
const sources = {shared: read('demo-shared.js'), inbox: read('demo-inbox.js'), guest: read('demo-guest.js')};

function memoryStorage(seed = {}) {
  const data = new Map(Object.entries(seed));
  return {getItem: key => (data.has(key) ? data.get(key) : null), setItem: (key, value) => data.set(key, String(value))};
}

// Temporizadores falsos: nada corre solo; la prueba decide cuándo vence cada uno.
function fakeTimers() {
  let next = 1;
  const active = new Map();
  return {
    setTimeout: (fn, ms) => { const id = next++; active.set(id, {fn, ms}); return id; },
    clearTimeout: id => active.delete(id),
    setInterval: () => 0,
    clearInterval: () => {},
    pending: () => [...active.values()],
    async runAll() {
      const due = [...active.entries()];
      active.clear();
      // Como el navegador: dispara y no espera; la respuesta de red la entrega la prueba después.
      for (const [, timer] of due) timer.fn();
      await flush();
    }
  };
}

function boot(script, ids, {local = {}, session = {}} = {}) {
  const document = createDocument();
  addById(document, ids);
  for (const id of ['inbox-error', 'guest-error']) {
    const box = document.getElementById(id);
    if (box) box.append(document.createElement('span'), document.createElement('button'));
  }
  const net = controlledFetch();
  const timers = fakeTimers();
  const window = {COPILOTO_CONFIG: {copilotoUrl: 'http://demo.test'}, crypto: globalThis.crypto,
    localStorage: memoryStorage(local), sessionStorage: memoryStorage(session), confirm: () => true};
  const context = {window, document, location: {href: 'http://demo.test/demo', hostname: 'demo.test', protocol: 'http:'},
    fetch: net.fetch, Response, URL, Intl, Date, Math, JSON, String, Number, Array, Object, Promise, Uint8Array,
    AbortController, Node, encodeURIComponent, console, ...timers};
  vm.runInNewContext(sources.shared + '\n' + sources[script], context);
  return {window, document, net, timers};
}

const INBOX_IDS = ['inbox-name', 'identity-dialog', 'identity-input', 'identity-error', 'identity-form', 'inbox-identity',
  'inbox-error', 'inbox-live', 'inbox-items', 'inbox-empty', 'case-messages', 'case-action', 'card-code', 'card-facts',
  'inventory-check', 'inventory-down', 'case-close', 'inventory-result', 'card-measure', 'case-empty', 'case-thread',
  'case-card', 'case-code', 'case-status', 'case-sub', 'inbox-filter', 'inbox-search'];

const item = (id, code) => ({id, code, status: 'en_atencion', status_label: 'En atención', in_shift: true,
  commercial_at: 1, checkin: null, adults: null, reason_label: 'Pidió hablar con recepción', assignee: 'Sofía',
  measurement: {state: 'en_curso', elapsed_s: 5, target_s: 180, label: 'x'}});
const detail = (id, code) => ({...item(id, code), channel_label: 'WhatsApp simulado', contact_name: 'Huésped demo',
  events: [], messages: [], faq: [], reservation_status: 'pendiente_confirmacion',
  reservation_label: 'Pendiente de confirmación', actions: {take: false, reply: true, close: true, inventory: false}});
const inbox = (selected = null) => ({now: 1, me: 'Sofía', amber_s: 120, target_s: 180,
  requests: [item(1, 'BDL-001'), item(2, 'BDL-002')], selected});

async function openInbox() {
  const ui = boot('inbox', INBOX_IDS, {local: {'copiloto-demo-recepcion': 'Sofía'}});
  const started = ui.window.DemoInbox.init();
  await flush();
  ui.net.pending(call => call.url.includes('/api/demo/session')).respond(null, 204);
  await flush();
  ui.net.pending(call => call.url.endsWith('/api/panel/requests')).respond(inbox());
  await started;
  await flush();
  return ui;
}

const markDone = call => { call.done = true; return call; };

test('a late detail of case A never replaces the selection of B, and the reply goes to B', async () => {
  const {window, document, net} = await openInbox();
  for (const call of net.calls) call.done = true;
  window.DemoInbox.select(1);
  await flush();
  const loadA = markDone(net.pending(call => call.url.includes('selected=1')));
  window.DemoInbox.select(2);
  await flush();
  loadA.respond(inbox(detail(1, 'BDL-001')));
  await flush();
  assert.notEqual(document.getElementById('case-code').textContent, 'BDL-001', 'el detalle de A no se muestra');
  assert.equal(document.getElementById('reply-send'), null, 'sin detalle de B no hay botón de enviar');
  const loadB = net.pending(call => call.url.includes('selected=2'));
  assert.ok(loadB, 'al cambiar de caso durante la carga se pide el caso nuevo');
  markDone(loadB).respond(inbox(detail(2, 'BDL-002')));
  await flush();
  assert.equal(document.getElementById('case-code').textContent, 'BDL-002');
  const current = document.querySelector('#inbox-items .item[aria-current="true"]');
  assert.equal(current.dataset.id, '2', 'la lista marca el mismo caso que el detalle');
  document.getElementById('reply-text').value = 'Hola desde recepción';
  document.querySelector('form').emit('submit');
  await flush();
  const post = net.pending(call => call.options.method === 'POST' && call.url.includes('/reply'));
  assert.match(post.url, /\/api\/panel\/requests\/2\/reply$/, 'el envío usa el ID del caso seleccionado');
});

test('a failed reply is retried with the original case, key and text after switching cases', async () => {
  const {window, document, net} = await openInbox();
  for (const call of net.calls) call.done = true;
  window.DemoInbox.select(1);
  await flush();
  markDone(net.pending(call => call.url.includes('selected=1'))).respond(inbox(detail(1, 'BDL-001')));
  await flush();
  document.getElementById('reply-text').value = 'Respuesta para A';
  document.querySelector('form').emit('submit');
  await flush();
  const first = markDone(net.pending(call => call.url.includes('/requests/1/reply')));
  first.fail();
  await flush();
  for (const call of net.calls.filter(call => !call.done && call.url.includes('/api/panel/requests'))) {
    markDone(call).respond(inbox(detail(1, 'BDL-001')));
  }
  await flush();
  window.DemoInbox.select(2);
  await flush();
  markDone(net.pending(call => call.url.includes('selected=2'))).respond(inbox(detail(2, 'BDL-002')));
  await flush();
  document.querySelector('#inbox-error button').emit('click');
  await flush();
  const retry = net.pending(call => call.url.includes('/reply'));
  assert.match(retry.url, /\/requests\/1\/reply$/, 'el reintento va al caso original, no al seleccionado');
  assert.equal(retry.body.client_id, first.body.client_id, 'misma llave');
  assert.equal(retry.body.body, 'Respuesta para A', 'mismo texto');
});

const GUEST_IDS = ['guest-thread', 'guest-input', 'guest-send', 'guest-form', 'guest-actions', 'guest-typing',
  'guest-error', 'guest-request', 'guest-reset', 'guest-hotel', 'guest-channel', 'privacy-link'];
const reception = (messages, after) => ({conversation_id: -5, step: 'handed_off', messages, handled_by: 'recepcion',
  request: {code: 'BDL-001', status: 'pendiente', label: 'Enviada', open: true}, quick_replies: [], after});
const message = (id, body) => ({id, role: 'assistant', body, created_at: 1, options: null});

async function openGuest() {
  const ui = boot('guest', GUEST_IDS, {session: {'copiloto-demo-huesped:sin-corrida': 'huesped-anterior-000001'}});
  ui.window.DemoGuest.init({});
  await flush();
  return ui;
}

test('a late read from the previous guest never lands in the new guest view', async () => {
  const {window, document, net} = await openGuest();
  const oldRead = markDone(net.pending(call => call.url.includes('huesped-anterior-000001')));
  await document.getElementById('guest-reset').emit('click');
  oldRead.respond(reception([message(41, 'Mensaje del huésped anterior')]));
  await flush();
  assert.doesNotMatch(document.getElementById('guest-thread').textContent, /huésped anterior/);
  assert.equal(document.getElementById('guest-request').hidden, true, 'sin solicitud del huésped anterior');
  assert.notEqual(window.DemoGuest.sessionId, 'huesped-anterior-000001');
});

test('polling backs off on 429 (Retry-After) and network errors, recovers, and keeps one loop', async () => {
  const {document, net, timers} = await openGuest();
  markDone(net.pending(call => call.url.includes('/conversation'))).respond(reception([message(1, 'Hola')]));
  await flush();
  assert.equal(timers.pending().length, 1, 'un solo ciclo de sondeo');
  await timers.runAll();
  markDone(net.pending(call => call.url.includes('/conversation'))).respond({detail: 'x'}, 429, {'Retry-After': '7'});
  await flush();
  assert.equal(timers.pending().length, 1, 'el 429 reprograma el sondeo');
  assert.equal(timers.pending()[0].ms, 7000, 'respeta Retry-After');
  await timers.runAll();
  markDone(net.pending(call => call.url.includes('/conversation'))).fail();
  await flush();
  assert.equal(timers.pending().length, 1, 'un error de red también reprograma');
  assert.ok(timers.pending()[0].ms > 4000 && timers.pending()[0].ms <= 30000, 'espera acotada');
  await timers.runAll();
  const recovered = markDone(net.pending(call => call.url.includes('/conversation')));
  assert.match(recovered.url, /after=1/, 'retoma desde el último mensaje visto');
  recovered.respond(reception([message(2, 'Sofía responde')]));
  await flush();
  assert.match(document.getElementById('guest-thread').textContent, /Sofía responde/);
  assert.equal(timers.pending().length, 1);
  assert.equal(timers.pending()[0].ms, 4000, 'tras recuperarse vuelve al ritmo normal');
});
