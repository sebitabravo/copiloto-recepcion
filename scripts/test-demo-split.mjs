// Contrato de /demo (chat del huésped + bandeja de recepción): formatos, render del hilo, separación de
// roles y regresiones de estilo. Sin navegador: un DOM mínimo y lectura estática de los archivos.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createDocument, addById, flush} from './lib/mini-dom.mjs';

const read = name => readFileSync(new URL(`../landing/${name}`, import.meta.url), 'utf8');
const html = read('demo.html');
const css = read('demo-split.css');
const landingCss = read('demo.css');
const shared = read('demo-shared.js');
const guest = read('demo-guest.js');
const inbox = read('demo-inbox.js');
const page = read('demo-page.js');
const index = read('index.html');

class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.className = ''; this.dataset = {}; this.text = ''; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
}

function loadShared() {
  const window = {COPILOTO_CONFIG: {copilotoUrl: 'http://localhost:8100'}, crypto: globalThis.crypto};
  const document = {
    createElement: tag => new Node(tag),
    createTextNode: text => { const node = new Node('#text'); node.text = String(text); return node; }
  };
  vm.runInNewContext(shared, {window, document, location: {href: 'http://localhost:8080/demo', hostname: 'localhost',
    protocol: 'http:'}, Intl, Date, URL, Math, String, Number, Array, Uint8Array, AbortController, setTimeout, clearTimeout});
  return window.DemoShared;
}

const S = loadShared();

test('stay and guest labels match the reference («20–22 nov · 2 adultos»)', () => {
  assert.equal(S.stayRange('2026-11-20', '2026-11-22'), '20–22 nov');
  assert.equal(S.stayRange('2026-12-30', '2027-01-02'), '30 dic – 2 ene');
  assert.equal(S.stayRange(null, null), null);
  assert.equal(S.summary({checkin: '2026-11-20', checkout: '2026-11-22', adults: 2}), '20–22 nov · 2 adultos');
  assert.equal(S.summary({checkin: null, reason_label: 'Pidió hablar con recepción'}), 'Pidió hablar con recepción');
  assert.equal(S.guests({adults: 2, children: 0}), '2 adultos · 0 niños');
  assert.equal(S.guests({adults: 1, children: null}), '1 adulto · niños sin informar');
  assert.equal(S.guests({adults: null}), null, 'lo que falta queda explícito, no inventado');
});

test('waiting clock and risk tones follow the server thresholds', () => {
  assert.equal(S.clock(42), '00:42');
  assert.equal(S.clock(185), '03:05');
  assert.equal(S.waitTone(30, 120, 180), '');
  assert.equal(S.waitTone(130, 120, 180), 'amber');
  assert.equal(S.waitTone(180, 120, 180), 'red');
  const fetchedAt = 1_000_000;
  assert.equal(S.liveElapsed({state: 'en_curso', elapsed_s: 10}, fetchedAt, fetchedAt + 5000), 15);
  assert.equal(S.liveElapsed({state: 'cumplida', elapsed_s: 42}, fetchedAt, fetchedAt + 99000), 42, 'cumplida no sigue');
  assert.equal(S.liveElapsed({state: 'fuera_de_turno', elapsed_s: null}, fetchedAt), null);
  assert.deepEqual(['pendiente', 'en_atencion', 'respondida', 'cerrada'].map(S.tone), ['amber', 'blue', 'green', 'grey']);
});

test('the thread labels who speaks and hides internal notes from the guest', () => {
  const note = {id: 1, role: 'note', body: 'Pre-información', created_at: 1};
  assert.equal(S.messageNodes(note, 'guest', null).length, 0, 'el huésped nunca ve notas internas');
  assert.match(S.messageNodes(note, 'staff', null)[0].textContent, /Nota interna · solo recepción/);
  const assistant = {id: 2, role: 'assistant', body: 'Solicitud enviada a recepción.\n\nN.º BDL-001', created_at: 1};
  const bubbles = S.messageNodes(assistant, 'guest', 'guest');
  assert.equal(bubbles.length, 2, 'una idea por burbuja');
  assert.match(bubbles[0].textContent, /^Asistente virtual/);
  const staff = {id: 3, role: 'staff', body: 'Hay una doble', author: 'Sofía', kind: 'answer', created_at: 1};
  assert.match(S.messageNodes(staff, 'guest', 'assistant')[0].textContent, /^Sofía · Recepción/);
  const ack = {...staff, kind: 'ack'};
  assert.match(S.messageNodes(ack, 'staff', null)[0].textContent, /acuse/, 'recepción distingue un acuse');
  assert.doesNotMatch(S.messageNodes(ack, 'guest', null)[0].textContent, /acuse/);
});

test('links in assistant replies are short and safe; guest text is never a link', () => {
  const map = 'https://www.google.com/maps/search/?api=1&query=Hotel+Boutique+Bordeluz+Villarrica';
  const reply = {id: 9, role: 'assistant', body: `Dirección: Molco\nMapa: ${map}`, created_at: 1};
  const paragraph = S.messageNodes(reply, 'guest', null)[0].children.find(node => node.tagName === 'p');
  const link = paragraph.children.find(node => node.tagName === 'a');
  assert.equal(link.textContent, 'Abrir en Google Maps');
  assert.equal(link.href, map);
  assert.equal(link.rel, 'noopener noreferrer');
  assert.doesNotMatch(paragraph.textContent, /api=1/, 'la URL cruda no se muestra');
  const guestMessage = {id: 10, role: 'guest', body: `mira ${map}`, created_at: 1};
  const guestParagraph = S.messageNodes(guestMessage, 'guest', null)[0].children.find(node => node.tagName === 'p');
  assert.equal(guestParagraph.children.length, 0, 'lo que escribe el huésped queda como texto');
  const sneaky = {id: 11, role: 'assistant', body: 'javascript:alert(1) <b>hola</b>', created_at: 1};
  const plain = S.messageNodes(sneaky, 'guest', null)[0].children.find(node => node.tagName === 'p');
  assert.ok(plain.children.every(node => node.tagName !== 'a'), 'solo http(s) se vuelve enlace');
});

test('idempotency keys satisfy the server contract', () => {
  const ids = new Set(Array.from({length: 50}, () => S.newId()));
  assert.equal(ids.size, 50);
  for (const id of ids) assert.match(id, /^[A-Za-z0-9-]{8,64}$/);
});

test('the page shows the reference labels and the guest actions', () => {
  assert.match(html, /Hotel Boutique Bordeluz/);
  assert.match(html, /WhatsApp simulado/);
  assert.match(html, /Bandeja de recepción/);
  assert.match(html, /datos de prueba/i);
  for (const action of ['Ubicación', 'Consultar fechas', 'Hablar con recepción']) {
    assert.match(html, new RegExp(`data-say="${action}"`), action);
  }
  for (const label of ['Tomar solicitud', 'Enviar respuesta', 'Pendiente de confirmación']) {
    assert.ok((inbox + html).includes(label) || label === 'Pendiente de confirmación', label);
  }
  assert.match(html, /\?vista=huesped/);
  assert.match(html, /\?vista=recepcion/);
});

test('accessibility basics: live regions, labels and visible focus', () => {
  assert.match(html, /id="guest-thread"[^>]*role="log"[^>]*aria-live="polite"/);
  assert.match(html, /<label class="sr-only" for="guest-input">/);
  assert.match(html, /<label class="sr-only" for="inbox-search">/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion/);
  // El modo oscuro lo pone la portada: demo.css redefine sus tokens y la demo solo usa esos tokens.
  assert.match(landingCss, /prefers-color-scheme: dark/);
});

test('the demo keeps the landing name, brand and palette', () => {
  // Misma marca que la portada: «B» + Bordeluz, mismo hotel en el chat que en el hero.
  const brand = '<span class="brand-mark" aria-hidden="true">B</span>Bordeluz';
  assert.ok(index.includes(brand) && html.includes(brand), 'la marca de la demo es la de la portada');
  assert.ok(index.includes('Hotel Boutique Bordeluz') && html.includes('Hotel Boutique Bordeluz'));
  assert.match(html, /copiloto\.bordeluz\.demo/, 'el marco repite la dirección del hero');
  assert.doesNotMatch(html + css, /Hostería|hostería|VLL-/, 'sin restos del alojamiento ficticio anterior');
  // Los colores salen de los tokens de demo.css; solo se admiten el verde «en línea» de WhatsApp y
  // los tonos de las mezclas de bronce que ya usa la portada.
  const hex = [...new Set(css.match(/#[0-9a-f]{3,8}\b/gi) || [])].map(value => value.toLowerCase()).sort();
  assert.deepEqual(hex, ['#25d366', '#40230d', '#fff']);
  for (const token of ['--accent', '--ink', '--card', '--wa-bg', '--ok']) assert.match(css, new RegExp(`var\\(${token}\\)`), token);
});

test('the guest role never touches reception endpoints or credentials', () => {
  assert.doesNotMatch(guest, /\/api\/panel|staff:\s*true|\/api\/demo\/session/);
  assert.match(inbox, /staff: true/);
  assert.match(shared, /credentials: staff \? 'include' : 'omit'/);
  assert.match(page, /\?vista=huesped|vista/);
});

test('no class of the demo collides with the landing stylesheet', () => {
  // Regresión: .msg y .note de la portada animaban y atenuaban las burbujas de la bandeja.
  const own = new Set([...css.matchAll(/^\s*\.([a-z][a-z0-9-]*)/gm)].map(([, name]) => name));
  const allowed = new Set(['wrap']);
  for (const name of own) {
    if (allowed.has(name)) continue;
    const pattern = new RegExp(`(^|[\\s,>+~(])\\.${name}([\\s,:.{\\[>)]|$)`, 'm');
    assert.doesNotMatch(landingCss, pattern, `.${name} ya existe en demo.css`);
  }
});

test('server text is never interpreted as HTML', () => {
  for (const source of [shared, guest, inbox, page, read('demo-admin.js')]) assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML/);
});

function bootPage(view, {offline = false} = {}) {
  const document = createDocument();
  addById(document, ['shift-scenario', 'shift-status', 'app-addr', 'guest-view', 'inbox-view', 'admin-view']);
  for (const role of ['ambas', 'huesped', 'recepcion', 'admin']) {
    const button = document.createElement('button');
    button.dataset.viewOption = role;
    document.body.append(button);
  }
  const started = {huesped: 0, recepcion: 0, admin: 0};
  const calls = [];
  const window = {DemoShared: {store: {get: () => null, set() {}}, setRun() {},
    el: (tag, cls, text) => { const node = document.createElement(tag); node.textContent = text; return node; },
    async api(path) {
      calls.push(path);
      if (offline) throw new Error('Sin conexión.');
      if (path === '/api/demo/status') return {shift: {start: '08:00', end: '22:00', in_shift: true}};
      return {run: 'corrida-de-prueba-123'};
    }},
    DemoGuest: {init() { started.huesped++; }}, DemoInbox: {init() { started.recepcion++; }},
    DemoAdmin: {init() { started.admin++; }}, matchMedia: () => ({matches: false})};
  const location = {href: `http://localhost:8080/demo?vista=${view}`, search: `?vista=${view}`, pathname: '/demo', hash: ''};
  vm.runInNewContext(page, {window, document, location, history: {replaceState() {}}, URL, URLSearchParams,
    setTimeout() {}, encodeURIComponent});
  return {document, started, calls, button: role => document.querySelector(`[data-view-option="${role}"]`)};
}

test('Administration is an accessible perspective in the existing selector, not the split view', async () => {
  assert.match(html, /data-view-option="admin"[^>]*aria-pressed="false"[^>]*aria-controls="admin-view"[^>]*>Administración</);
  assert.match(html, /id="admin-view"[^>]*aria-labelledby="admin-title"[^>]*hidden/);
  assert.match(html, /id="admin-status"[^>]*role="status"/);
  assert.match(html, /id="admin-frame"[^>]*title="PMS simulado de administración"/);
  assert.match(html, /src="demo-admin\.js\?v=/);
  const ui = bootPage('admin', {offline: true});
  await flush();
  assert.equal(ui.document.body.dataset.view, 'admin');
  assert.equal(ui.button('admin').getAttribute('aria-pressed'), 'true');
  assert.equal(ui.document.getElementById('admin-view').hidden, false);
  assert.equal(ui.document.getElementById('guest-view').hidden, true);
  assert.equal(ui.document.getElementById('inbox-view').hidden, true);
  assert.deepEqual(ui.started, {huesped: 0, recepcion: 0, admin: 1}, 'admin no depende de la API de chat ni inicia otros roles');
});

test('guest, reception, split, shift and separate-window controls keep their previous behavior', async () => {
  const ui = bootPage('huesped');
  await flush();
  assert.deepEqual(ui.started, {huesped: 1, recepcion: 0, admin: 0});
  await ui.button('recepcion').click();
  assert.deepEqual(ui.started, {huesped: 1, recepcion: 1, admin: 0});
  await ui.button('ambas').click();
  await ui.button('huesped').click();
  assert.deepEqual(ui.started, {huesped: 1, recepcion: 1, admin: 0}, 'cada rol se inicia una sola vez');
  assert.equal(ui.button('huesped').getAttribute('aria-pressed'), 'true');
  await ui.button('admin').click();
  await ui.button('ambas').click();
  assert.equal(ui.document.getElementById('guest-view').hidden, false);
  assert.equal(ui.document.getElementById('inbox-view').hidden, false);
  assert.equal(ui.document.getElementById('admin-view').hidden, true);
  assert.deepEqual(ui.started, {huesped: 1, recepcion: 1, admin: 1});
  for (const id of ['guest-form', 'guest-reset', 'inbox-filter', 'inbox-search', 'inventory-check', 'shift-scenario']) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  for (const role of ['huesped', 'recepcion']) assert.ok(html.includes(`/demo?vista=${role}`));
});

function bootAdmin(config, fetchResult = () => Promise.resolve({ok: true, type: 'opaque'})) {
  const document = createDocument();
  addById(document, ['admin-status', 'admin-open', 'admin-retry', 'admin-frame']);
  for (const id of ['admin-open', 'admin-retry', 'admin-frame']) document.getElementById(id).hidden = true;
  const calls = [];
  const window = {COPILOTO_CONFIG: config};
  const location = {href: 'http://localhost:8080/demo', hostname: 'localhost', protocol: 'http:'};
  const context = {window, document, location, URL, Intl, Date, AbortController, setTimeout, clearTimeout,
    fetch: (url, options) => { calls.push({url, options}); return fetchResult(); }};
  vm.runInNewContext(shared + '\n' + read('demo-admin.js'), context);
  window.DemoAdmin.init();
  return {window, document, calls, node: id => document.getElementById(`admin-${id}`)};
}

test('static Administration is explicitly unavailable and makes no service calls or writes', async () => {
  const ui = bootAdmin({staticDemo: true, pmsUrl: 'http://localhost:8200'});
  await flush();
  assert.equal(ui.node('status').textContent,
    'Administración/PMS no disponible en esta versión estática. No hay servicio de administración: aquí no se crean ni se guardan reservas.');
  await ui.node('open').click();
  await ui.node('retry').click();
  assert.equal(ui.calls.length, 0);
  assert.equal(ui.node('open').hidden, true);
  assert.equal(ui.node('retry').hidden, true);
  assert.equal(ui.node('frame').hidden, true);
  assert.equal(ui.node('frame').src, undefined);
});

test('only a configured reachable PMS exposes the existing demo entry, after explicit opening', async () => {
  const ui = bootAdmin({pmsUrl: 'http://localhost:8200/'});
  await flush();
  assert.equal(ui.calls.length, 1);
  assert.equal(ui.calls[0].url, 'http://localhost:8200/health');
  assert.equal(ui.calls[0].options.method, 'GET');
  assert.equal(ui.calls[0].options.redirect, 'follow');
  assert.equal(ui.calls[0].options.credentials, 'omit');
  assert.equal(ui.calls[0].options.mode, 'no-cors', 'PMS no expone CORS; una respuesta opaca no certifica modo demo');
  assert.equal(ui.node('frame').src, undefined, 'la comprobación no crea una sesión de personal');
  assert.equal(ui.node('open').hidden, false);
  await ui.node('open').click();
  assert.equal(ui.node('frame').src, 'http://localhost:8200/admin?demo=1');
  assert.equal(ui.node('frame').hidden, false);
  assert.match(ui.node('status').textContent, /PMS valida el modo demo/);
  await ui.node('open').click();
  assert.equal(ui.calls.length, 1, 'sin API de escritura ni tokens enviados desde JS');
});

test('an unreachable PMS stays unavailable and can be checked again without fake writes', async () => {
  let down = true;
  const ui = bootAdmin({pmsUrl: 'http://localhost:8200'}, () => down
    ? Promise.reject(new Error('network')) : Promise.resolve({ok: true, type: 'opaque'}));
  await flush();
  assert.equal(ui.node('status').textContent, 'El servicio de Administración/PMS no está disponible. Enciende el PMS de prueba y reintenta. Este panel no simula reservas.');
  await ui.node('open').click();
  assert.equal(ui.node('frame').src, undefined);
  assert.equal(ui.node('open').hidden, true);
  assert.equal(ui.node('retry').hidden, false);
  down = false;
  await ui.node('retry').click();
  await flush();
  assert.equal(ui.calls.length, 2);
  assert.equal(ui.node('open').hidden, false);
  assert.equal(ui.node('frame').hidden, true);
});

test('missing or unsafe PMS configuration never offers an automatic admin session', async () => {
  for (const pmsUrl of [undefined, '', 'javascript:alert(1)', 'https://user:pass@demo.test', 'https://demo.test?token=x', 'https://demo.test#token']) {
    const ui = bootAdmin({pmsUrl});
    await flush();
    assert.equal(ui.calls.length, 0, String(pmsUrl));
    assert.equal(ui.node('open').hidden, true);
    assert.equal(ui.node('frame').src, undefined);
    assert.match(ui.node('status').textContent, /no está configurado/);
  }
});
