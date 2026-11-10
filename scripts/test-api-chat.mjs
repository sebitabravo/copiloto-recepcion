import test from 'node:test';
import assert from 'node:assert/strict';

const {ask, buildMessages} = await import('../api/demo/chat.mjs');

const KEY = 'clave-de-prueba';

test('sin clave responde 503 y no llama al modelo', async () => {
  let called = false;
  const result = await ask('hola', [], {key: '', fetchImpl: async () => { called = true; return new Response('{}'); }});
  assert.equal(result.status, 503);
  assert.match(result.body, /LLM_API_KEY/);
  assert.equal(called, false);
});

test('el mensaje del sistema lleva los datos aprobados y las reglas del copiloto', () => {
  const messages = buildMessages('¿tienen piscina?', []);
  assert.equal(messages[0].role, 'system');
  assert.equal(messages.at(-1).role, 'user');
  assert.equal(messages.filter(m => m.role === 'system').length, 1, 'un solo system, al inicio');
  const system = messages[0].content;
  assert.match(system, /primera persona plural/);
  assert.match(system, /Nunca confirmas reservas/);
  assert.match(system, /piscina temperada/i, 'los hechos del hotel viajan en el prompt');
  assert.match(system, /Villarrica|Molco|playa/i, 'la ubicación viaja en el prompt');
});

test('la conversación previa entra como historial acotado', () => {
  const history = Array.from({length: 20}, (_, i) => ({role: i % 2 ? 'assistant' : 'guest', text: `turno ${i}`}));
  const messages = buildMessages('¿y el desayuno?', history);
  assert.equal(messages.length, 8 + 1 + 1, "system + 8 turnos + el mensaje actual");
  assert.equal(messages[1].role, 'user');
  assert.equal(messages[2].role, 'assistant');
});

test('una respuesta del modelo se limpia de Markdown y se recorta', async () => {
  const result = await ask('hola', [], {
    key: KEY,
    fetchImpl: async () => new Response(JSON.stringify({choices: [{message: {content: '**Hola.** Tenemos piscina.'}}]}), {status: 200}),
  });
  assert.equal(result.status, 200);
  assert.equal(result.body.reply, 'Hola. Tenemos piscina.');
});

test('un error del proveedor no se muestra como respuesta buena', async () => {
  const result = await ask('hola', [], {key: KEY, fetchImpl: async () => new Response('nope', {status: 429})});
  assert.equal(result.status, 502);
  assert.match(result.body, /429/);
});

test('el modelo se llama con la temperatura baja y el tope de tokens del copiloto', async () => {
  let sent;
  await ask('hola', [], {
    key: KEY,
    base: 'https://api.deepseek.com/',
    model: 'deepseek-chat',
    fetchImpl: async (url, init) => {
      sent = {url, init};
      return new Response(JSON.stringify({choices: [{message: {content: 'Hola.'}}]}), {status: 200});
    },
  });
  assert.equal(sent.url, 'https://api.deepseek.com/chat/completions');
  assert.equal(sent.init.headers.authorization, `Bearer ${KEY}`);
  const payload = JSON.parse(sent.init.body);
  assert.equal(payload.model, 'deepseek-chat');
  assert.equal(payload.temperature, 0.2);
  assert.ok(payload.max_tokens <= 300);
});

test('el tope por IP frena un bucle antes de gastar saldo', async () => {
  const {allow} = await import('../api/demo/chat.mjs');
  const now = Date.parse('2026-11-10T12:00:00Z');
  const results = Array.from({length: 21}, () => allow('203.0.113.7', now));
  assert.equal(results.filter(Boolean).length, 20, 'veinte pasan');
  assert.equal(results.at(-1), false, 'la vigésima primera se rechaza');
  assert.equal(allow('203.0.113.7', now + 61_000), true, 'al minuto siguiente vuelve a pasar');
  assert.equal(allow('198.51.100.9', now), true, 'otra IP no se ve afectada');
});
