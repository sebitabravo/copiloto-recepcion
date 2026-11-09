import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import vm from 'node:vm';

const root = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const read = name => readFileSync(join(root, name), 'utf8');
const chrome = read('landing/site.js');

// Un enlace por servicio, como en index.html: el HTML deja /demo y site.js lo reescribe.
function links() {
  return ['inbox', 'pms', 'metrics'].map(service => ({
    dataset: {service},
    href: '/demo',
    attrs: {target: '_blank', rel: 'noopener'},
    getAttribute(name) { return name === 'href' ? this.href : this.attrs[name]; },
    setAttribute(name, value) { this.attrs[name] = value; },
    removeAttribute(name) { delete this.attrs[name]; },
  }));
}

// Carga el chrome de la landing con la config que escribe el build y devuelve los enlaces resueltos.
function run({config, hostname = 'copiloto-recepcion.vercel.app', protocol = 'https:'}) {
  const anchors = links();
  const window = {
    COPILOTO_CONFIG: config,
    location: {protocol, hostname, href: `${protocol}//${hostname}/`, host: hostname},
    matchMedia: () => ({matches: true}),
    addEventListener() {},
    requestAnimationFrame: fn => fn(),
    scrollY: 0,
    innerHeight: 900,
    IntersectionObserver: undefined,
  };
  const document = {
    querySelectorAll: selector => (selector === 'a[data-service]' ? anchors : []),
    getElementById: () => null,
    documentElement: {scrollHeight: 1000},
  };
  vm.runInNewContext(chrome, {window, document, location: window.location, URL, Math, String, Number, Object, console});
  return anchors;
}

const STATIC = {chatwootUrl: '', copilotoUrl: '', pmsUrl: '', websiteToken: '', privacyUrl: '', staticDemo: true};

test('publicado sin backend, los enlaces a servicios abren su vista de la consola', () => {
  const by = Object.fromEntries(run({config: STATIC}).map(anchor => [anchor.dataset.service, anchor]));
  assert.equal(by.pms.href, '/demo?vista=admin', 'el PMS se explica en Administración');
  assert.equal(by.metrics.href, '/demo?vista=recepcion', 'las métricas viven en la bandeja');
  assert.equal(by.inbox.href, '/demo');
  for (const anchor of Object.values(by)) {
    assert.ok(!/:(3000|8100|8200)/.test(anchor.href), anchor.href);
    assert.equal(anchor.attrs.target, undefined, 'sin servicio no se abre otra pestaña');
  }
});

test('con el stack completo, cada servicio usa su puerto en el host de la página', () => {
  const anchors = run({config: {}});
  const by = Object.fromEntries(anchors.map(anchor => [anchor.dataset.service, anchor.href]));
  assert.equal(by.pms, 'https://copiloto-recepcion.vercel.app:8200/admin');
  assert.equal(by.metrics, 'https://copiloto-recepcion.vercel.app:8100/metricas');
  assert.equal(by.inbox, '/demo', 'la bandeja es la consola, no un servicio aparte');
});

test('una config explícita manda sobre el host y el puerto', () => {
  const anchors = run({config: {pmsUrl: 'https://pms.hotel.cl', copilotoUrl: 'https://api.hotel.cl'}});
  const by = Object.fromEntries(anchors.map(anchor => [anchor.dataset.service, anchor.href]));
  assert.equal(by.pms, 'https://pms.hotel.cl/admin');
  assert.equal(by.metrics, 'https://api.hotel.cl/metricas');
});

test('una demo por LAN conserva el host de la página', () => {
  const anchors = run({config: {}, hostname: '192.168.1.20', protocol: 'http:'});
  const by = Object.fromEntries(anchors.map(anchor => [anchor.dataset.service, anchor.href]));
  assert.equal(by.pms, 'http://192.168.1.20:8200/admin');
});
