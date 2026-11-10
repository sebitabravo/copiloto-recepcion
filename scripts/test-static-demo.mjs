import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
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
function loadShim({localStorage = memoryStorage(), sessionStorage = memoryStorage(), run = 'corrida-estatica-0001', config, fetchImpl} = {}) {
  const calls = [];
  const realFetch = fetchImpl ? (...args) => fetchImpl(...args, calls) : (...args) => { calls.push(String(args[0])); return Promise.resolve(new Response('{}')); };
  const window = {fetch: realFetch, localStorage, sessionStorage, COPILOTO_CONFIG: config || {},
    location: {href: `https://demo.example.test/demo${run ? `?corrida=${run}` : ''}`}, addEventListener() {}};
  class Clock extends Date { static now() { return Date.parse('2026-08-01T15:00:00Z'); } }
  vm.runInNewContext(shim, {window, Response, URL, JSON, Date: Clock, Intl, Math, String, Number, Object, RegExp, console});
  const call = async (path, body, headers = {}) => {
    const response = await window.fetch(`https://demo.example.test${path}`,
      {headers, ...(body === undefined ? {} : {method: 'POST', body: JSON.stringify(body)})});
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
  assert.match((await say('¿Dónde queda el hotel?')).body.reply, /sector Molco/);
  await say('Consultar fechas');
  assert.match((await say('22 al 20 de noviembre 2 adultos')).body.reply, /tiene que ser después/);
  assert.deepEqual((await say('20-22 nov')).body.quick_replies, ['Sin niños', '1 niño', '2 niños']);
  const summary = (await say('Sin niños')).body.reply;
  assert.match(summary, /Revisa tu solicitud/);
  assert.match(summary, /Disponible según lectura del PMS a las \d\d:\d\d/, 'sello de hora, como en la portada');
  const sent = await say('Enviar a recepción', {client_message_id: 'enviar-0000001'});
  assert.match(sent.body.reply, /^Solicitud enviada a recepción\. Te responderán por aquí\./);
  assert.match(sent.body.reply, /BDL-001/);
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
  assert.equal(inventory.source, 'PMS simulado');
  assert.ok(inventory.offers.length > 0 && inventory.offers.every(offer => offer.available_units > 0));
  const reply = 'Hay una habitación doble para esas fechas. ¿Quieres avanzar con la reserva?';
  const answered = (await call(`/api/panel/requests/${request.id}/reply`, {body: reply, client_id: 'resp-00000001'})).body;
  assert.equal(answered.request.status_label, 'Respondida');
  assert.equal(answered.request.reservation_label, 'Pendiente de confirmación');
  const guest = (await call(`/api/demo/conversation?session_id=${session}`)).body;
  assert.equal(guest.messages.at(-1).body, reply);
  assert.ok(guest.messages.every(message => message.role !== 'note'), 'el huésped no lee notas internas');
  assert.deepEqual(calls, []);
});

test('corridas isolate conversations, inboxes, resets and staff sessions while same-run tabs share state', async () => {
  const localStorage = memoryStorage();
  const sessionStorage = memoryStorage();
  const a = loadShim({localStorage, sessionStorage});
  const peer = loadShim({localStorage});
  const b = loadShim({localStorage, sessionStorage, run: 'corrida-estatica-0002'});
  await a.call('/api/demo/chat', {session_id: 'guest', message: 'Recepción', shift: 'open'});
  await a.call('/api/demo/session', {name: 'Sofía', operator_key: 'operador-estatico-0001'});
  const before = await a.call('/api/demo/conversation?session_id=guest');
  assert.deepEqual(await peer.call('/api/demo/conversation?session_id=guest'), before);
  assert.equal((await b.call('/api/demo/conversation?session_id=guest')).body.conversation_id, null);
  assert.equal((await b.call('/api/panel/requests')).status, 401, 'la sesión no cruza corridas');
  await b.call('/api/demo/session', {name: 'Sofía', operator_key: 'operador-estatico-0001'});
  assert.deepEqual((await b.call('/api/panel/requests')).body.requests, []);
  assert.deepEqual(await b.call('/api/panel/requests/1/close', {}),
    {status: 404, body: {detail: 'Solicitud no encontrada'}});
  await b.call('/api/demo/reset', {session_id: 'guest'});
  assert.deepEqual(await a.call('/api/demo/conversation?session_id=guest'), before);
  await b.call('/api/demo/chat', {session_id: 'guest', message: 'Recepción', shift: 'open'});
  assert.equal((await b.call('/api/panel/requests')).body.requests[0].id, 1, 'contador independiente');
  await peer.call('/api/demo/session', {name: 'Sofía', operator_key: 'operador-estatico-0001'});
  await peer.call('/api/panel/requests/1/take', {});
  assert.equal((await a.call('/api/panel/requests')).body.requests[0].status, 'en_atencion');
  const shared = await a.call('/api/demo/conversation?session_id=guest');
  assert.deepEqual(await b.call('/api/demo/reset', {session_id: 'guest'}), {status: 200, body: {status: 'ok'}});
  assert.equal((await b.call('/api/demo/conversation?session_id=guest')).body.conversation_id, null);
  assert.deepEqual((await b.call('/api/panel/requests')).body.requests, []);
  assert.deepEqual(await a.call('/api/demo/conversation?session_id=guest'), shared);
});

test('body, query and staff header select the same corrida after creating a run', async () => {
  const {call} = loadShim({run: null});
  const first = await call('/api/demo/run', {});
  const second = await call('/api/demo/run', {});
  assert.equal(first.status, 201);
  assert.equal(second.status, 201);
  assert.notEqual(first.body.run, second.body.run);
  const run = first.body.run;
  await call('/api/demo/chat', {run, session_id: 'guest', message: 'Recepción'});
  assert.ok((await call(`/api/demo/conversation?session_id=guest&run=${run}`)).body.request);
  assert.equal((await call(`/api/demo/conversation?session_id=guest&run=${second.body.run}`)).body.request, null);
  await call('/api/demo/session', {run, name: 'Sofía', operator_key: 'operador-estatico-0001'});
  const inbox = await call('/api/panel/requests', undefined, {'X-Demo-Run': run});
  assert.equal(inbox.body.requests.length, 1);
  assert.equal((await call('/api/panel/requests', undefined, {'X-Demo-Run': second.body.run})).status, 401);
});

test('take and close require the actual operator, not a matching display name, without mutation on rejection', async () => {
  const {call} = loadShim();
  await call('/api/demo/chat', {session_id: 'guest', message: 'Recepción', shift: 'open'});
  const login = operator_key => call('/api/demo/session', {name: 'Sofía', operator_key});
  await login('operador-estatico-0001');
  const snapshot = async () => ({inbox: await call('/api/panel/requests'),
    guest: await call('/api/demo/conversation?session_id=guest')});
  const rejected = async (action, detail, body = {}) => {
    const before = await snapshot();
    const response = await call(`/api/panel/requests/1/${action}`, body);
    assert.equal(response.status, 409);
    assert.equal(response.body.detail, detail);
    assert.deepEqual(response.body.request, before.inbox.body.requests[0]);
    assert.deepEqual(await snapshot(), before, 'rechazo no cambia mensajes, eventos, datos ni contadores visibles');
  };
  await rejected('close', 'Toma la solicitud antes de cerrar');
  assert.equal((await call('/api/panel/requests/1/take', {})).status, 200);
  const taken = await snapshot();
  assert.equal((await call('/api/panel/requests/1/take', {})).status, 200);
  assert.deepEqual(await snapshot(), taken, 'tomar de nuevo es idempotente');
  await login('operador-estatico-0002');
  const actions = (await call('/api/panel/requests')).body.requests[0].actions;
  assert.equal(actions.reply, false);
  assert.equal(actions.close, false);
  await rejected('take', 'Ya la tomó Sofía');
  await rejected('close', 'La atiende Sofía');
  await rejected('reply', 'La atiende Sofía', {body: 'No autorizado', client_id: 'rechazada'});
  await login('operador-estatico-0001');
  const previousId = (await call('/api/panel/requests')).body.requests[0].messages.at(-1).id;
  const reply = await call('/api/panel/requests/1/reply', {body: 'Respuesta autorizada', client_id: 'rechazada'});
  assert.equal(reply.status, 200);
  assert.equal(reply.body.duplicate, false, 'el rechazo no consume la llave de idempotencia');
  assert.equal(reply.body.message.id, previousId + 1, 'el rechazo no consume el contador de mensajes');
  assert.equal((await call('/api/panel/requests/1/close', {})).body.status, 'cerrada');
  const closed = await snapshot();
  assert.equal((await call('/api/panel/requests/1/close', {})).status, 200);
  assert.deepEqual(await snapshot(), closed, 'cerrar de nuevo es idempotente');
  await rejected('take', 'La solicitud está cerrada');
  await rejected('reply', 'La solicitud está cerrada', {body: 'No reabrir'});
});

test('the static demo declares itself and never interprets HTML', () => {
  assert.match(shim, /WhatsApp simulado · versión estática/, 'el canal se rotula como versión estática');
  assert.doesNotMatch(shim, /innerHTML/, 'el shim no interpreta HTML');
  assert.doesNotMatch(shim, /963949710|comercial@/i, 'nunca el contacto real del hotel');
});

// --- El guion guiado de la versión estática responde como el copiloto ---------------------------
const MISSING = 'Ese dato no lo tengo confirmado. Si quieres, lo consulto con recepción.';

async function guestSays(text, {run} = {}) {
  const shim = loadShim(run ? {run} : {});
  await shim.call('/api/demo/chat', {session_id: 'guest', message: text, shift: 'open'});
  const conversation = (await shim.call('/api/demo/conversation?session_id=guest')).body;
  return {shim, messages: conversation.messages.filter(message => message.role === 'assistant')};
}

test('un saludo se responde con un saludo y opciones, no con «no te entendí»', async () => {
  const {messages} = await guestSays('hola');
  const last = messages.at(-1).body;
  assert.match(last, /hola, bienvenido/i);
  assert.ok(!/no estoy seguro|no te entend/i.test(last), last);
  assert.ok(messages.at(-1).options.length >= 3, 'ofrece el menú');
});

test('preguntar si es una IA se responde con la identidad, sin derivar', async () => {
  const {shim, messages} = await guestSays('¿eres una persona o una IA?');
  assert.match(messages.at(-1).body, /asistente virtual/i);
  assert.ok(!/solicitud (enviada|guardada)/i.test(messages.at(-1).body), 'no deriva por preguntar quién es');
  await shim.call('/api/demo/session', {name: 'Ana', operator_key: 'operador-estatico-0002'});
  assert.deepEqual((await shim.call('/api/panel/requests')).body.requests, []);
});

test('un dato fuera del catálogo usa la frase fija, no una invención', async () => {
  const {messages} = await guestSays('¿tienen helipuerto?');
  assert.equal(messages.at(-1).body, MISSING);
});

test('pedir hablar con recepción sí deriva y deja la solicitud con su número', async () => {
  const {shim, messages} = await guestSays('quiero hablar con recepción');
  assert.match(messages.at(-1).body, /N\.º BDL-001/);
  await shim.call('/api/demo/session', {name: 'Ana', operator_key: 'operador-estatico-0003'});
  const requests = (await shim.call('/api/panel/requests')).body.requests;
  assert.equal(requests.length, 1);
  assert.equal(requests[0].code, 'BDL-001');
  assert.equal(requests[0].reason_label, 'Pidió hablar con recepción');
});

// --- Con IA configurada, la respuesta conversacional la da la función de Vercel -------------------
const AI_CONFIG = {staticDemo: true, aiChat: true};

test('con aiChat la charla la responde el modelo y queda en el hilo', async () => {
  const shim = loadShim({
    config: AI_CONFIG,
    fetchImpl: async () => new Response(JSON.stringify({reply: 'Hola, soy el asistente del hotel. ¿En qué te ayudo?'}), {status: 200}),
  });
  const response = await shim.call('/api/demo/chat', {session_id: 'guest', message: 'buenas tardes', shift: 'open'});
  assert.equal(response.status, 200);
  assert.equal(response.body.mode, 'ai');
  assert.match(response.body.reply, /asistente del hotel/);
  const conversation = (await shim.call('/api/demo/conversation?session_id=guest')).body;
  assert.equal(conversation.messages.at(-1).body, 'Hola, soy el asistente del hotel. ¿En qué te ayudo?');
});

test('si la IA no responde, sigue el guion sin dejar mensajes a medias', async () => {
  const shim = loadShim({
    config: AI_CONFIG,
    fetchImpl: async () => new Response('{"detail":"sin ia"}', {status: 503}),
  });
  const response = await shim.call('/api/demo/chat', {session_id: 'guest', message: 'buenas tardes', shift: 'open'});
  assert.equal(response.body.mode, 'guided');
  const conversation = (await shim.call('/api/demo/conversation?session_id=guest')).body;
  const guests = conversation.messages.filter(message => message.role === 'guest');
  assert.equal(guests.length, 1, 'un solo turno del huésped, sin duplicados');
  const answers = conversation.messages.filter(message => message.role === 'assistant');
  assert.ok(answers.length >= 1, 'el guion responde');
  assert.match(answers.at(-1).body, /hola, bienvenido/i, 'y la última respuesta es la del guion');
});

test('una fecha dicha como persona la interpreta el modelo y la disponibilidad aparece después', async () => {
  let called = 0;
  const shim = loadShim({
    config: AI_CONFIG,
    fetchImpl: async () => {
      called += 1;
      return new Response(JSON.stringify({
        reply: 'Claro, el viernes 13 al domingo 15. Déjame ver qué tenemos.',
        stay: {checkin: '2026-11-13', checkout: '2026-11-15', adults: 2, children: 1},
      }), {status: 200});
    },
  });
  const response = await shim.call('/api/demo/chat', {session_id: 'guest', message: 'quería algo para el próximo fin de semana, somos dos y una niña', shift: 'open'});
  assert.equal(called, 1, 'la fecha natural la entiende el modelo, no un formato rígido');
  assert.equal(response.body.mode, 'ai');
  const texto = (await shim.call('/api/demo/conversation?session_id=guest')).body.messages.map(m => m.body).join(String.fromCharCode(10));
  assert.match(texto, /viernes 13 al domingo 15/, 'la respuesta del modelo queda en el hilo');
  assert.match(texto, /Revisa tu solicitud antes de enviarla/, 'y la estadía se muestra con la disponibilidad');
  assert.match(texto, /2 adultos, 1 niño/);
});

test('pedir recepción no pasa por el modelo: crea la solicitud', async () => {
  let called = 0;
  const shim = loadShim({
    config: AI_CONFIG,
    fetchImpl: async () => { called += 1; return new Response(JSON.stringify({reply: 'no debería usarse'}), {status: 200}); },
  });
  const response = await shim.call('/api/demo/chat', {session_id: 'guest', message: 'quiero hablar con recepción', shift: 'open'});
  assert.equal(called, 0, 'la derivación se resuelve en local');
  assert.notEqual(response.body.mode, 'ai');
  await shim.call('/api/demo/session', {name: 'Ana', operator_key: 'operador-estatico-0009'});
  const requests = (await shim.call('/api/panel/requests')).body.requests;
  assert.equal(requests.length, 1);
});

test('la voz no se simula: /api/demo/tts viaja a la red', async () => {
  const shim = loadShim({
    config: {staticDemo: true, aiChat: true, voice: true},
    fetchImpl: async (url, _init, calls) => {
      calls.push(String(url));
      return new Response(new Uint8Array([1, 2, 3]), {status: 200, headers: {'content-type': 'audio/mpeg'}});
    },
  });
  // La respuesta es audio, no JSON: el helper de pruebas no puede parsearla, pero lo que importa es
  // que la petición haya salido hacia la función en vez de quedar simulada en el navegador.
  await assert.rejects(() => shim.call('/api/demo/tts', {text: 'hola'}));
  assert.ok(shim.calls.some(url => String(url).includes('/api/demo/tts')), 'sale del shim hacia la función');
});

test('cuando el modelo deriva, la solicitud se crea con su número', async () => {
  const shim = loadShim({
    config: AI_CONFIG,
    fetchImpl: async () => new Response(JSON.stringify({
      reply: 'Listo, Camila: aviso a recepción.',
      stay: {checkin: '2026-11-13', checkout: '2026-11-15', adults: 2, children: 1},
      handoff: {name: 'Camila', reason: 'consulta de fechas'},
    }), {status: 200}),
  });
  await shim.call('/api/demo/chat', {session_id: 'guest', message: 'envíalo a recepción, soy Camila', shift: 'open'});
  await shim.call('/api/demo/session', {name: 'Ana', operator_key: 'operador-estatico-0011'});
  const requests = (await shim.call('/api/panel/requests')).body.requests;
  assert.equal(requests.length, 1, 'la derivación del modelo crea la solicitud');
  assert.equal(requests[0].code, 'BDL-001');
  assert.equal(requests[0].checkin, '2026-11-13');
});

test('los botones de confirmar siguen ahí después de otra pregunta', async () => {
  let round = 0;
  const shim = loadShim({
    config: AI_CONFIG,
    fetchImpl: async () => {
      round += 1;
      if (round === 1) {
        return new Response(JSON.stringify({reply: 'Tenemos opciones para esas fechas.', stay: {
          checkin: '2026-11-20', checkout: '2026-11-22', adults: 2, children: 1}}, ), {status: 200});
      }
      return new Response(JSON.stringify({reply: 'La política de mascotas no está publicada; recepción te confirma.'}), {status: 200});
    },
  });
  await shim.call('/api/demo/chat', {session_id: 'guest', message: 'del 20 al 22 para dos y un niño', shift: 'open'});
  const segunda = await shim.call('/api/demo/chat', {session_id: 'guest', message: 'y llevo a mi perro', shift: 'open'});
  const opciones = segunda.body.messages.at(-1).options || [];
  assert.ok(opciones.includes('Enviar a recepción'), `opciones: ${opciones}`);
});
