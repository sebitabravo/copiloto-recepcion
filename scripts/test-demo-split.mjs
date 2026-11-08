// Contrato de /demo (chat del huésped + bandeja de recepción): formatos, render del hilo, separación de
// roles y regresiones de estilo. Sin navegador: un DOM mínimo y lectura estática de los archivos.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

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
  for (const source of [shared, guest, inbox, page]) assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML/);
});
