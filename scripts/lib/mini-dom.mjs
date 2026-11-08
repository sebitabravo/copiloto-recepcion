// DOM mínimo para probar los scripts de /demo en Node, sin dependencias. Cubre lo que usan demo-*.js:
// árbol, texto, atributos, dataset, eventos y selectores simples (#id, .clase, etiqueta, [attr="valor"] y
// descendiente). No interpreta HTML: los scripts tampoco lo hacen.

export class Node {
  constructor(tag = 'div', document = null) {
    this.tagName = tag.toLowerCase();
    this.ownerDocument = document;
    this.children = [];
    this.parentElement = null;
    this.attributes = {};
    // Como en el navegador, dataset siempre guarda texto.
    this.dataset = new Proxy({}, {set: (target, key, value) => { target[key] = String(value); return true; }});
    this.listeners = {};
    this.style = {};
    this.text = '';
    this.hidden = false;
    this.disabled = false;
    this.value = '';
    this.checked = false;
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.clientHeight = 0;
    const node = this;
    this.classList = {
      add: (...names) => { for (const name of names) if (!node.classes().includes(name)) node.className = `${node.className} ${name}`.trim(); },
      remove: (...names) => { node.className = node.classes().filter(name => !names.includes(name)).join(' '); },
      contains: name => node.classes().includes(name),
      toggle: (name, on) => (on ? node.classList.add(name) : node.classList.remove(name))
    };
    this.className = '';
  }

  classes() { return String(this.className || '').split(/\s+/).filter(Boolean); }
  get id() { return this.attributes.id || ''; }
  set id(value) { this.attributes.id = String(value); }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.text = String(value); for (const child of this.children) child.parentElement = null; this.children = []; }
  get lastElementChild() { return this.children.at(-1) || null; }
  get parentNode() { return this.parentElement; }

  setAttribute(name, value) { this.attributes[name] = String(value); if (name === 'id') this.id = value; }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
  hasAttribute(name) { return name in this.attributes; }
  removeAttribute(name) { delete this.attributes[name]; if (name === 'href') delete this.href; }

  append(...nodes) {
    for (let node of nodes) {
      if (typeof node === 'string') node = this.ownerDocument.createTextNode(node);
      node.remove();
      node.parentElement = this;
      this.children.push(node);
    }
  }
  prepend(...nodes) { const rest = this.children; this.children = []; this.append(...nodes); this.children.push(...rest); }
  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter(child => child !== this);
    this.parentElement = null;
  }

  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  async emit(type, extra = {}) {
    const event = {type, target: this, preventDefault() {}, ...extra};
    for (const handler of this.listeners[type] || []) await handler(event);
  }
  click() { return this.emit('click'); }
  focus() { if (this.ownerDocument) this.ownerDocument.activeElement = this; }
  select() {}
  showModal() { this.setAttribute('open', ''); }
  close() { this.removeAttribute('open'); }
  requestSubmit() { return this.emit('submit'); }

  *walk() { for (const child of this.children) { yield child; yield* child.walk(); } }
  matches(selector) { return matchCompound(this, selector); }
  querySelectorAll(selector) {
    const parts = selector.trim().split(/\s+/);
    const results = [];
    for (const node of this.walk()) if (matchChain(node, parts, this)) results.push(node);
    return results;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function attr(node, name) {
  if (name.startsWith('data-')) {
    const key = name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
    return node.dataset[key] !== undefined ? String(node.dataset[key]) : null;
  }
  if (['name', 'value', 'type'].includes(name) && node[name] !== undefined && node[name] !== '') return String(node[name]);
  return node.getAttribute(name);
}

function matchCompound(node, compound) {
  if (node.tagName === '#text') return false;
  const pattern = /([#.]?)([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]/g;
  for (const match of compound.matchAll(pattern)) {
    const [, prefix, name, attrName, attrValue] = match;
    if (attrName) {
      const value = attr(node, attrName);
      if (value === null || (attrValue !== undefined && value !== attrValue)) return false;
    } else if (prefix === '#') {
      if (node.id !== name) return false;
    } else if (prefix === '.') {
      if (!node.classes().includes(name)) return false;
    } else if (node.tagName !== name.toLowerCase()) {
      return false;
    }
  }
  return true;
}

function matchChain(node, parts, root) {
  if (!matchCompound(node, parts.at(-1))) return false;
  let index = parts.length - 2;
  let current = node.parentElement;
  while (index >= 0 && current && current !== root.parentElement) {
    if (matchCompound(current, parts[index])) index -= 1;
    current = current.parentElement;
  }
  return index < 0;
}

export function createDocument() {
  const document = {
    hidden: false,
    activeElement: null,
    listeners: {},
    createElement: tag => new Node(tag, document),
    createTextNode: text => { const node = new Node('#text', document); node.text = String(text); return node; },
    addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); },
    getElementById(id) {
      for (const node of document.body.walk()) if (node.id === id) return node;
      return null;
    },
    querySelector: selector => document.body.querySelector(selector),
    querySelectorAll: selector => document.body.querySelectorAll(selector)
  };
  document.body = new Node('body', document);
  document.activeElement = document.body;
  return document;
}

// Agrega al body elementos con id (y sus hijos <span>/<button> donde los scripts los buscan).
export function addById(document, ids, tag = 'div') {
  for (const id of ids) {
    const node = document.createElement(tag);
    node.id = id;
    document.body.append(node);
  }
}

// fetch controlable: cada petición queda pendiente hasta que la prueba la resuelva.
export function controlledFetch() {
  const calls = [];
  const fetch = (url, options = {}) => new Promise((resolve, reject) => {
    calls.push({url: String(url), options, body: options.body ? JSON.parse(options.body) : undefined,
      respond(data, status = 200, headers = {}) {
        resolve(new Response(status === 204 ? null : JSON.stringify(data), {status, headers}));
      },
      fail() { reject(new TypeError('network')); }});
  });
  const pending = predicate => calls.find(call => !call.done && predicate(call));
  return {fetch, calls, pending};
}

// Deja correr las promesas pendientes (varias vueltas de la cola de microtareas).
export const flush = async (rounds = 20) => { for (let i = 0; i < rounds; i += 1) await Promise.resolve(); };
