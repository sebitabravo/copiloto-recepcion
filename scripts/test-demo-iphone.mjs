import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const root = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const html = readFileSync(`${root}/landing/demo.html`, 'utf8');
const css = readFileSync(`${root}/landing/demo-console.css`, 'utf8');

// El marco es decoración: nada del iPhone debe llegar al lector de pantalla.
test('the iPhone chrome stays out of the accessibility tree', () => {
  for (const marker of ['class="dynamic-island" aria-hidden="true"',
    'class="home-indicator" aria-hidden="true"',
    'class="wa-status" aria-hidden="true"']) {
    assert.ok(html.includes(marker), `falta ${marker}`);
  }
  // Las etiquetas visibles de la llamada no duplican el nombre del botón.
  const labels = [...html.matchAll(/<span class="call-action-label"([^>]*)>/g)];
  assert.equal(labels.length, 2);
  for (const [, attrs] of labels) assert.match(attrs, /aria-hidden="true"/);
});

test('each call control keeps exactly one accessible name', () => {
  for (const id of ['voice-talk', 'voice-hangup']) {
    const tag = html.match(new RegExp(`<button id="${id}"[^>]*>`))[0];
    assert.equal((tag.match(/aria-label=/g) || []).length, 1, `${id} debe tener un solo aria-label`);
    assert.match(tag, /title=/);
  }
  assert.match(html, /id="call-timer"[^>]*aria-hidden="true"/);
});

test('the phone styles never leak into the operational cards', () => {
  const phoneRules = css.split('}').filter(rule => /\.phone\b|\.call-screen/.test(rule));
  assert.ok(phoneRules.length > 0);
  for (const rule of phoneRules) {
    assert.doesNotMatch(rule, /\.console-card|\.tab-panel/, 'el marco no redefine tarjetas operativas');
  }
  // El redondeo del marco vive solo en `.demo-phone .phone`.
  const radius = css.split('}').filter(rule => /border-radius:\s*48px/.test(rule));
  assert.equal(radius.length, 1);
  assert.match(radius[0], /\.demo-phone \.phone/);
});

test('demo.html pins the newest console stylesheet once', () => {
  const pins = [...html.matchAll(/demo-console\.css\?v=([0-9a-z]+)/g)].map(([, version]) => version);
  assert.equal(pins.length, 1, 'un solo pin de demo-console.css');
  const cssPins = [`${root}/landing/index.html`].map(file => readFileSync(file, 'utf8'))
    .join('\n').match(/demo-console\.css/g) || [];
  assert.equal(cssPins.length, 0, 'la portada no carga los estilos de la consola');
});
