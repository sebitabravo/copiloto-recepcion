import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../landing/demo.html', import.meta.url), 'utf8');
const scriptUrl = new URL('../landing/demo-journey.js', import.meta.url);
// An absent module is the pre-implementation baseline, not a test-loader failure.
const source = existsSync(scriptUrl) ? readFileSync(scriptUrl, 'utf8') : '';
const roles = ['huesped', 'recepcion', 'admin'];

// Tiny HTML-backed DOM: production journey handlers run unchanged. Existing owners
// (console.js / demo.js) are represented by click spies, never network calls.
function app(hash = '') {
  const nodes = [];
  let document;
  class Element {
    constructor(tag, attrs = {}) {
      this.tagName = tag; this.attrs = attrs; this.children = []; this.listeners = {};
      this.dataset = {};
      for (const [key, value] of Object.entries(attrs)) {
        if (key.startsWith('data-')) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
      }
      this.hidden = 'hidden' in attrs; this.open = 'open' in attrs;
      this.disabled = 'disabled' in attrs; this.textContent = ''; this.clicks = 0;
      const classes = new Set((attrs.class || '').split(/\s+/));
      this.classList = {
        contains: name => classes.has(name),
        toggle(name, force = !classes.has(name)) { force ? classes.add(name) : classes.delete(name); return force; }
      };
    }
    getAttribute(name) { return this.attrs[name] ?? null; }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
    focus() { document.activeElement = this; }
    scrollIntoView() { this.scrolled = true; }
    closest(selector) {
      for (let node = this; node; node = node.parentElement) if (matches(node, selector)) return node;
      return null;
    }
    click() {
      if (this.disabled) return;
      this.clicks += 1;
      const event = {target: this, preventDefault() { this.defaultPrevented = true; }};
      for (const listener of this.listeners.click || []) listener(event);
      if (this.tagName === 'summary' && !event.defaultPrevented) {
        this.parentElement.open = !this.parentElement.open;
        this.parentElement.emit('toggle');
      }
    }
    emit(type) { for (const listener of this.listeners[type] || []) listener({target: this}); }
  }
  function matches(node, selector) {
    if (selector.startsWith('#')) return node.attrs.id === selector.slice(1);
    const match = /^(\w+)?\[([^=\]]+)(?:="([^"]*)")?\]$/.exec(selector);
    if (match) return (!match[1] || node.tagName === match[1]) && match[2] in node.attrs && (match[3] === undefined || node.attrs[match[2]] === match[3]);
    return node.tagName === selector;
  }
  const stack = [];
  for (const token of html.matchAll(/<!--[\s\S]*?-->|<\/?[a-z][^>]*>/gi)) {
    const raw = token[0];
    if (raw.startsWith('<!--')) continue;
    const tag = /^<\/?([a-z0-9-]+)/i.exec(raw)[1];
    if (raw.startsWith('</')) { while (stack.length && stack.pop().tagName !== tag) {} continue; }
    const attrs = Object.fromEntries([...raw.slice(tag.length + 1, -1).matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(([, key, value]) => [key, value ?? '']));
    const node = new Element(tag, attrs);
    node.parentElement = stack.at(-1);
    node.parentElement?.children.push(node); nodes.push(node);
    if (!['meta', 'link', 'input', 'br', 'img', 'hr', 'source', 'path', 'rect', 'circle'].includes(tag)) stack.push(node);
  }
  const get = id => nodes.find(node => node.attrs.id === id);
  const queryAll = selector => nodes.filter(node => selector.split(',').some(part => matches(node, part.trim())));
  document = {getElementById: get, querySelectorAll: queryAll, activeElement: null};
  const location = {pathname: '/demo', search: '?tour=1', hash};
  const windowListeners = {};
  const window = {location, addEventListener(type, listener) { (windowListeners[type] ||= []).push(listener); }};
  // These spies enforce reuse of the established click path and tab state.
  for (const role of roles) get(`tab-${role}`).addEventListener('click', () => {
    for (const other of roles) {
      get(`tab-${other}`).setAttribute('aria-selected', String(other === role));
      get(`panel-${other}`).hidden = other !== role;
    }
  });
  get('toggle-actions').addEventListener('click', () => {
    const panel = get('actions-panel'); panel.hidden = !panel.hidden;
    get('toggle-actions').setAttribute('aria-expanded', String(!panel.hidden));
  });
  vm.runInNewContext(source, {document, window, location});
  return {get, queryAll, document, location, hashchange(hash) {
    location.hash = hash; for (const listener of windowListeners.hashchange || []) listener();
  }};
}

for (const role of roles) test(`journey actions select and focus the actual ${role} tab without changing route`, () => {
  const ui = app();
  const controls = ui.queryAll(`[data-demo-view="${role}"]`);
  assert.ok(controls.length, `missing actionable journey to ${role}`);
  for (const control of controls) {
    const route = {...ui.location};
    const previous = ui.get(`tab-${role}`).clicks;
    control.click();
    assert.equal(ui.get(`tab-${role}`).clicks, previous + 1);
    assert.equal(ui.document.activeElement, ui.get(`tab-${role}`));
    assert.equal(ui.get(`panel-${role}`).hidden, false);
    assert.equal(ui.get(`tab-${role}`).getAttribute('aria-selected'), 'true');
    assert.deepEqual(ui.location, route);
  }
});

test('trace starts closed, and its existing button reveals a visible trace through closed diagnostics', () => {
  const ui = app();
  assert.ok(ui.get('demo-diagnostics'), 'native diagnostics disclosure exists');
  assert.equal(ui.get('demo-diagnostics').tagName, 'details');
  assert.equal(ui.get('demo-diagnostics').open, false);
  assert.equal(ui.get('actions-panel').hidden, true);
  assert.match(html, />Ver traza técnica<\/button>/);
  ui.get('toggle-actions').click();
  assert.equal(ui.get('actions-panel').hidden, false);
  assert.equal(ui.get('demo-diagnostics').open, true);
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'true');
  for (let node = ui.get('actions-panel'); node; node = node.parentElement) {
    assert.equal(node.hidden, false);
    if (node.tagName === 'details') assert.equal(node.open, true);
  }
  ui.get('toggle-actions').click();
  assert.equal(ui.get('actions-panel').hidden, true, 'one click, not a duplicated toggle');
  assert.equal(ui.get('toggle-actions').getAttribute('aria-expanded'), 'false');
});

test('native diagnostics summary remains reversible without sending or resetting anything', () => {
  const ui = app(); const details = ui.get('demo-diagnostics');
  assert.ok(details);
  const summary = details.children.find(node => node.tagName === 'summary');
  summary.click(); assert.equal(details.open, true);
  summary.click(); assert.equal(details.open, false);
  assert.equal(ui.get('send').clicks, 0); assert.equal(ui.get('reset').clicks, 0);
});

test('PMS expansion is reversible in-route and ARIA follows the actual expanded class', () => {
  const ui = app(); const button = ui.get('admin-expand');
  assert.ok(button, 'expand control exists');
  const workspace = ui.get(button.getAttribute('aria-controls'));
  assert.equal(workspace, ui.get('admin-console'));
  assert.equal(button.getAttribute('aria-expanded'), 'false');
  const route = {...ui.location};
  button.click();
  assert.equal(workspace.classList.contains('is-expanded'), true);
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.equal(button.textContent, 'Reducir PMS');
  button.click();
  assert.equal(workspace.classList.contains('is-expanded'), false);
  assert.equal(button.getAttribute('aria-expanded'), 'false');
  assert.equal(button.textContent, 'Ampliar PMS');
  assert.deepEqual(ui.location, route);
  assert.equal(ui.get('admin-frame').getAttribute('src'), null, 'journey does not load or navigate the PMS');
});

test('real-channel anchors reveal the guest view and disclosure, but never open or send the chat', () => {
  const ui = app();
  ui.get('tab-admin').click();
  const anchors = ui.queryAll('a[href="#canal"]');
  assert.ok(anchors.length);
  anchors[0].click();
  assert.equal(ui.get('panel-huesped').hidden, false);
  assert.equal(ui.get('demo-channel').open, true);
  assert.equal(ui.get('open-chat').clicks, 0);
  assert.equal(ui.get('send').clicks, 0);
});

test('direct and subsequent #canal links remain discoverable from other perspectives', () => {
  const ui = app('#canal');
  assert.ok(ui.get('demo-channel'));
  assert.equal(ui.get('demo-channel').open, true);
  assert.equal(ui.get('panel-huesped').hidden, false);
  ui.get('tab-recepcion').click(); ui.get('demo-channel').open = false;
  ui.hashchange('#canal');
  assert.equal(ui.get('demo-channel').open, true);
  assert.equal(ui.get('panel-huesped').hidden, false);
});

test('journey navigation leaves independently owned controls and content untouched', () => {
  const ui = app();
  const ids = ['demo-mode-switch', 'voice-start', 'voice-talk', 'voice-hangup', 'reset', 'send', 'open-chat', 'recepcion-back'];
  for (const id of ids) {
    const node = ui.get(id); const count = node.listeners.click?.length || 0;
    node.click(); assert.equal(node.listeners.click?.length || 0, count);
    assert.equal(count, 0, `journey must not attach behavior to ${id}`);
  }
  const route = {...ui.location};
  const clicks = ids.map(id => ui.get(id).clicks);
  for (const control of ui.queryAll('[data-demo-view]')) control.click();
  for (const [index, id] of ids.entries()) assert.equal(ui.get(id).clicks, clicks[index], `${id} must not be invoked by navigation`);
  assert.deepEqual(ui.location, route);
  assert.equal(ui.get('reception-tools').children.length, 0, 'queue owner fills the optional seam');
});

test('HTML retains primary capabilities and only adds a deferred journey module', () => {
  for (const id of ['chat-form', 'message-input', 'messages', 'scenario-status', 'voice-form', 'voice-log', 'timeline', 'actions-panel', 'recepcion-summary', 'recepcion-queue', 'recepcion-detail', 'recepcion-state', 'admin-frame', 'admin-metrics', 'canal']) {
    assert.equal([...html.matchAll(new RegExp(`id="${id}"`, 'g'))].length, 1, id);
  }
  for (const scenario of ['info', 'booking', 'human']) assert.match(html, new RegExp(`data-scenario="${scenario}"`));
  assert.match(html, /<script src="demo-journey\.js\?v=[^"]+" defer><\/script>/);
  assert.ok(html.indexOf('src="console.js') < html.indexOf('src="demo-journey.js'));
});
