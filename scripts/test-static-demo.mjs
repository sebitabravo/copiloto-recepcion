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
const frontend = ['landing/demo.js', 'landing/console.js', 'landing/voice.js'].map(read).join('\n');

// Rutas que el frontend pide de verdad: si una no está interceptada, la demo estática llama a la red.
const requested = [...new Set([...frontend.matchAll(/['"`](\/(?:api|metricas)\/[^'"`]*?)['"`]/g)]
  .map(([, path]) => path.replace(/\$\{[^}]*\}/g, 'x').replace(/\?.*$/, ''))
  .filter(path => path !== '/api/' && path !== '/metricas/'))];

// Carga el shim en un DOM mínimo y devuelve el fetch interceptado junto al real (espía).
function loadShim() {
  const calls = [];
  const element = () => ({hidden: false, removeAttribute() {}, prepend() {}, style: {cssText: ''}, setAttribute() {}});
  const document = {
    addEventListener() {},
    createElement: element,
    getElementById: () => null,
    querySelectorAll: () => [],
    body: element()
  };
  const realFetch = (...args) => { calls.push(args[0]); return Promise.resolve(new Response('{}', {status: 200})); };
  const window = {fetch: realFetch};
  vm.runInNewContext(shim, {window, document, Response, RegExp, JSON, Date, console});
  return {fetch: window.fetch, calls};
}

test('every endpoint the frontend calls is intercepted by the static shim', async () => {
  const {fetch, calls} = loadShim();
  for (const path of requested) {
    const method = /chat|reply|reset|voice|session/.test(path) ? 'POST' : 'GET';
    const response = await fetch(`http://localhost:8100${path}`, method === 'POST' ? {method, body: '{"message":"piscina"}'} : {});
    assert.ok(response instanceof Response, `${path} no devolvió una respuesta simulada`);
    await response.json().catch(() => null);
  }
  assert.deepEqual(calls, [], `salieron a la red: ${calls.join(', ')}`);
});

test('the static build replaces the public URL everywhere and leaks no secrets', () => {
  const work = mkdtempSync(join(tmpdir(), 'static-demo-'));
  try {
    execFileSync('bash', [join(root, 'scripts/build-static-demo.sh')], {
      cwd: root,
      env: {...process.env, PUBLIC_SITE_URL: 'https://example.test', STATIC_DEMO_OUT: work},
      stdio: 'pipe'
    });
    const files = readdirSync(work).filter(name => statSync(join(work, name)).isFile());
    for (const name of files.filter(file => /\.(html|txt|xml)$/.test(file))) {
      assert.doesNotMatch(readFileSync(join(work, name), 'utf8'), /__PUBLIC_SITE_URL__/, name);
    }
    const config = readFileSync(join(work, 'config.js'), 'utf8');
    assert.doesNotMatch(config, /https?:\/\/|localhost/i, 'config.js estático no lleva hosts');
    assert.match(config, /websiteToken: ""/, 'config.js estático no lleva el token de Chatwoot');
    const demo = readFileSync(join(work, 'demo.html'), 'utf8');
    const shimTag = demo.indexOf('src="static-demo.js"');
    const appTag = demo.indexOf('src="demo.js');
    assert.ok(shimTag > -1 && appTag > -1 && shimTag < appTag, 'el shim se carga antes que demo.js');
  } finally {
    rmSync(work, {recursive: true, force: true});
  }
});

test('the build only ever cleans its own output directory', () => {
  const script = read('scripts/build-static-demo.sh');
  // OUT solo puede salir de la raíz del repo o de STATIC_DEMO_OUT, siempre entre comillas.
  assert.match(script, /OUT="\$\{STATIC_DEMO_OUT:-\$ROOT\/dist\}"/);
  assert.match(script, /rm -rf "\$OUT" 2>\/dev\/null \|\| true/);
  assert.match(script, /find "\$OUT" -mindepth 1 -maxdepth 1/);
  assert.doesNotMatch(script, /rm -rf "\$ROOT"/, 'nunca se borra la raíz del repo');

  const work = mkdtempSync(join(tmpdir(), 'static-demo-safe-'));
  try {
    const out = join(work, 'out');
    writeFileSync(join(work, 'KEEP.txt'), 'sentinel');
    execFileSync('bash', [join(root, 'scripts/build-static-demo.sh')], {
      cwd: root,
      env: {...process.env, PUBLIC_SITE_URL: 'https://example.test', STATIC_DEMO_OUT: out},
      stdio: 'pipe'
    });
    assert.equal(readFileSync(join(work, 'KEEP.txt'), 'utf8'), 'sentinel', 'no toca archivos vecinos');
    assert.ok(existsSync(join(out, 'demo.html')));
  } finally {
    rmSync(work, {recursive: true, force: true});
  }
});

test('the static demo declares itself and hides what it cannot serve', () => {
  assert.doesNotMatch(shim, /static-demo-banner/, 'sin banda fija que tape la página');
  // La honestidad la aporta la interfaz («Flujo guiado · sin IA»), no un cartel añadido.
  for (const id of ['privacy-link', 'footer-metrics', 'en-vivo']) assert.match(shim, new RegExp(id));
  assert.doesNotMatch(shim, /innerHTML/, 'el shim no interpreta HTML');
});
