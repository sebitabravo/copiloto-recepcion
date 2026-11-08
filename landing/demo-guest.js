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
  // `epoch` cambia con cada huésped nuevo: una lectura que empezó con otro epoch se descarta al llegar.
  let epoch = 0;
  let reading = false;
  let failures = 0;
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
    const sentEpoch = epoch;
    setBusy(true);
    try {
      const body = {session_id: sessionId, message: text, client_message_id: clientId};
      if (shift()) body.shift = shift();
      const data = await S.api('/api/demo/chat', {method: 'POST', body});
      node.remove();
      if (sentEpoch === epoch) apply(data);
    } catch (error) {
      if (sentEpoch === epoch) markFailed(node, text, clientId, error);
    } finally {
      // Sin reenfocar el campo: en un teléfono abriría el teclado tras tocar un atajo.
      setBusy(false);
    }
  }

  // Una sola lectura a la vez; su resultado solo se aplica si sigue siendo el mismo huésped.
  async function refresh() {
    if (!sessionId || reading) return;
    reading = true;
    const readEpoch = epoch;
    try {
      const path = `/api/demo/conversation?session_id=${encodeURIComponent(sessionId)}&after=${lastId}`;
      const data = await S.api(path);
      if (readEpoch !== epoch) return;
      failures = 0;
      clearError();
      apply(data);
    } catch (error) {
      if (readEpoch !== epoch) return;
      failures += 1;
      // 429 o red caída: se reintenta solo, con espera acotada (Retry-After si el servidor la pide).
      if (error.status !== 429) showError(`${error.message} Reintentamos solos en unos segundos.`, refresh);
      if (handledBy === 'recepcion') schedulePoll(S.backoff(failures, error.retryAfter, POLL_MS));
    } finally {
      if (readEpoch === epoch) reading = false;
    }
  }

  // Un solo ciclo: cada programación reemplaza a la anterior y el temporizador no corre si cambió el huésped.
  function schedulePoll(delay = POLL_MS) {
    clearTimeout(pollTimer);
    if (handledBy !== 'recepcion') return;
    const pollEpoch = epoch;
    pollTimer = setTimeout(async () => {
      if (pollEpoch !== epoch) return;
      if (document.hidden || busy || reading) schedulePoll(delay);
      else await refresh();
    }, delay);
  }

  // Otro huésped: sesión nueva. El caso anterior sigue en la bandeja (recepción no pierde lo que atiende);
  // la demo lo purga sola al vencer su sesión. Para borrar todo: `make demo-local LIMPIO=1`.
  function newGuest() {
    if (busy) return;
    // Todo lo que esté en vuelo pertenece al huésped anterior: se invalida antes de limpiar la vista.
    epoch += 1;
    reading = false;
    failures = 0;
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
