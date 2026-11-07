(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const config = window.COPILOTO_CONFIG || {};
  const copilotoUrl = (config.copilotoUrl || 'http://localhost:8100').replace(/\/+$/, '');
  // Demo por LAN: si la página no corre en localhost pero la config sí apunta ahí,
  // se reescribe el host al de la página conservando puerto y ruta.
  function resolveUrl(raw) {
    const text = String(raw);
    try {
      const url = new URL(text);
      const local = host => host === 'localhost' || host === '127.0.0.1';
      if (!local(location.hostname) && local(url.hostname)) {
        url.hostname = location.hostname;
        // Una página servida por https no puede llamar por http (contenido mixto activo): se
        // refleja el protocolo de la página conservando el puerto.
        url.protocol = location.protocol;
      }
      return url.toString();
    } catch (_) { return text; }
  }
  // voice.js carga después y reutiliza este resolutor: misma reescritura de host en la demo por LAN.
  window.resolveDemoUrl = resolveUrl;
  const baseUrl = resolveUrl(copilotoUrl).replace(/\/+$/, '');
  // El aviso de privacidad es configurable (window.COPILOTO_CONFIG.privacyUrl);
  // por defecto vive junto al servicio copiloto.
  const privacyLink = get('privacy-link');
  if (privacyLink) privacyLink.href = resolveUrl(config.privacyUrl || `${copilotoUrl}/privacidad`);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  // Saludos en dos ideas (C1): una línea en blanco separa las burbujas, como escribe una persona.
  const greetingOpen = 'Hola, bienvenido a Hotel Bordeluz.';
  const aiInitialText = `${greetingOpen}\n\nSoy el asistente de recepción, una IA: te ayudo con ubicación, servicios y reservas de prueba. Antes de reservar te muestro una propuesta y solo la creo si la confirmas.`;
  const aiInitialReplies = ['¿Cómo llego?', '¿Tienen piscina?', 'Quiero reservar para 2 adultos'];
  const assistedInitialText = `${greetingOpen}\n\nSoy el asistente de recepción, una IA: te ayudo con ubicación, servicios y disponibilidad. Las reservas las confirma una persona del equipo.`;
  const guidedInitialText = `${greetingOpen}\n\nSoy el asistente de recepción y hoy respondo con respuestas guiadas, sin IA: te ayudo con ubicación, servicios y políticas del hotel. Las reservas las confirma una persona del equipo.`;
  const guidedInitialReplies = ['¿Cómo llego?', '¿Tienen piscina?', '¿Cuál es el horario de check-in?'];
  const pendingInitialText = `${greetingOpen}\n\nSoy el asistente de recepción: te ayudo con la ubicación y los servicios del hotel.`;
  let aiEnabled = null;
  let autonomousBooking = false;
  let proposalButton = null;
  const input = get('message-input');
  const messageList = get('messages');
  // El aviso de privacidad vive dentro del historial: se guarda la referencia porque reiniciar lo desmonta.
  const disclaimerNote = get('ai-disclaimer');
  const sessionKey = 'bordeluz-demo-session';
  const money = new Intl.NumberFormat('es-CL', {style:'currency', currency:'CLP', maximumFractionDigits:0});
  const timeFormat = new Intl.DateTimeFormat('es-CL', {hour:'2-digit', minute:'2-digit', hourCycle:'h23'});
  const clockLabel = () => timeFormat.format(new Date());
  let sessionId = readSession();
  let busy = false;
  let tracing = false;
  let scenarioRunning = false;
  let scenarioVersion = 0;
  let cooldownUntil = 0;
  let retryOperation = null;
  let lastAssistant = null;
  let pinned = true;
  let turns = 0;
  // Mientras se revelan las burbujas de una respuesta, el indicador de escritura solo aparece entre ellas.
  let revealing = false;
  let betweenBubbles = false;
  const CONFIRMATION_TEXT = 'Sí, confirmo la reserva';

  function setConnectionLabel(text) {
    const label = get('connection-label');
    label.dataset.base = text;
    if (!busy) label.textContent = text;
  }

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
    const blocked = busy || tracing || scenarioRunning || coolingDown();
    // La traza animando no bloquea el composer: el huésped puede escribir su próximo turno;
    // solo se impide un turno simultáneo (envío, botones y sugerencias).
    input.disabled = busy;
    get('send').disabled = blocked || !input.value.trim() || input.value.length > 400;
    get('reset').disabled = busy || scenarioRunning;
    document.querySelectorAll('[data-scenario]').forEach(button => {
      button.disabled = blocked;
    });
    messageList.querySelectorAll('.quick-replies button').forEach(button => { button.disabled = blocked; });
    if (proposalButton) proposalButton.disabled = blocked;
    get('char-count').textContent = `${input.value.length}/400`;
    // El indicador de escritura vive dentro del historial y siempre cae al final de la conversación.
    const typing = get('typing');
    const showTyping = busy && (!revealing || betweenBubbles);
    typing.hidden = !showTyping;
    if (showTyping && messageList.lastElementChild !== typing) {
      messageList.append(typing);
      scrollToLatest();
    }
    get('cancel-scenario').hidden = !scenarioRunning;
    const connection = get('connection-label');
    connection.textContent = busy ? 'escribiendo…' : (connection.dataset.base || connection.textContent);
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
      // La confirmación solo aparece junto a una propuesta emitida por el servidor.
      if (/confirm/i.test(text)) return;
      const button = create('button', '', text);
      button.type = 'button';
      button.addEventListener('click', () => sendMessage(text));
      container.append(button);
    });
    message.append(container);
    updateControls();
    scrollToLatest();
  }
  // C1: una línea en blanco separa ideas; cada idea es una burbuja (máximo 3, el resto va en la última).
  function splitReply(text) {
    const parts = String(text).split(/\n[ \t]*\n/).map(part => part.trim()).filter(Boolean);
    if (parts.length <= 3) return parts.length ? parts : [String(text)];
    return [parts[0], parts[1], parts.slice(2).join('\n\n')];
  }
  // C2: negrita al estilo WhatsApp (*texto*; también el **texto** de Markdown que se le escape al modelo).
  // Solo se crean nodos de texto y <b>: nada del servidor se interpreta como HTML.
  const boldPattern = /\*\*(\S(?:[^*\n]*\S)?)\*\*|\*(\S(?:[^*\n]*\S)?)\*/g;
  function appendFormatted(parent, text) {
    const value = String(text);
    let last = 0;
    for (const match of value.matchAll(boldPattern)) {
      if (match.index > last) parent.append(document.createTextNode(value.slice(last, match.index)));
      parent.append(create('b', '', match[1] ?? match[2]));
      last = match.index + match[0].length;
    }
    if (last < value.length) parent.append(document.createTextNode(value.slice(last)));
  }
  const plainText = text => String(text).replace(boldPattern, (_, double, single) => double ?? single);
  // Pausa de escritura proporcional al largo de la siguiente burbuja, con tope de 1,2 s.
  const bubblePause = text => Math.min(1200, String(text).length * 12);
  function addBubble(role, text, continued = false) {
    if (role === 'assistant') get('typing').hidden = true;
    const message = create('article', `message ${role}${continued ? ' continued' : ''}`);
    const bubble = create('div', 'bubble');
    const paragraph = create('p');
    if (role === 'assistant') appendFormatted(paragraph, text);
    else paragraph.textContent = text;
    bubble.append(paragraph);
    const time = create('span', 'message-time', clockLabel());
    if (role === 'user') time.append(create('span', 'ticks', '✓✓'));
    bubble.append(time);
    message.append(bubble);
    messageList.append(message);
    if (role === 'assistant') lastAssistant = message;
    scrollToLatest();
    return message;
  }
  // Versión inmediata (saludo y mensajes del huésped): todas las burbujas de una vez.
  function addMessage(role, text, replies = []) {
    if (role !== 'assistant') return addBubble(role, text);
    const parts = splitReply(text);
    let message = null;
    parts.forEach((part, index) => { message = addBubble('assistant', part, index > 0); });
    suggestions(message, replies);
    // Una región separada anuncia solo la respuesta nueva, nunca el historial completo.
    get('assistant-announcement').textContent = plainText(parts.join(' '));
    return message;
  }
  // Respuesta del asistente: las burbujas llegan una tras otra con el indicador de escritura entre ellas.
  async function revealReply(text, replies) {
    const parts = splitReply(text);
    // El lector de pantalla recibe la respuesta completa de una vez, sin esperar las pausas visuales.
    get('assistant-announcement').textContent = plainText(parts.join(' '));
    revealing = true;
    let message = null;
    try {
      for (let index = 0; index < parts.length; index += 1) {
        if (index > 0 && !reducedMotion.matches) {
          betweenBubbles = true;
          updateControls();
          await pause(bubblePause(parts[index]));
          betweenBubbles = false;
        }
        message = addBubble('assistant', parts[index], index > 0);
        updateControls();
      }
    } finally {
      revealing = false;
      betweenBubbles = false;
    }
    // Las respuestas rápidas cuelgan de la última burbuja.
    suggestions(message, replies);
    return message;
  }
  function showChatError(text, retry) {
    get('chat-error').hidden = false;
    get('chat-error').querySelector('span').textContent = text;
    retryOperation = retry;
    get('chat-error').querySelector('button').hidden = !retry;
  }
  function clearChatError() { get('chat-error').hidden = true; retryOperation = null; }
  let cooldownTimer = 0;
  function startCooldown(seconds) {
    const duration = Math.max(1, Math.ceil(Number(seconds) || 30));
    cooldownUntil = Date.now() + duration * 1000;
    if (!cooldownTimer) cooldownTimer = window.setInterval(updateCooldown, 500);
    updateCooldown();
  }
  function updateCooldown() {
    const seconds = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
    get('rate-status').hidden = seconds === 0;
    get('rate-status').textContent = seconds ? `Pausa de la demo: podrás enviar otro mensaje en ${seconds} s.` : '';
    // El temporizador solo corre mientras hay pausa activa; de otra forma tick-ea para siempre.
    if (!seconds && cooldownTimer) { window.clearInterval(cooldownTimer); cooldownTimer = 0; }
    updateControls();
  }

  async function request(path, body, extra = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 90000);
    try {
      const options = {method:body === undefined ? 'GET' : 'POST', credentials:extra.credentials || 'omit',
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
      if (controller.signal.aborted) throw {status:0, message:'El asistente tardó demasiado en responder. Reintenta en unos momentos.'};
      throw {status:0, message:'No pudimos conectar con el asistente. Revisa que el servidor esté encendido y permita este origen, y reintenta.'};
    } finally { window.clearTimeout(timeout); }
  }
  function initialGreeting() {
    if (autonomousBooking) return {text:aiInitialText, replies:aiInitialReplies};
    if (aiEnabled === true) return {text:assistedInitialText, replies:guidedInitialReplies};
    if (aiEnabled === false) return {text:guidedInitialText, replies:guidedInitialReplies};
    return {text:pendingInitialText, replies:guidedInitialReplies};
  }
  function updateInitialGreeting() {
    // La carga de estado no debe reemplazar mensajes ni sugerencias de una conversación iniciada.
    if (messageList.querySelector('.user')) return;
    const previous = messageList.querySelectorAll('.assistant');
    if (!previous.length) return;
    // El saludo puede cambiar de cantidad de burbujas: se reemplaza entero, no solo su texto.
    previous.forEach(element => element.remove());
    const greeting = initialGreeting();
    addMessage('assistant', greeting.text, greeting.replies);
  }
  async function loadStatus() {
    get('status-error').hidden = true;
    try {
      const data = await request('/api/demo/status');
      aiEnabled = data.ai_enabled === true;
      autonomousBooking = aiEnabled && data.autonomous_booking === true;
      get('model-label').textContent = aiEnabled ? `Modelo: ${data.model || 'DeepSeek'}` : 'Flujo guiado · sin IA';
      disclaimerNote.hidden = !aiEnabled;
      get('guided-banner').hidden = aiEnabled;
      // «Registra una reserva» solo se promete donde el servidor puede reservar (modo full).
      const bookingTrace = get('trace-booking');
      if (bookingTrace) bookingTrace.hidden = data.mode !== 'full';
      get('capability').hidden = !aiEnabled;
      get('capability').textContent = !aiEnabled ? '' : autonomousBooking ?
        'Puede crear reservas en el PMS simulado solo después de mostrar una propuesta y recibir tu confirmación explícita.' :
        'Sin permiso para crear reservas. Puedes consultar información; para contactar a recepción usa el widget de Chatwoot.';
      const bookingScenario = document.querySelector('[data-scenario="booking"]');
      const bookingLabel = bookingScenario.querySelector('.scenario-label') || bookingScenario;
      bookingScenario.hidden = false;
      // El guion consulta disponibilidad y se detiene antes de reservar: está disponible en todos los modos.
      bookingLabel.textContent = 'Disponibilidad sin reservar';
      setConnectionLabel(aiEnabled ? 'asistente con IA' : 'flujo guiado');
      get('status-dot').classList.add('ready');
      if (!turns) get('messages-left').textContent = `Mensajes restantes: ${data.messages_per_session ?? '—'}`;
      updateInitialGreeting();
      updateControls();
    } catch (error) {
      autonomousBooking = false;
      // Sin estado del servidor, la escritura queda habilitada solo con el descargo de IA visible:
      // la privacidad antes de preguntar no puede desaparecer justo cuando el backend cae.
      disclaimerNote.hidden = false;
      const bookingTrace = get('trace-booking');
      if (bookingTrace) bookingTrace.hidden = true;
      get('status-error').hidden = false;
      get('status-error').querySelector('span').textContent = error.message;
      get('model-label').textContent = 'Conexión pendiente';
      setConnectionLabel('sin conexión');
      get('status-dot').classList.remove('ready');
      // Conservamos el modo informativo, pero deshabilitamos la escritura sin estado reciente.
      updateControls();
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
  const toolSources = {
    check_availability: 'PMS simulado',
    get_hotel_info: 'catálogo del hotel',
    create_booking: 'PMS simulado',
    handoff_to_human: 'simulación del navegador · sin notificación a Chatwoot'
  };
  const toolTitles = {
    get_hotel_info: 'Consultó la información del hotel',
    check_availability: 'Verificó disponibilidad',
    create_booking: 'Procesó una solicitud de reserva',
    handoff_to_human: 'Simuló una solicitud de atención humana'
  };
  const dayMonth = new Intl.DateTimeFormat('es-CL', {day:'numeric', month:'short', timeZone:'UTC'});
  function shortDate(value) {
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(parsed.getTime()) ? String(value) : dayMonth.format(parsed);
  }
  function availabilityCard(result, args) {
    const card = create('div', 'availability');
    const dates = args && args.checkin && args.checkout ? `${shortDate(args.checkin)} → ${shortDate(args.checkout)} · ` : '';
    card.append(create('p', 'availability-head', `${dates}${result.noches ?? '—'} noches · lectura ${result.lectura || 'sin hora'}`));
    if (!Array.isArray(result.opciones) || !result.opciones.length) {
      card.append(create('p', 'availability-empty', 'Sin cupo para esas fechas y personas.'));
      return card;
    }
    const list = create('ul', 'availability-list');
    result.opciones.forEach(option => {
      const row = create('li');
      row.append(
        create('strong', '', option.nombre),
        create('span', '', option.cupos === 1 ? 'queda 1' : `quedan ${option.cupos}`),
        create('span', 'availability-price', `${money.format(Number(option.precio_noche_clp) || 0)} por noche`),
        create('span', 'availability-total', `${money.format(Number(option.total_clp) || 0)} en total`));
      list.append(row);
    });
    card.append(list, create('p', 'availability-note', 'Precios y cupos simulados: recepción los confirma.'));
    return card;
  }
  function technicalDetail(event) {
    const detail = create('details', 'tech');
    detail.append(create('summary', '', 'Detalle técnico'), create('code', '', event.name || 'tool_call'));
    const argumentsList = create('div', 'arguments');
    // Lista permitida de valores escalares: no exponemos credenciales ni objetos anidados.
    const safeArguments = ['topic', 'checkin', 'checkout', 'adults', 'children', 'room_code', 'guest_name', 'reason'];
    safeArguments.forEach(key => {
      const value = event.arguments?.[key];
      if (typeof value === 'string' || typeof value === 'number') argumentsList.append(create('span', '', `${key}: ${value}`));
    });
    detail.append(argumentsList, create('p', '', `${event.ms ?? '—'} ms`));
    // De dónde salió el dato: la traza nunca muestra un valor sin origen.
    detail.append(create('span', 'event-source', `fuente: ${toolSources[event.name] || 'servidor de la demo'}`));
    return detail;
  }
  function eventCard(event) {
    const card = create('article', 'event-card');
    if (event.type === 'tool_call') {
      const heading = create('div', 'event-heading');
      const icon = create('span', 'event-icon');
      icon.append(toolIcon(event.name));
      const result = create('span', `event-result${event.ok ? '' : ' failed'}`, event.ok ? '✓' : '✕');
      result.setAttribute('aria-label', event.ok ? 'Acción completada' : 'Acción con error');
      heading.append(icon, create('h3', '', toolTitles[event.name] || event.label || 'Acción del asistente'), result);
      card.append(heading);
      if (event.summary && event.name !== 'handoff_to_human') card.append(create('p', 'event-summary', event.summary));
      if (event.name === 'handoff_to_human') card.append(create('p', '', 'No se notificó a recepción. Para contactar al equipo, abre el widget separado de Chatwoot.'));
      if (event.result && event.name === 'check_availability') card.append(availabilityCard(event.result, event.arguments));
      card.append(technicalDetail(event));
    } else if (event.type === 'booking_created') {
      card.classList.add('booking-ticket');
      card.append(create('h3', '', `Reserva #${event.booking_id} creada en el PMS simulado`),
        create('p', '', event.room_name || 'Habitación de demostración'),
        create('p', '', `${event.checkin} → ${event.checkout} · ${event.nights} noches`),
        create('p', '', `${event.adults} adultos · ${event.children} niños`),
        create('p', 'ticket-total', `${money.format(Number(event.total_clp) || 0)} CLP`),
        create('span', 'stamp', 'demostración'));
    } else if (event.type === 'handoff') {
      card.append(create('h3', '', 'Derivación simulada: no se notificó a recepción'),
        create('p', '', event.reason || ''), create('p', '', 'Para contactar al equipo, usa el botón «Escribir a recepción» de Chatwoot.'));
    } else if (event.type === 'fallback') {
      card.append(create('h3', '', 'La IA no respondió: se usó el flujo guiado'));
    } else return null;
    return card;
  }
  const pause = milliseconds => new Promise(resolve => window.setTimeout(resolve, milliseconds));
  function invalidateProposal() {
    if (proposalButton) {
      proposalButton.disabled = true;
      // La propuesta anterior ya no es válida: se marca vencida en lugar de dejar un botón muerto.
      if (typeof proposalButton.replaceWith === 'function' && proposalButton.isConnected) {
        proposalButton.replaceWith(create('p', 'proposal-expired', 'Propuesta vencida: solicita una nueva para confirmar.'));
      }
    }
    proposalButton = null;
  }
  function consumeProposal() {
    // La confirmación ya fue enviada: el botón se retira sin anunciar la propuesta como vencida.
    if (proposalButton) proposalButton.remove();
    proposalButton = null;
  }
  function showProposal(event) {
    invalidateProposal();
    const card = create('section', 'booking-proposal');
    card.setAttribute('aria-label', 'Propuesta de reserva del servidor');
    card.append(create('h3', '', 'Propuesta de reserva · aún no creada'),
      create('p', '', `Huésped: ${event.guest_name}`),
      create('p', '', `Habitación: ${event.room_name} (${event.room_code})`),
      create('p', '', `${event.checkin} → ${event.checkout} · ${event.nights} noches`),
      create('p', '', `${event.adults} adultos · ${event.children} niños`),
      create('p', 'ticket-total', `${money.format(Number(event.total_clp) || 0)} CLP`),
      create('p', '', event.simulated === true ? 'PMS simulado · sin reserva real.' : 'Entorno no simulado: confirmación no disponible en esta demo.'));
    if (autonomousBooking && event.simulated === true) {
      const button = create('button', 'button primary', 'Sí, confirmo la reserva');
      button.type = 'button';
      button.addEventListener('click', () => {
        if (button !== proposalButton || button.disabled) return;
        sendMessage(CONFIRMATION_TEXT);
      });
      proposalButton = button;
      card.append(create('p', '', 'Revisa todos los datos. El servidor vuelve a validar la propuesta, su vigencia y disponibilidad al confirmar.'), button);
    }
    lastAssistant.append(card);
    get('assistant-announcement').textContent += ` ${card.textContent}`;
    scrollToLatest();
  }
  let actionCount = 0;
  function updateActionsToggle() {
    const panel = get('actions-panel');
    const toggle = get('toggle-actions');
    const open = !panel.hidden;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? 'Ocultar acciones del asistente' :
      (actionCount ? `Ver acciones del asistente (${actionCount})` : 'Ver acciones del asistente');
    const grid = document.querySelector('.demo-grid');
    if (grid) grid.classList.toggle('with-actions', open);
  }
  // En escritorio la traza se ve junto al teléfono; en móvil arranca cerrada para no alargar la página.
  if (window.matchMedia('(min-width: 1000px)').matches) get('actions-panel').hidden = false;
  updateActionsToggle();
  get('toggle-actions').addEventListener('click', () => {
    get('actions-panel').hidden = !get('actions-panel').hidden;
    updateActionsToggle();
  });
  async function showEvents(events, version = null) {
    if (!Array.isArray(events) || !events.length) return;
    actionCount += events.filter(event => event && event.type === 'tool_call').length;
    updateActionsToggle();
    get('timeline-empty').hidden = true;
    get('timeline').append(create('p', 'turn-label', `Turno ${turns} · acciones del asistente`));
    for (const event of events) {
      if (!event || typeof event !== 'object') continue;
      if (event.type === 'booking_proposal') { showProposal(event); continue; }
      const card = eventCard(event);
      if (!card) continue;
      get('timeline').append(card);
      get('timeline').scrollTop = get('timeline').scrollHeight;
      if (!reducedMotion.matches) {
        await pause(220);
        // Una demo guiada detenida no sigue animando la traza pendiente.
        if (version !== null && version !== scenarioVersion) return;
      }
    }
  }
  async function sendMessage(text, retry = false, guided = false) {
    if (busy || tracing || coolingDown() || (scenarioRunning && !guided)) return false;
    const message = String(text).trim();
    if (!message || message.length > 400) return false;
    // La confirmación de la propia propuesta no la vence: la tarjeta debe seguir en pantalla
    // mientras la reserva se crea; cualquier otro turno sí invalida la propuesta anterior.
    const confirmingProposal = !retry && message === CONFIRMATION_TEXT;
    if (!confirmingProposal) invalidateProposal();
    // ¿El foco estaba en la conversación? Un botón de respuesta rápida activado por teclado se
    // desmonta con clearSuggestions y el foco caería al body: se captura antes de limpiar.
    const chatHadFocus = document.activeElement === input ||
      Boolean(document.activeElement && messageList.contains && messageList.contains(document.activeElement));
    busy = true;
    clearChatError();
    clearSuggestions();
    if (!retry) addMessage('user', message);
    if (confirmingProposal) consumeProposal();
    input.value = '';
    updateControls();
    let success = false;
    try {
      const data = await request('/api/demo/chat', {session_id:sessionId, message});
      if (typeof data.reply !== 'string') throw {message:'La respuesta llegó incompleta. Reintenta en un momento.'};
      turns += 1;
      await revealReply(data.reply, data.quick_replies);
      // El tiempo de respuesta solo se muestra cuando el servidor lo midió: nunca «Respuesta en — s».
      const llmMs = data.usage?.llm_ms;
      const responseTime = get('response-time');
      if (typeof llmMs === 'number' && Number.isFinite(llmMs)) {
        responseTime.textContent = `Respuesta en ${(llmMs / 1000).toLocaleString('es-CL', {maximumFractionDigits:2})} s`;
        responseTime.hidden = false;
      }
      get('messages-left').textContent = `Mensajes restantes: ${data.usage?.messages_left ?? '—'}`;
      // La respuesta ya está en pantalla: se libera el composer antes de animar la traza.
      busy = false;
      // La traza anima con su propia señal: impide un turno simultáneo sin bloquear el composer.
      tracing = true;
      updateControls();
      await showEvents(data.events, guided ? scenarioVersion : null);
      success = true;
    } catch (error) {
      showChatError(error.message || 'No se pudo enviar el mensaje. Reintenta.', () => sendMessage(message, true));
    } finally {
      busy = false;
      tracing = false;
      updateControls();
      scrollToLatest();
      // Se devuelve el foco al composer solo si estaba en la conversación: no se roba ni reabre el teclado móvil.
      if (chatHadFocus) input.focus({preventScroll:true});
    }
    return success;
  }
  function clearConversation() {
    invalidateProposal();
    messageList.replaceChildren();
    messageList.append(create('div', 'chat-date', 'Hoy'), disclaimerNote);
    get('timeline').replaceChildren();
    get('timeline-empty').hidden = false;
    actionCount = 0;
    updateActionsToggle();
    get('response-time').hidden = true;
    get('messages-left').textContent = 'Mensajes restantes: —';
    get('scenario-status').textContent = '';
    input.value = '';
    pinned = true;
    turns = 0;
    clearChatError();
    const greeting = initialGreeting();
    addMessage('assistant', greeting.text, greeting.replies);
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
      booking:['Quiero consultar disponibilidad, sin crear una reserva', exampleDates(), '2 adultos y 1 niño'],
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
      get('scenario-status').textContent = name === 'booking' ?
        'Consulta terminada, no se creó una reserva. Ahora elige una opción ofrecida, escribe un nombre ficticio, revisa la propuesta del servidor y confirma manualmente solo si estás de acuerdo.' :
        name === 'human' ? 'Derivación simulada: no se notificó a recepción. Usa el widget separado de Chatwoot para contactar al equipo.' :
        'Demo guiada terminada. Ahora puedes continuar la conversación.';
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

  // El canal real de Chatwoot se carga solo al usarlo: su SDK pesa más que toda la página.
  const chatStatus = get('chat-status');
  const chatUnavailable = 'El canal de recepción no está disponible en este momento. Vuelve a intentarlo más tarde.';
  let chatwootReady = false;
  let chatOpenRequested = false;
  let chatwootLoad = null;

  function openChatwoot() {
    if (!window.$chatwoot || typeof window.$chatwoot.toggle !== 'function') return false;
    try {
      window.$chatwoot.toggle('open');
      chatStatus.textContent = 'Chat de recepción abierto.';
      return true;
    } catch (_) {
      chatStatus.textContent = 'No se pudo abrir el canal de recepción. Reintenta en un momento.';
      return false;
    }
  }

  function loadChatwoot() {
    if (chatwootLoad) return chatwootLoad;
    const cfg = window.COPILOTO_CONFIG;
    if (!cfg || !cfg.websiteToken) return Promise.reject(new Error('sin token'));
    const chatwootBase = resolveUrl(cfg.chatwootUrl || 'http://localhost:3000').replace(/\/+$/, '');
    window.chatwootSettings = { locale: "es", position: "right", type: "expanded_bubble",
                                launcherTitle: "Escribir a recepción", hideMessageBubble: true };
    chatwootLoad = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = chatwootBase + "/packs/js/sdk.js";
      script.async = true;
      script.onload = () => {
        try {
          window.chatwootSDK.run({ websiteToken: cfg.websiteToken, baseUrl: chatwootBase });
          resolve();
        } catch (error) { chatwootLoad = null; reject(error); }
      };
      script.onerror = () => { chatwootLoad = null; reject(new Error('carga fallida')); };
      document.body.appendChild(script);
    });
    return chatwootLoad;
  }

  window.addEventListener('chatwoot:ready', () => {
    chatwootReady = true;
    chatStatus.textContent = 'La bandeja real de recepción está lista.';
    if (chatOpenRequested) { chatOpenRequested = false; openChatwoot(); }
  });

  get('open-chat').addEventListener('click', async () => {
    if (openChatwoot()) return;
    chatStatus.textContent = 'Abriendo el canal de recepción…';
    chatOpenRequested = true;
    try {
      await loadChatwoot();
      // Si el SDK avisa que está listo, el evento abre el chat; si no, el próximo clic lo hace.
      if (chatwootReady) { chatOpenRequested = false; openChatwoot(); }
      else {
        // Respaldo acotado: si el SDK nunca avisa que está listo, el estado no queda colgado para siempre.
        window.setTimeout(() => {
          if (!chatOpenRequested) return;
          chatOpenRequested = false;
          if (!openChatwoot()) chatStatus.textContent = 'El canal de recepción tardó en responder. Vuelve a intentarlo.';
        }, 4000);
      }
    } catch (_) {
      chatOpenRequested = false;
      console.warn('Chatwoot no disponible: ¿levantaste el stack con make up?');
      chatStatus.textContent = chatUnavailable;
    }
  });
  // Barra fija: borde y progreso de lectura cuando la página ya se desplazó.
  const topbar = get('topbar');
  const progress = get('scroll-progress');
  if (topbar && progress) {
    let frame = 0;
    const syncTopbar = () => {
      frame = 0;
      topbar.classList.toggle('scrolled', window.scrollY > 8);
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = scrollable > 0 ? Math.min(1, Math.max(0, window.scrollY / scrollable)) : 0;
      progress.style.setProperty('--progress', ratio.toFixed(4));
    };
    const requestSync = () => { if (!frame) frame = window.requestAnimationFrame(syncTopbar); };
    syncTopbar();
    window.addEventListener('scroll', requestSync, {passive:true});
    window.addEventListener('resize', requestSync);
  }

  // Pausa de animaciones fuera de pantalla: el hero sostiene siete animaciones infinitas.
  const animatedSections = document.querySelectorAll('.hero-shell');
  if (animatedSections.length && 'IntersectionObserver' in window) {
    const motionObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => entry.target.classList.toggle('is-offscreen', !entry.isIntersecting));
    }, {rootMargin: '140px'});
    animatedSections.forEach(element => motionObserver.observe(element));
  }
  document.addEventListener('visibilitychange', () => {
    document.body.classList.toggle('is-hidden', document.hidden);
  });

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
  // Conexiones en vivo: consultan endpoints reales y, si fallan, muestran el fallo.
  const liveEndpoints = {
    health: {
      path: '/health?probe=readiness',
      describe: (data, ms) => `Proceso/SQLite: ${data.status || 'sin estado'} · ${ms} ms. No comprueba todas las integraciones.`
    },
    status: {
      path: '/api/demo/status',
      describe: data => data.ai_enabled ?
        `Modelo ${data.model || 'sin nombre'} · ${data.messages_per_session} mensajes por sesión · ` +
        (data.autonomous_booking ? 'reserva simulada con propuesta y confirmación explícita' : 'sin permiso para crear reservas') :
        'Sin IA configurada: responde el flujo guiado.'
    },
    metrics: {
      path: '/metricas/data.json?days=7',
      // Las métricas exigen sesión del panel: la consola la obtuvo con el modo demo.
      credentials: 'include',
      describe: data => {
        // ai_tools llega como {herramienta: veces}; se muestra el total y la más usada.
        const tools = Object.entries(data.ai_tools || {}).sort((a, b) => b[1] - a[1]);
        const total = tools.reduce((sum, [, veces]) => sum + veces, 0);
        const top = tools.length ? ` · más usada: ${tools[0][0]}` : '';
        return `${data.ai_replies ?? 0} respuestas de IA · ${data.ai_bookings ?? 0} reservas · ` +
          `${total} herramientas${top}`;
      }
    }
  };
  document.querySelectorAll('[data-live]').forEach(card => {
    const spec = liveEndpoints[card.dataset.live];
    const button = card.querySelector('.live-button');
    const result = card.querySelector('.live-result');
    if (!spec || !button || !result) return;
    button.addEventListener('click', async () => {
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      card.classList.remove('is-ok', 'is-error');
      result.textContent = 'Consultando…';
      const started = performance.now();
      try {
        const data = await request(spec.path, undefined, {credentials: spec.credentials});
        result.textContent = spec.describe(data, Math.round(performance.now() - started));
        card.classList.add('is-ok');
      } catch (error) {
        result.textContent = error.status === 0 ?
          'Sin respuesta del servidor: levanta el stack y vuelve a intentar.' :
          (error.message || 'No se pudo consultar este endpoint.');
        card.classList.add('is-error');
      } finally {
        button.disabled = false;
        button.removeAttribute('aria-busy');
      }
    });
  });

  clearConversation();
  loadStatus();
})();
