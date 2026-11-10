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
  assert.match(system, /Nunca confirmas una reserva/);
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
  assert.equal(payload.temperature, 0.3);
  assert.ok(Array.isArray(payload.tools) && payload.tools.length >= 1, 'la herramienta de estadía viaja al modelo');
  assert.ok(payload.max_tokens <= 320);
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

test('una fecha natural se normaliza con la herramienta y vuelve en la respuesta', async () => {
  let round = 0;
  const result = await ask('quería algo para el próximo fin de semana, somos dos y una niña', [], {
    key: KEY,
    fetchImpl: async () => {
      round += 1;
      if (round === 1) {
        return new Response(JSON.stringify({choices: [{message: {tool_calls: [{
          id: 'call-1', type: 'function',
          function: {name: 'registrar_estadia', arguments: JSON.stringify({checkin: '2026-11-13', checkout: '2026-11-15', adults: 2, children: 1})},
        }]}}]}), {status: 200});
      }
      return new Response(JSON.stringify({choices: [{message: {content: 'Perfecto: del viernes 13 al domingo 15, dos adultos y una niña.'}}]}), {status: 200});
    },
  });
  assert.equal(result.status, 200);
  assert.match(result.body.reply, /viernes 13/);
  assert.deepEqual(result.body.stay, {checkin: '2026-11-13', checkout: '2026-11-15', adults: 2, children: 1});
});

test('el modelo recibe el resultado de la herramienta antes de contestar', async () => {
  const seen = [];
  let round = 0;
  await ask('del 20 al 23 de diciembre para 3', [], {
    key: KEY,
    fetchImpl: async (_url, init) => {
      seen.push(JSON.parse(init.body).messages);
      round += 1;
      if (round === 1) {
        return new Response(JSON.stringify({choices: [{message: {tool_calls: [{
          id: 'call-9', type: 'function',
          function: {name: 'registrar_estadia', arguments: JSON.stringify({checkin: '2026-12-20', checkout: '2026-12-23', adults: 3})},
        }]}}]}), {status: 200});
      }
      return new Response(JSON.stringify({choices: [{message: {content: 'Listo.'}}]}), {status: 200});
    },
  });
  const toolMessage = seen[1].find(m => m.role === 'tool');
  assert.ok(toolMessage, 'la segunda llamada lleva el resultado de la herramienta');
  assert.match(toolMessage.content, /"ok":true/);
  assert.match(toolMessage.content, /2026-12-20/);
});

test('una estadía imposible no se acepta', async () => {
  const result = await ask('del 20 al 18 de diciembre para 2', [], {
    key: KEY,
    fetchImpl: async () => new Response(JSON.stringify({choices: [{message: {tool_calls: [{
      id: 'call-2', type: 'function',
      function: {name: 'registrar_estadia', arguments: JSON.stringify({checkin: '2026-12-20', checkout: '2026-12-18', adults: 2})},
    }]}}]}), {status: 200}),
  });
  assert.equal(result.body.stay, undefined, 'la salida antes de la llegada no se registra');
});

test('pasar a recepción pide el nombre cuando falta y devuelve la derivación', async () => {
  let round = 0;
  const result = await ask('envíalo a recepción, soy Camila', [], {
    key: KEY,
    fetchImpl: async () => {
      round += 1;
      if (round === 1) {
        return new Response(JSON.stringify({choices: [{message: {tool_calls: [{
          id: 'call-h', type: 'function',
          function: {name: 'pasar_a_recepcion', arguments: JSON.stringify({nombre: 'Camila', motivo: 'consulta de fechas'})},
        }]}}]}), {status: 200});
      }
      return new Response(JSON.stringify({choices: [{message: {content: 'Listo, Camila: aviso a recepción.'}}]}), {status: 200});
    },
  });
  assert.equal(result.status, 200);
  assert.deepEqual(result.body.handoff, {name: 'Camila', reason: 'consulta de fechas'});
  assert.match(result.body.reply, /aviso a recepción/);
});
