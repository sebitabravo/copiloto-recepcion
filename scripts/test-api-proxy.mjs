import test from 'node:test';
import assert from 'node:assert/strict';

const {targetUrl, proxy} = await import('../api/[...path].mjs');

test('la ruta se arma con el prefijo del backend y conserva la consulta', () => {
  assert.equal(targetUrl('https://copiloto.hotel.cl', '/api/demo/status'),
    'https://copiloto.hotel.cl/api/demo/status');
  assert.equal(targetUrl('https://copiloto.hotel.cl/', '/api/panel/requests?selected=1'),
    'https://copiloto.hotel.cl/api/panel/requests?selected=1');
  assert.equal(targetUrl('https://hotel.cl/copiloto', '/api/demo/chat'),
    'https://hotel.cl/copiloto/api/demo/chat');
});

test('sin COPILOTO_URL el endpoint lo dice y no llama a nadie', async () => {
  let called = false;
  const result = await proxy({method: 'GET', url: '/api/demo/status', headers: {}}, {
    base: '', fetchImpl: async () => { called = true; return new Response('{}'); },
  });
  assert.equal(result.status, 503);
  assert.match(result.body, /COPILOTO_URL/);
  assert.equal(called, false);
});

test('reenvía método, cuerpo y cabeceras propias, y descarta las de salto', async () => {
  let seen;
  const result = await proxy({method: 'POST', url: '/api/demo/chat', headers: {cookie: 'panel=abc', host: 'x', 'accept-encoding': 'gzip'}, body: {message: 'hola'}}, {
    base: 'https://copiloto.hotel.cl',
    fetchImpl: async (url, init) => {
      seen = {url, init};
      return new Response(JSON.stringify({reply: 'ok'}), {status: 201, headers: {'content-type': 'application/json', 'transfer-encoding': 'chunked'}});
    },
  });
  assert.equal(seen.url, 'https://copiloto.hotel.cl/api/demo/chat');
  assert.equal(seen.init.method, 'POST');
  assert.equal(seen.init.body, JSON.stringify({message: 'hola'}));
  assert.equal(seen.init.headers.get('cookie'), 'panel=abc');
  assert.equal(seen.init.headers.has('host'), false);
  assert.equal(seen.init.headers.has('accept-encoding'), false);
  assert.equal(result.status, 201);
  assert.equal(result.headers.has('transfer-encoding'), false);
  assert.equal(JSON.parse(result.body.toString()).reply, 'ok');
});

test('un backend caído se reporta como 502, no como éxito vacío', async () => {
  const result = await proxy({method: 'GET', url: '/api/demo/status', headers: {}}, {
    base: 'https://copiloto.hotel.cl',
    fetchImpl: async () => { throw new Error('connect ECONNREFUSED'); },
  });
  assert.equal(result.status, 502);
  assert.match(result.body, /ECONNREFUSED/);
});
