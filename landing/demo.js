(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const config = window.COPILOTO_CONFIG || {};
  const baseUrl = (config.copilotoUrl || 'http://localhost:8100').replace(/\/+$/, '');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const initialText = 'Hola, soy el asistente de recepción de Hotel Bordeluz (demo con IA). Pregúntame por la ubicación, los servicios o reserva una habitación.';
  const initialReplies = ['¿Cómo llego?', '¿Tienen piscina?', 'Quiero reservar para 2 adultos'];
  const input = get('message-input');
  const messageList = get('messages');
  const sessionKey = 'bordeluz-demo-session';
  const money = new Intl.NumberFormat('es-CL', {style:'currency', currency:'CLP', maximumFractionDigits:0});
  let sessionId = readSession();
  let busy = false;
  let scenarioRunning = false;
  let scenarioVersion = 0;
  let cooldownUntil = 0;
  let retryOperation = null;
  let lastAssistant = null;
  let pinned = true;
  let turns = 0;

  function create(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }
  function newSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
    else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
    return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  }
  function persistSession(value) {
    try { window.sessionStorage.setItem(sessionKey, value); } catch (_) { /* La sesión continúa en memoria. */ }
  }
  function readSession() {
    let stored;
    try { stored = window.sessionStorage.getItem(sessionKey); } catch (_) { /* Almacenamiento no disponible. */ }
    if (stored && /^[A-Za-z0-9-]{16,64}$/.test(stored)) return stored;
    const value = newSessionId();
    persistSession(value);
    return value;
  }
  function coolingDown() { return Date.now() < cooldownUntil; }
  function updateControls() {
    const blocked = busy || scenarioRunning || coolingDown();
    input.disabled = blocked;
    get('send').disabled = blocked || !input.value.trim() || input.value.length > 400;
    get('reset').disabled = busy || scenarioRunning;
    document.querySelectorAll('[data-scenario]').forEach(button => { button.disabled = blocked; });
    messageList.querySelectorAll('.quick-replies button').forEach(button => { button.disabled = blocked; });
    get('char-count').textContent = `${input.value.length}/400`;
    get('typing').hidden = !busy;
    get('cancel-scenario').hidden = !scenarioRunning;
  }
  function scrollToLatest() {
    if (pinned) messageList.scrollTop = messageList.scrollHeight;
  }
  messageList.addEventListener('scroll', () => {
    pinned = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < 65;
  });
  function clearSuggestions() {
    messageList.querySelectorAll('.quick-replies').forEach(element => element.remove());
  }
  function suggestions(message, replies) {
    clearSuggestions();
    if (!Array.isArray(replies)) return;
    const container = create('div', 'quick-replies');
    replies.slice(0, 4).forEach(text => {
      if (typeof text !== 'string' || !text.trim()) return;
      const button = create('button', '', text);
      button.type = 'button';
      button.addEventListener('click', () => sendMessage(text));
      container.append(button);
    });
    message.append(container);
    updateControls();
    scrollToLatest();
  }
  function addMessage(role, text, replies = []) {
    const message = create('article', `message ${role}`);
    message.append(create('span', 'message-label', role === 'user' ? 'TÚ · DEMOSTRACIÓN' : 'COPILOTO'));
    const bubble = create('div', 'bubble');
    bubble.append(create('p', '', text));
    message.append(bubble);
    messageList.append(message);
    if (role === 'assistant') {
      lastAssistant = message;
      suggestions(message, replies);
      // Una región separada anuncia solo la respuesta nueva, nunca el historial completo.
      get('assistant-announcement').textContent = text;
    }
    scrollToLatest();
    return message;
  }
  function showChatError(text, retry) {
    get('chat-error').hidden = false;
    get('chat-error').querySelector('span').textContent = text;
    retryOperation = retry;
    get('chat-error').querySelector('button').hidden = !retry;
  }
  function clearChatError() { get('chat-error').hidden = true; retryOperation = null; }
  function startCooldown(seconds) {
    const duration = Math.max(1, Math.ceil(Number(seconds) || 30));
    cooldownUntil = Date.now() + duration * 1000;
    updateCooldown();
  }
  function updateCooldown() {
    const seconds = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
    get('rate-status').hidden = seconds === 0;
    get('rate-status').textContent = seconds ? `Pausa de la demo: podrás enviar otro mensaje en ${seconds} s.` : '';
    updateControls();
  }
  window.setInterval(updateCooldown, 500);

  async function request(path, body) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 40000);
    try {
      const options = {method:body === undefined ? 'GET' : 'POST', credentials:'omit',
        cache:'no-store', signal:controller.signal};
      if (body !== undefined) {
        options.headers = {'Content-Type':'application/json'};
        options.body = JSON.stringify(body);
      }
      const response = await fetch(baseUrl + path, options);
      let data;
      try { data = await response.json(); } catch (_) { data = {}; }
      if (!response.ok) {
        if (response.status === 429) {
          startCooldown(data.retry_after_s || response.headers.get('Retry-After'));
          throw {status:429, message:'Se alcanzó un límite temporal de la demo. Espera el contador y reintenta.'};
        }
        if (response.status === 400 || response.status === 422) {
          throw {status:response.status, message:'Revisa el mensaje: debe tener entre 1 y 400 caracteres. Si persiste, reinicia la conversación.'};
        }
        throw {status:response.status, message:'El asistente no está disponible en este momento. Reintenta en unos segundos.'};
      }
      return data;
    } catch (error) {
      if (error && error.message && Number.isInteger(error.status)) throw error;
      throw {status:0, message:'No pudimos conectar con el asistente. Revisa que el servidor esté encendido y permita este origen, y reintenta.'};
    } finally { window.clearTimeout(timeout); }
  }
  async function loadStatus() {
    get('status-error').hidden = true;
    try {
      const data = await request('/api/demo/status');
      get('model-label').textContent = data.ai_enabled ? `Modelo: ${data.model || 'DeepSeek'}` : 'Flujo guiado · sin IA';
      get('guided-banner').hidden = data.ai_enabled !== false;
      get('capability').textContent = data.autonomous_booking ?
        'En este servidor la IA puede crear la reserva de demostración por sí sola.' :
        'En este servidor el asistente prepara la solicitud; la demostración no crea reservas autónomamente.';
      get('connection-label').textContent = data.ai_enabled ? 'Demo con IA · lista para conversar' : 'Flujo guiado disponible';
      get('status-dot').classList.add('ready');
      if (!turns) get('messages-left').textContent = `Mensajes restantes: ${data.messages_per_session ?? '—'}`;
    } catch (error) {
      get('status-error').hidden = false;
      get('status-error').querySelector('span').textContent = error.message;
      get('model-label').textContent = 'Conexión pendiente';
      get('connection-label').textContent = 'No se pudo comprobar la conexión';
      get('status-dot').classList.remove('ready');
      get('capability').textContent = 'Las capacidades del servidor se mostrarán cuando esté disponible.';
    }
  }
  const iconPaths = {
    check_availability:'M4 5h16v16H4zM4 10h16M8 2v6M16 2v6m-8 6h3m2 0h3',
    get_hotel_info:'M4 21V9l8-6 8 6v12M9 21v-7h6v7M3 21h18',
    create_booking:'M5 3h14v18H5zM8 8h8m-8 5 3 3 5-6',
    handoff_to_human:'M4 20v-2a6 6 0 0 1 12 0v2M10 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8m8 0 3 3-3 3m-2-3h5'
  };
  function toolIcon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.6');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', iconPaths[name] || iconPaths.get_hotel_info);
    svg.append(path);
    return svg;
  }
  function eventCard(event) {
    const card = create('article', 'event-card');
    if (event.type === 'tool_call') {
      const heading = create('div', 'event-heading');
      const icon = create('span', 'event-icon');
      icon.append(toolIcon(event.name));
      const result = create('span', `event-result${event.ok ? '' : ' failed'}`, event.ok ? '✓' : '✕');
      result.setAttribute('aria-label', event.ok ? 'Herramienta completada' : 'Herramienta con error');
      heading.append(icon, create('h3', '', event.label || 'Consulta de herramienta'), result);
      card.append(heading);
      const argumentsList = create('div', 'arguments');
      if (event.arguments && typeof event.arguments === 'object') {
        Object.entries(event.arguments).forEach(([key, value]) => {
          const formatted = typeof value === 'object' ? JSON.stringify(value) : String(value);
          argumentsList.append(create('span', '', `${key}: ${formatted}`));
        });
      }
      card.append(argumentsList, create('p', '', event.summary || ''), create('p', '', `${event.ms ?? '—'} ms`));
    } else if (event.type === 'booking_created') {
      card.classList.add('booking-ticket');
      card.append(create('h3', '', `Reserva #${event.booking_id} creada en el PMS simulado`),
        create('p', '', event.room_name || 'Habitación de demostración'),
        create('p', '', `${event.checkin} → ${event.checkout} · ${event.nights} noches`),
        create('p', '', `${event.adults} adultos · ${event.children} niños`),
        create('p', 'ticket-total', `${money.format(Number(event.total_clp) || 0)} CLP`),
        create('span', 'stamp', 'demostración'));
    } else if (event.type === 'handoff') {
      card.append(create('h3', '', 'Se avisa a una persona de recepción (simulado)'), create('p', '', event.reason || ''));
    } else if (event.type === 'fallback') {
      card.append(create('h3', '', 'La IA no respondió: se usó el flujo guiado'));
    } else return null;
    return card;
  }
  const pause = milliseconds => new Promise(resolve => window.setTimeout(resolve, milliseconds));
  async function showEvents(events) {
    if (!Array.isArray(events) || !events.length) return;
    get('timeline-empty').hidden = true;
    get('timeline').append(create('p', 'turn-label', `Turno ${turns} · acciones del asistente`));
    for (const event of events) {
      if (!event || typeof event !== 'object') continue;
      const card = eventCard(event);
      if (!card) continue;
      get('timeline').append(card);
      get('timeline').scrollTop = get('timeline').scrollHeight;
      if (!reducedMotion.matches) await pause(220);
    }
  }
  async function sendMessage(text, retry = false, guided = false) {
    if (busy || coolingDown() || (scenarioRunning && !guided)) return false;
    const message = String(text).trim();
    if (!message || message.length > 400) return false;
    busy = true;
    clearChatError();
    clearSuggestions();
    if (!retry) addMessage('user', message);
    input.value = '';
    updateControls();
    let success = false;
    try {
      const data = await request('/api/demo/chat', {session_id:sessionId, message});
      if (typeof data.reply !== 'string') throw {message:'La respuesta llegó incompleta. Reintenta en un momento.'};
      turns += 1;
      addMessage('assistant', data.reply, data.quick_replies);
      get('response-time').textContent = `Respuesta en ${typeof data.usage?.llm_ms === 'number' ?
        (data.usage.llm_ms / 1000).toLocaleString('es-CL', {maximumFractionDigits:2}) : '—'} s`;
      get('messages-left').textContent = `Mensajes restantes: ${data.usage?.messages_left ?? '—'}`;
      if (data.mode === 'guided') get('guided-banner').hidden = false;
      await showEvents(data.events);
      success = true;
    } catch (error) {
      showChatError(error.message || 'No se pudo enviar el mensaje. Reintenta.', () => sendMessage(message, true));
    } finally {
      busy = false;
      updateControls();
      scrollToLatest();
      if (!scenarioRunning && !coolingDown()) input.focus({preventScroll:true});
    }
    return success;
  }
  function clearConversation() {
    messageList.replaceChildren();
    get('timeline').replaceChildren();
    get('timeline-empty').hidden = false;
    get('response-time').textContent = 'Respuesta en — s';
    get('messages-left').textContent = 'Mensajes restantes: —';
    get('scenario-status').textContent = '';
    input.value = '';
    pinned = true;
    turns = 0;
    clearChatError();
    addMessage('assistant', initialText, initialReplies);
    updateControls();
  }
  async function resetConversation() {
    if (busy || scenarioRunning) return;
    busy = true;
    clearChatError();
    updateControls();
    try {
      await request('/api/demo/reset', {session_id:sessionId});
      sessionId = newSessionId();
      persistSession(sessionId);
      clearConversation();
      loadStatus();
    } catch (error) { showChatError(error.message, resetConversation); }
    finally { busy = false; updateControls(); }
  }
  function exampleDates() {
    const checkin = new Date();
    // Mediodía y días de calendario evitan desfases al cambiar el horario de verano.
    checkin.setHours(12, 0, 0, 0);
    checkin.setDate(checkin.getDate() + 120);
    const checkout = new Date(checkin);
    checkout.setDate(checkout.getDate() + 3);
    const format = value => `${String(value.getDate()).padStart(2, '0')}/${String(value.getMonth() + 1).padStart(2, '0')}/${value.getFullYear()}`;
    return `${format(checkin)} al ${format(checkout)}`;
  }
  async function typeScenario(text, version) {
    input.value = '';
    if (reducedMotion.matches) { input.value = text; updateControls(); return; }
    for (const character of text) {
      if (version !== scenarioVersion) return;
      input.value += character;
      updateControls();
      await pause(12);
    }
  }
  async function runScenario(name) {
    if (busy || scenarioRunning || coolingDown()) return;
    const scenarios = {
      info:['¿Cómo llego al hotel?', '¿Tienen piscina y qué otros servicios ofrecen?'],
      booking:['Quiero reservar una habitación', exampleDates(), '2 adultos y 1 niño', 'La Doble con Jacuzzi',
        'Me llamo Camila Rojas, confirma la reserva por favor'],
      human:['Quiero hablar con una persona de recepción']
    };
    const messages = scenarios[name];
    if (!messages) return;
    const version = ++scenarioVersion;
    scenarioRunning = true;
    clearChatError();
    updateControls();
    get('scenario-status').textContent = 'Demo guiada en curso… Puedes detenerla.';
    try {
      for (let index = 0; index < messages.length; index += 1) {
        if (version !== scenarioVersion) return;
        get('scenario-status').textContent = `Demo guiada: mensaje ${index + 1} de ${messages.length}.`;
        await typeScenario(messages[index], version);
        if (version !== scenarioVersion) return;
        const success = await sendMessage(messages[index], false, true);
        if (version !== scenarioVersion) return;
        if (!success) { get('scenario-status').textContent = 'Demo guiada pausada por un error. Puedes reintentar el mensaje.'; return; }
        await pause(800);
      }
      get('scenario-status').textContent = 'Demo guiada terminada. Ahora puedes continuar la conversación.';
    } finally {
      if (version === scenarioVersion) {
        scenarioRunning = false;
        updateControls();
      }
    }
  }
  get('cancel-scenario').addEventListener('click', () => {
    scenarioVersion += 1;
    scenarioRunning = false;
    input.value = '';
    get('scenario-status').textContent = busy ? 'Demo detenida. Esperando la respuesta del mensaje ya enviado.' : 'Demo guiada detenida. Puedes escribir tu propio mensaje.';
    updateControls();
  });
  get('chat-form').addEventListener('submit', event => { event.preventDefault(); sendMessage(input.value); });
  input.addEventListener('input', updateControls);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage(input.value);
    }
  });
  get('reset').addEventListener('click', resetConversation);
  get('status-error').querySelector('button').addEventListener('click', loadStatus);
  get('chat-error').querySelector('button').addEventListener('click', () => {
    if (!busy && !coolingDown() && !scenarioRunning && retryOperation) retryOperation();
  });
  document.querySelectorAll('[data-scenario]').forEach(button => {
    button.addEventListener('click', () => runScenario(button.dataset.scenario));
  });

  // El canal real de Chatwoot sigue disponible como alternativa secundaria.
  const chatStatus = get('chat-status');
  window.addEventListener('chatwoot:ready', () => { chatStatus.textContent = 'La bandeja real de recepción está lista.'; });
  get('open-chat').addEventListener('click', () => {
    const unavailable = 'El chat no está disponible: ¿levantaste el stack con make up?';
    if (window.$chatwoot && typeof window.$chatwoot.toggle === 'function') {
      try { window.$chatwoot.toggle('open'); chatStatus.textContent = 'Chat de recepción abierto.'; }
      catch (_) { chatStatus.textContent = unavailable; }
    } else chatStatus.textContent = unavailable;
  });
  (function () {
    var cfg = window.COPILOTO_CONFIG;
    if (!cfg || !cfg.websiteToken) { return; }
    window.chatwootSettings = { locale: "es", position: "right", type: "expanded_bubble",
                                launcherTitle: "Habla con recepción" };
    var script = document.createElement("script");
    script.src = cfg.chatwootUrl + "/packs/js/sdk.js";
    script.async = true;
    script.onload = function () {
      window.chatwootSDK.run({ websiteToken: cfg.websiteToken, baseUrl: cfg.chatwootUrl });
    };
    document.body.appendChild(script);
  })();
  if ('IntersectionObserver' in window && !reducedMotion.matches) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) { entry.target.classList.remove('waiting'); observer.unobserve(entry.target); }
      });
    }, {threshold:0.08});
    document.querySelectorAll('main > section:not(#demo)').forEach(section => {
      section.classList.add('reveal', 'waiting');
      observer.observe(section);
    });
  }
  clearConversation();
  loadStatus();
})();
