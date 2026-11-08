/* Chat del huésped («WhatsApp simulado»). Cada mensaje viaja con una llave de idempotencia: si la red
   falla, «Reintentar» reenvía la MISMA llave y el servidor no lo procesa dos veces. Mientras recepción
   tiene la solicitud, el chat consulta el hilo cada pocos segundos para mostrar su respuesta. */
(() => {
  'use strict';
  const S = window.DemoShared;
  const $ = id => document.getElementById(id);
  const SESSION_KEY = 'copiloto-demo-huesped';
  const POLL_MS = 4000;

  let sessionId = null;
  let lastId = 0;
  let previousRole = null;
  let handledBy = 'asistente';
  let busy = false;
  let pollTimer = 0;
  let shift = () => '';
  let pendingRetry = null;
  const rendered = new Set();

  const thread = () => $('guest-thread');
  const input = () => $('guest-input');

  function readSession() {
    const stored = S.store.get('sessionStorage', SESSION_KEY);
    if (stored && /^[A-Za-z0-9-]{16,64}$/.test(stored)) return stored;
    const value = S.newId();
    S.store.set('sessionStorage', SESSION_KEY, value);
    return value;
  }

  function scrollDown() { thread().scrollTop = thread().scrollHeight; }

  function clearQuick() { thread().querySelectorAll('.chips').forEach(node => node.remove()); }

  function render(messages) {
    for (const message of messages || []) {
      if (rendered.has(message.id)) continue;
      rendered.add(message.id);
      S.messageNodes(message, 'guest', previousRole).forEach(node => thread().append(node));
      previousRole = message.role;
      lastId = Math.max(lastId, message.id);
    }
  }

  function quickReplies(options) {
    clearQuick();
    if (!options || !options.length || handledBy !== 'asistente') return;
    const box = S.el('div', 'chips');
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', 'Respuestas sugeridas');
    options.slice(0, 4).forEach(text => {
      const button = S.el('button', '', text);
      button.type = 'button';
      button.addEventListener('click', () => send(text));
      box.append(button);
    });
    thread().append(box);
  }

  function showRequest(request) {
    const strip = $('guest-request');
    if (!request) { strip.hidden = true; strip.textContent = ''; return; }
    strip.hidden = false;
    strip.textContent = '';
    strip.append(S.el('b', '', `Solicitud ${request.code}`), document.createTextNode(` · ${request.label}`));
    strip.dataset.tone = request.status === 'respondida' ? 'green' : request.status === 'pendiente' ? 'amber' : '';
  }

  function apply(snapshot) {
    handledBy = snapshot.handled_by || 'asistente';
    render(snapshot.messages);
    showRequest(snapshot.request);
    // Con recepción a cargo, los atajos del asistente se ocultan: lo que escribas le llega a una persona.
    $('guest-actions').hidden = handledBy !== 'asistente';
    input().placeholder = handledBy === 'recepcion' ? 'Escribe a recepción' : 'Escribe un mensaje';
    quickReplies(snapshot.quick_replies);
    scrollDown();
    schedulePoll();
  }

  function setBusy(on) {
    busy = on;
    $('guest-typing').hidden = !on || handledBy !== 'asistente';
    $('guest-send').disabled = on || !input().value.trim();
    document.querySelectorAll('#guest-actions button, #guest-thread .chips button')
      .forEach(button => { button.disabled = on; });
    if (on) scrollDown();
  }

  function showError(text, retry) {
    const box = $('guest-error');
    box.hidden = false;
    box.querySelector('span').textContent = text;
    pendingRetry = retry;
  }

  function clearError() { $('guest-error').hidden = true; pendingRetry = null; }

  function pendingBubble(text) {
    const bubble = S.el('article', 'chat-bubble out guest pending');
    bubble.append(S.el('p', '', text));
    const meta = S.el('span', 'meta');
    meta.append(S.el('span', 'state', 'enviando…'));
    bubble.append(meta);
    thread().append(bubble);
    scrollDown();
    return bubble;
  }

  function markFailed(bubble, text, clientId, error) {
    // Una sola acción de reintento (en el aviso): reenvía con la MISMA llave, así no se duplica.
    bubble.classList.remove('pending');
    bubble.classList.add('failed');
    bubble.querySelector('.state').textContent = 'no enviado';
    showError(error.message, () => {
      bubble.classList.remove('failed');
      bubble.classList.add('pending');
      bubble.querySelector('.state').textContent = 'enviando…';
      send(text, clientId, bubble);
    });
  }

  async function send(raw, clientId = S.newId(), bubble = null) {
    const text = String(raw || '').trim();
    if (!text || busy) return;
    clearError();
    clearQuick();
    const node = bubble || pendingBubble(text);
    setBusy(true);
    try {
      const body = {session_id: sessionId, message: text, client_message_id: clientId};
      if (shift()) body.shift = shift();
      const data = await S.api('/api/demo/chat', {method: 'POST', body});
      node.remove();
      apply(data);
    } catch (error) {
      markFailed(node, text, clientId, error);
    } finally {
      // Sin reenfocar el campo: en un teléfono abriría el teclado tras tocar un atajo.
      setBusy(false);
    }
  }

  async function refresh() {
    if (!sessionId) return;
    try {
      const path = `/api/demo/conversation?session_id=${encodeURIComponent(sessionId)}&after=${lastId}`;
      apply(await S.api(path));
    } catch (error) {
      if (error.status !== 429) showError(error.message, refresh);
    }
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (handledBy !== 'recepcion') return;
    pollTimer = setTimeout(async () => {
      if (!document.hidden && !busy) await refresh();
      else schedulePoll();
    }, POLL_MS);
  }

  // Otro huésped: sesión nueva. El caso anterior sigue en la bandeja (recepción no pierde lo que atiende);
  // la demo lo purga sola al vencer su sesión. Para borrar todo: `make demo-local LIMPIO=1`.
  function newGuest() {
    if (busy) return;
    sessionId = S.newId();
    S.store.set('sessionStorage', SESSION_KEY, sessionId);
    clearTimeout(pollTimer);
    thread().querySelectorAll('.chat-bubble, .chips').forEach(node => node.remove());
    rendered.clear();
    lastId = 0;
    previousRole = null;
    handledBy = 'asistente';
    showRequest(null);
    $('guest-actions').hidden = false;
    clearError();
    input().focus();
  }

  function init(options = {}) {
    shift = options.shift || shift;
    if (options.status) {
      $('guest-hotel').textContent = options.status.hotel.name;
      $('guest-channel').textContent = options.status.hotel.channel_label;
      // Sin aviso publicado (versión estática) el enlace queda como texto: nunca un enlace roto.
      if (options.status.privacy_url) $('privacy-link').href = S.base + options.status.privacy_url;
      else $('privacy-link').removeAttribute('href');
    }
    sessionId = readSession();
    $('guest-form').addEventListener('submit', event => {
      event.preventDefault();
      const text = input().value;
      input().value = '';
      $('guest-send').disabled = true;
      send(text);
    });
    input().addEventListener('input', () => { $('guest-send').disabled = busy || !input().value.trim(); });
    document.querySelectorAll('#guest-actions [data-say]')
      .forEach(button => button.addEventListener('click', () => send(button.dataset.say)));
    $('guest-error').querySelector('button').addEventListener('click', () => pendingRetry && pendingRetry());
    $('guest-reset').addEventListener('click', newGuest);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) schedulePoll(); });
    return refresh();
  }

  window.DemoGuest = {init, send, refresh, get sessionId() { return sessionId; }};
})();
