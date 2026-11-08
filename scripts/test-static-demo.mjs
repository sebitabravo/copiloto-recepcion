import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync, readdirSync, statSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import vm from 'node:vm';

const root = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const read = name => readFileSync(join(root, name), 'utf8');
const shim = read('landing/static-demo.js');
const frontend = ['landing/demo-shared.js', 'landing/demo-guest.js', 'landing/demo-inbox.js', 'landing/demo-page.js']
  .map(read).join('\n');

// Rutas que el frontend pide de verdad: si una no está interceptada, la demo estática llama a la red.
const requested = [...new Set([...frontend.matchAll(/['"`](\/api\/[^'"`?]*)/g)]
  .map(([, path]) => path.replace(/\$\{[^}]*\}/g, '1'))
  .filter(path => !path.endsWith('/')))];

function memoryStorage() {
  const data = new Map();
  return {getItem: key => (data.has(key) ? data.get(key) : null), setItem: (key, value) => data.set(key, String(value))};
}

// Carga el shim con almacenamiento en memoria y un fetch real espía: nada debe llegar a él.
function loadShim() {
  const calls = [];
  const realFetch = (...args) => { calls.push(String(args[0])); return Promise.resolve(new Response('{}')); };
  const window = {fetch: realFetch, localStorage: memoryStorage(), sessionStorage: memoryStorage(),
    location: {href: 'https://demo.example.test/demo'}, addEventListener() {}};
  vm.runInNewContext(shim, {window, Response, URL, JSON, Date, Intl, Math, String, Number, Object, RegExp, console});
  const call = async (path, body) => {
    const response = await window.fetch(`https://demo.example.test${path}`,
      body === undefined ? {} : {method: 'POST', body: JSON.stringify(body)});
    return {status: response.status, body: response.status === 204 ? null : await response.json()};
  };
  return {call, calls};
}

test('every endpoint the new frontend calls is intercepted by the static shim', async () => {
  assert.ok(requested.length >= 6, `rutas detectadas: ${requested}`);
  const {call, calls} = loadShim();
  for (const path of requested) {
    const post = /chat|reply|reset|session|take|close|inventory/.test(path);
    const response = await call(path, post ? {session_id: 'x'.repeat(20), message: 'hola', name: 'Sofía'} : undefined);
    assert.ok(response.status < 500, `${path} respondió ${response.status}`);
  }
  assert.deepEqual(calls, [], `salieron a la red: ${calls.join(', ')}`);
});

test('the static demo runs the canonical case without a backend', async () => {
  const {call, calls} = loadShim();
  const session = 'estatico-huesped-000001';
  const say = (message, extra = {}) => call('/api/demo/chat', {session_id: session, message, shift: 'open', ...extra});
  assert.match((await say('¿Dónde queda la hostería?')).body.reply, /Cerca de la costanera de Villarrica/);
  await say('Consultar fechas');
  assert.match((await say('22 al 20 de noviembre 2 adultos')).body.reply, /tiene que ser después/);
  assert.deepEqual((await say('20-22 nov')).body.quick_replies, ['Sin niños', '1 niño', '2 niños']);
  assert.match((await say('Sin niños')).body.reply, /Revisa tu solicitud/);
  const sent = await say('Enviar a recepción', {client_message_id: 'enviar-0000001'});
  assert.match(sent.body.reply, /^Solicitud enviada a recepción\. Te responderán por aquí\./);
  const retry = await say('Enviar a recepción', {client_message_id: 'enviar-0000001'});
  assert.equal(retry.body.duplicate, true, 'el reintento no duplica');

  assert.equal((await call('/api/panel/requests')).status, 401, 'la bandeja pide sesión de recepción');
  await call('/api/demo/session', {name: 'Sofía'});
  const inbox = (await call('/api/panel/requests')).body;
  assert.equal(inbox.requests.length, 1);
  const request = inbox.requests[0];
  assert.equal(request.status_label, 'Pendiente de recepción');
  assert.equal(request.checkin.slice(5), '11-20');
  assert.equal((await call(`/api/panel/requests/${request.id}/take`, {})).body.status_label, 'En atención');
  const inventory = (await call(`/api/panel/requests/${request.id}/inventory`, {})).body;
  assert.equal(inventory.offers[0].available_units, 1);
  const reply = 'Hay una habitación doble para esas fechas. ¿Quieres avanzar con la reserva?';
  const answered = (await call(`/api/panel/requests/${request.id}/reply`, {body: reply, client_id: 'resp-00000001'})).body;
  assert.equal(answered.request.status_label, 'Respondida');
  assert.equal(answered.request.reservation_label, 'Pendiente de confirmación');
  const guest = (await call(`/api/demo/conversation?session_id=${session}`)).body;
  assert.equal(guest.messages.at(-1).body, reply);
  assert.ok(guest.messages.every(message => message.role !== 'note'), 'el huésped no lee notas internas');
  assert.deepEqual(calls, []);
});

test('the static build replaces the public URL everywhere and leaks no secrets', () => {
  const work = mkdtempSync(join(tmpdir(), 'static-demo-'));
  const local = join(root, 'landing/config.js');
  const hadConfig = existsSync(local);
  const previous = hadConfig ? readFileSync(local, 'utf8') : null;
  try {
    // Un config.js local con token nunca debe viajar al sitio estático.
    writeFileSync(local, 'window.COPILOTO_CONFIG = {websiteToken: "secreto-local", copilotoUrl: "http://localhost:8100"};\n');
    execFileSync('bash', [join(root, 'scripts/build-static-demo.sh')], {
      cwd: root, env: {...process.env, PUBLIC_SITE_URL: 'https://example.test', STATIC_DEMO_OUT: work}, stdio: 'pipe'
    });
    const files = readdirSync(work).filter(name => statSync(join(work, name)).isFile());
    for (const name of files.filter(file => /\.(html|txt|xml)$/.test(file))) {
      assert.doesNotMatch(readFileSync(join(work, name), 'utf8'), /__PUBLIC_SITE_URL__/, name);
    }
    const config = readFileSync(join(work, 'config.js'), 'utf8');
    assert.doesNotMatch(config, /https?:\/\/|localhost|secreto-local/i, 'config.js estático no lleva hosts ni tokens');
    assert.match(config, /staticDemo: true/);
    const demo = readFileSync(join(work, 'demo.html'), 'utf8');
    const shimTag = demo.indexOf('src="static-demo.js"');
    const appTag = demo.indexOf('src="demo-shared.js');
    assert.ok(shimTag > -1 && appTag > -1 && shimTag < appTag, 'el shim se carga antes que la interfaz');
  } finally {
    if (hadConfig) writeFileSync(local, previous); else rmSync(local, {force: true});
    rmSync(work, {recursive: true, force: true});
  }
});

test('the build only ever cleans its own output directory', () => {
  const script = read('scripts/build-static-demo.sh');
  assert.match(script, /OUT="\$\{STATIC_DEMO_OUT:-\$ROOT\/dist\}"/);
  assert.match(script, /rm -rf "\$OUT" 2>\/dev\/null \|\| true/);
  assert.doesNotMatch(script, /rm -rf "\$ROOT"/, 'nunca se borra la raíz del repo');
  const work = mkdtempSync(join(tmpdir(), 'static-demo-safe-'));
  try {
    const out = join(work, 'out');
    writeFileSync(join(work, 'KEEP.txt'), 'sentinel');
    execFileSync('bash', [join(root, 'scripts/build-static-demo.sh')], {
      cwd: root, env: {...process.env, PUBLIC_SITE_URL: 'https://example.test', STATIC_DEMO_OUT: out}, stdio: 'pipe'
    });
    assert.equal(readFileSync(join(work, 'KEEP.txt'), 'utf8'), 'sentinel', 'no toca archivos vecinos');
    assert.ok(existsSync(join(out, 'demo.html')));
  } finally {
    rmSync(work, {recursive: true, force: true});
  }
});

test('the static demo declares itself and never interprets HTML', () => {
  assert.match(shim, /WhatsApp simulado · versión estática/, 'el canal se rotula como versión estática');
  assert.doesNotMatch(shim, /innerHTML/, 'el shim no interpreta HTML');
  assert.doesNotMatch(shim, /hotelbordeluz|963949710/i, 'ningún dato de un hotel real');
});
