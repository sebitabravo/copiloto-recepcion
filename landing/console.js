/* Consola de demo: pestañas Huésped / Recepción / Admin, interruptor de modo demo.
   Se carga después de demo.js y voice.js: no toca sus ids ni repite su trabajo.
   Sin credenciales en el navegador: la sesión llega por cookie del servidor. */
(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const config = window.COPILOTO_CONFIG || {};
  const copilotoUrl = (config.copilotoUrl || 'http://localhost:8100').replace(/\/+$/, '');
  // demo.js expone este resolutor para visitas por LAN; si no cargó, la URL cruda sirve igual.
  const resolve = typeof window.resolveDemoUrl === 'function' ? window.resolveDemoUrl : value => value;
  const baseUrl = resolve(copilotoUrl).replace(/\/+$/, '');
  const pmsBase = resolve('http://localhost:8200').replace(/\/+$/, '');
  const chatwootBase = resolve(config.chatwootUrl || 'http://localhost:3000').replace(/\/+$/, '');

  /* ---------- utilidades ---------- */

  const create = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };
  const fmtSeconds = value => {
    const total = Number(value);
    if (!Number.isFinite(total) || total < 0) return '—';
    const seconds = Math.round(total);
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  };
  // C3: una espera de una hora o más se lee en horas y minutos («10 h 38 min»), nunca «636:16».
  const fmtWait = value => {
    const total = Number(value);
    if (!Number.isFinite(total) || total < 3600) return fmtSeconds(value);
    const minutes = Math.floor(total / 60);
    return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  };
  // C3: Chatwoot bautiza a los visitantes anónimos como «cool-mountain-791»; se muestran como lo que son.
  const guestLabel = (name, id) => {
    const value = typeof name === 'string' ? name.trim() : '';
    const anonymous = /^[a-záéíóúñ]+-[a-záéíóúñ]+-(\d+)$/i.exec(value);
    if (anonymous) return `Visitante web · ${anonymous[1]}`;
    return value || (id === undefined || id === null ? 'Conversación sin nombre' : `Conversación ${id}`);
  };
  const dateLabel = value => {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(parsed.getTime()) ? value :
      new Intl.DateTimeFormat('es-CL', {day: '2-digit', month: '2-digit', timeZone: 'UTC'}).format(parsed);
  };
  const plural = (number, one, many) => Number(number) === 1 ? `${number} ${one}` : `${number} ${many}`;

  async function api(path, options = {}) {
    return fetch(baseUrl + path, {credentials: 'include', cache: 'no-store', ...options});
  }

  /* ---------- pestañas accesibles ---------- */

  const TAB_ENTRIES = [
    {tab: get('tab-huesped'), panel: get('panel-huesped')},
    {tab: get('tab-recepcion'), panel: get('panel-recepcion')},
    {tab: get('tab-admin'), panel: get('panel-admin')}
  ];
  let currentTab = 0;

  function activateRecepcion() {
    startQueuePoll();
    if (selectedId) showDetail(selectedId, {quiet: true});
    else refreshQueue();
  }

  function selectTab(index, options = {}) {
    TAB_ENTRIES.forEach((entry, position) => {
      entry.tab.setAttribute('aria-selected', String(position === index));
      entry.tab.tabIndex = position === index ? 0 : -1;
      entry.panel.hidden = position !== index;
    });
    currentTab = index;
    if (index === 1) activateRecepcion();
    else stopQueuePoll();
    if (index === 2) loadAdminFrame();
    if (options.focus) TAB_ENTRIES[index].tab.focus();
  }

  // El keydown vive en el tablist; sin contenedor (DOM suelto), cae en la propia pestaña activa.
  const tablist = TAB_ENTRIES[0].tab.parentElement || TAB_ENTRIES[0].tab;
  tablist.addEventListener('keydown', event => {
    const last = TAB_ENTRIES.length - 1;
    let next = null;
    if (event.key === 'ArrowRight') next = currentTab === last ? 0 : currentTab + 1;
    else if (event.key === 'ArrowLeft') next = currentTab === 0 ? last : currentTab - 1;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = last;
    if (next === null) return;
    event.preventDefault();
    selectTab(next, {focus: true});
  });
  TAB_ENTRIES.forEach((entry, index) => entry.tab.addEventListener('click', () => selectTab(index)));

  // Los anclas del canal y del simulador viven en la pestaña Huésped: llegar a ellos la activa.
  document.querySelectorAll('a[href="#canal"], a[href="#demo"]').forEach(anchor => {
    anchor.addEventListener('click', () => selectTab(0));
  });

  /* ---------- modo demo (L9): interruptor persistente, sin credenciales en la página ---------- */

  const DEMO_KEY = 'copiloto.demo';
  const demoSwitch = get('demo-mode-switch');
  const banner = get('demo-banner');
  const bannerText = get('demo-banner-text');
  let demoOn = readStoredMode();

  function readStoredMode() {
    let stored;
    try { stored = window.localStorage.getItem(DEMO_KEY); } catch (_) { return true; }
    return stored !== '0';
  }
  function persistMode() {
    try { window.localStorage.setItem(DEMO_KEY, demoOn ? '1' : '0'); } catch (_) { /* sigue en memoria */ }
  }

  // Estado del acceso automático: off | starting | ready | no-session | unavailable | rate | error
  let demoSession = demoOn ? 'starting' : 'off';
  let sessionRequested = false;
  // El servidor respondió al sondeo inicial que el modo demo está apagado: el interruptor queda
  // deshabilitado con explicación en vez de dejar que el POST falle más adelante.
  let demoDisabledOnServer = false;

  // Un solo aviso de modo demo: el de privacidad vive dentro del chat, junto a donde se escribe.
  const BANNER_ON = 'Modo demo: recepción y el PMS se abren sin contraseña. Apágalo para entrar como el personal.';
  const BANNER_OFF = 'Modo demo apagado: recepción pide la contraseña del panel y el PMS el token del personal.';
  const BANNER_SERVER_OFF = 'Demo deshabilitada en el servidor: recepción y el PMS se abren con sus credenciales propias.';
  const SESSION_LABELS = {
    ready: 'Sesión de demo lista',
    starting: 'Preparando sesión…',
    off: 'Entrada manual',
    unavailable: 'Demo no disponible',
    'no-session': 'Sin sesión',
    rate: 'En pausa',
    error: 'Sin conexión'
  };

  function syncChrome() {
    demoSwitch.setAttribute('aria-checked', String(demoOn));
    demoSwitch.disabled = demoDisabledOnServer;
    banner.classList.toggle('is-off', !demoOn);
    bannerText.textContent = demoDisabledOnServer ? BANNER_SERVER_OFF : (demoOn ? BANNER_ON : BANNER_OFF);
    const label = SESSION_LABELS[demoSession];
    const pill = get('recepcion-session');
    if (pill) pill.textContent = label || '';
    if (adminLoaded) loadAdminFrame();
    get('admin-metrics').href = `${baseUrl}/metricas`;
    // Los enlaces del pie salen de config.js: el HTML público no fija hosts (C5).
    const links = {'footer-inbox': chatwootBase, 'footer-pms': `${pmsBase}/admin`, 'footer-metrics': `${baseUrl}/metricas`};
    for (const [id, href] of Object.entries(links)) { const link = get(id); if (link) link.href = href; }
  }

  async function requestDemoSession({retry = false} = {}) {
    if (!demoOn || (sessionRequested && !retry)) {
      syncChrome();
      return;
    }
    sessionRequested = true;
    demoSession = 'starting';
    syncChrome();
    renderRecepcionGates();
    try {
      const response = await fetch(`${baseUrl}/api/demo/session`, {
        method: 'POST', credentials: 'include', cache: 'no-store'
      });
      if (response.ok) demoSession = 'ready';
      else if (response.status === 403 || response.status === 404) demoSession = 'unavailable';
      else if (response.status === 429) demoSession = 'rate';
      else demoSession = 'error';
    } catch (_) {
      demoSession = 'error';
    }
    syncChrome();
    renderRecepcionGates();
    if (demoSession === 'ready' && currentTab === 1) refreshQueue();
  }

  // Sondeo único al cargar: GET /api/demo/session informa si el modo demo está disponible. Con la
  // demo apagada en el servidor el interruptor se deshabilita con explicación en el banner, en vez
  // de esperar a que el POST falle al entrar a Recepción. Sin respuesta del copiloto, el flujo actual
  // (POST + estados de error) queda intacto.
  async function probeDemoAvailability() {
    try {
      const response = await api('/api/demo/session');
      if (!response.ok) return;
      const data = await response.json();
      if (data && data.demo === false) {
        demoDisabledOnServer = true;
        syncChrome();
      }
    } catch (_) { /* La sesión y sus estados se deciden igual con el flujo de siempre. */ }
  }

  demoSwitch.addEventListener('click', () => {
    demoOn = !demoOn;
    persistMode();
    if (demoOn) {
      sessionRequested = false; // cada encendido vuelve a pedir la sesión una sola vez
      requestDemoSession().then(() => { if (currentTab === 1) refreshQueue(); });
    } else {
      demoSession = 'off';
      selectedId = null;
      stopQueuePoll();
      syncChrome();
      renderRecepcionGates();
    }
    if (adminLoaded) loadAdminFrame();
  });

  /* ---------- pestaña Recepción: solo lectura, con estados honestos ---------- */

  const recepcionState = get('recepcion-state');
  const recepcionQueue = get('recepcion-queue');
  const recepcionDetail = get('recepcion-detail');
  const recepcionDetailBody = get('recepcion-detail-body');
  const recepcionSummary = get('recepcion-summary');
  let selectedId = null;
  let queuePoll = 0;

  const STEP_LABELS = {
    start: 'inicio', menu: 'menú', faq_menu: 'preguntas', ask_dates: 'pidiendo fechas',
    ask_adults: 'pidiendo adultos', ask_children: 'pidiendo niños', pick_room: 'eligiendo habitación',
    handed_off: 'derivada a recepción'
  };
  const PREBOOKING_LABELS = {
    active: 'pre-reserva activa', expired: 'pre-reserva vencida',
    converted: 'reserva confirmada', superseded: 'pre-reserva reemplazada'
  };

  function setState(kind, message, actions = []) {
    recepcionDetail.hidden = selectedId === null;
    recepcionQueue.hidden = true;
    if (recepcionSummary) recepcionSummary.hidden = true;
    recepcionState.hidden = false;
    recepcionState.className = `console-state ${kind || ''}`.trim();
    recepcionState.replaceChildren(create('p', '', message));
    for (const action of actions) recepcionState.append(action);
    return recepcionState;
  }

  function retryButton(label, handler) {
    const button = create('button', 'text-button', label);
    button.type = 'button';
    button.addEventListener('click', handler);
    return button;
  }

  const manualLink = () => {
    const link = create('a', 'text-button', 'Abrir el panel de recepción');
    link.href = `${baseUrl}/panel`;
    link.target = '_blank';
    link.rel = 'noopener';
    return link;
  };

  function renderRecepcionGates() {
    if (demoSession === 'ready') return;
    const pill = get('recepcion-session');
    if (pill) pill.textContent = SESSION_LABELS[demoSession] || '';
    if (!demoOn || demoSession === 'off') {
      get('recepcion-session').textContent = SESSION_LABELS.off;
      setState('gate', 'Modo demo desactivado: la recepción se abre con su contraseña. Esta vista de la consola no inventa datos.', [manualLink()]);
    } else if (demoSession === 'starting') {
      setState('', 'Preparando la sesión de recepción…');
    } else if (demoSession === 'unavailable') {
      setState('gate', 'Demo deshabilitada en el servidor: no hay acceso automático a recepción. Entra con la contraseña del panel.', [manualLink(), retryButton('Reintentar', () => requestDemoSession({retry: true}))]);
    } else if (demoSession === 'rate') {
      setState('rate', 'Límite temporal de la demo alcanzado. Espera un momento y reintenta.', [retryButton('Reintentar', () => requestDemoSession({retry: true}))]);
    } else if (demoSession === 'no-session') {
      setState('gate', 'Sin sesión de recepción: la sesión demo no está activa en este navegador.', [
        retryButton('Entrar con el modo demo', () => { sessionRequested = false; requestDemoSession({retry: true}).then(() => { if (currentTab === 1) refreshQueue(selectedId); }); }),
        manualLink()
      ]);
    } else {
      setState('error', 'No se pudo conectar con el servidor de recepción. Levanta el stack y reintenta.', [retryButton('Reintentar', () => requestDemoSession({retry: true}))]);
    }
  }

  async function refreshQueue(keepSelection = null) {
    if (currentTab !== 1) return;
    if (!demoOn || demoSession !== 'ready') return renderRecepcionGates();
    if (keepSelection) { selectedId = keepSelection; return showDetail(keepSelection, {quiet: true}); }
    selectedId = null;
    setState('', 'Consultando la cola de recepción…');
    try {
      const response = await api('/api/panel/queue');
      if (response.status === 401 || response.status === 403) {
        demoSession = 'no-session';
        syncChrome();
        return renderRecepcionGates();
      }
      if (response.status === 429) {
        return setState('rate', 'Límite temporal de la demo alcanzado. Espera un momento y reintenta.', [retryButton('Reintentar', () => refreshQueue())]);
      }
      if (!response.ok) {
        return setState('error', `La cola no respondió bien (código ${response.status}). Reintenta en unos segundos.`, [retryButton('Reintentar', () => refreshQueue())]);
      }
      const data = await response.json();
      const items = Array.isArray(data && data.conversations) ? data.conversations : [];
      if (!items.length) {
        return setState('', 'Sin conversaciones todavía. Cuando un huésped escriba, aparece acá.');
      }
      renderQueue(items, data);
    } catch (_) {
      setState('error', 'Sin conexión con el servidor de recepción. Levanta el stack y reintenta.', [retryButton('Reintentar', () => refreshQueue())]);
    }
  }

  // Riesgo de una espera frente a las metas del servidor: bad (vencida), warn (por vencer) u ok.
  function waitRisk(seconds, amber, red) {
    if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return null;
    if (Number.isFinite(red) && seconds >= red) return 'bad';
    if (Number.isFinite(amber) && seconds >= amber) return 'warn';
    return 'ok';
  }

  // Resumen sobre la cola: cuántas conversaciones hay y cuántas por nivel de riesgo.
  function renderSummary(items, amber, red) {
    if (!recepcionSummary) return;
    const counts = {bad: 0, warn: 0, ok: 0};
    for (const item of items) {
      const risk = waitRisk(item.waiting_s, amber, red);
      if (risk) counts[risk] += 1;
    }
    recepcionSummary.replaceChildren(create('b', '', plural(items.length, 'conversación', 'conversaciones')));
    const labels = {bad: plural(counts.bad, 'vencida', 'vencidas'), warn: `${counts.warn} por vencer`, ok: `${counts.ok} en plazo`};
    for (const kind of ['bad', 'warn', 'ok']) {
      if (counts[kind]) recepcionSummary.append(create('span', `risk ${kind}`, labels[kind]));
    }
    recepcionSummary.hidden = false;
  }

  function renderQueue(items, data) {
    const amber = Number(data && data.amber_s);
    const red = Number(data && data.red_s);
    recepcionState.hidden = true;
    recepcionDetail.hidden = true;
    recepcionQueue.hidden = false;
    recepcionQueue.replaceChildren();
    renderSummary(items.filter(item => item && typeof item === 'object'), amber, red);
    for (const item of items) {
      if (!item || typeof item !== 'object') continue;
      const row = document.createElement('li');
      const button = create('button', 'console-row');
      button.type = 'button';
      const identity = create('span', 'console-row-name');
      identity.append(create('b', '', guestLabel(item.contact_name, item.conversation_id)));
      const meta = [];
      if (typeof item.step === 'string' && item.step) meta.push(STEP_LABELS[item.step] || item.step);
      if (typeof item.prebooking === 'string' && item.prebooking) meta.push(PREBOOKING_LABELS[item.prebooking] || item.prebooking);
      if (item.needs_human === true) meta.push('necesita a una persona');
      identity.append(create('span', 'sub', meta.join(' · ')));
      button.append(identity);
      const wait = create('span', 'risk');
      const risk = waitRisk(item.waiting_s, amber, red);
      if (!risk) {
        wait.textContent = '—';
      } else {
        wait.textContent = fmtWait(item.waiting_s);
        if (risk !== 'ok') wait.classList.add(risk);
      }
      button.append(wait);
      button.addEventListener('click', () => showDetail(item.conversation_id));
      row.append(button);
      recepcionQueue.append(row);
    }
  }

  function slaView(sla, nowSeconds) {
    if (!sla || typeof sla !== 'object' || !sla.started_at) return {label: 'Sin cronómetro: aún no hay traspaso en turno', css: ''};
    const elapsedValue = (sla.stopped_at ?? nowSeconds) - sla.started_at;
    if (!Number.isFinite(elapsedValue)) return {label: 'Cronómetro sin lectura', css: ''};
    const elapsed = Math.max(0, Math.round(elapsedValue));
    const red = Number(sla.red_s) || 180;
    const amber = Number(sla.amber_s) || Math.round(red / 1.5);
    if (sla.stopped_at) {
      return elapsed < red ? {label: `Respondido a tiempo · ${fmtWait(elapsed)}`, css: 'ok'} :
        {label: `Respondido fuera de meta · ${fmtWait(elapsed)}`, css: 'bad'};
    }
    if (elapsed >= red) return {label: `Plazo vencido: responder ya · ${fmtWait(elapsed)}`, css: 'bad'};
    if (elapsed >= amber) return {label: `Por vencer · ${fmtWait(elapsed)}`, css: 'warn'};
    return {label: `En plazo · ${fmtWait(elapsed)}`, css: 'ok'};
  }

  async function showDetail(id, {quiet = false} = {}) {
    selectedId = id;
    if (!quiet) setState('', 'Leyendo la conversación…');
    else setState('', 'Actualizando la conversación…');
    try {
      const response = await api(`/api/panel/${encodeURIComponent(String(id))}`);
      if (response.status === 401 || response.status === 403) {
        demoSession = 'no-session';
        selectedId = null;
        syncChrome();
        return renderRecepcionGates();
      }
      if (response.status === 429) {
        return setState('rate', 'Límite temporal de la demo alcanzado. Espera un momento y reintenta.', [retryButton('Volver a la cola', () => { selectedId = null; refreshQueue(); })]);
      }
      if (!response.ok) {
        return setState('error', `La conversación no respondió bien (código ${response.status}).`, [retryButton('Volver a la cola', () => { selectedId = null; refreshQueue(); })]);
      }
      renderDetail(await response.json());
    } catch (_) {
      setState('error', 'Sin conexión con el servidor de recepción.', [retryButton('Volver a la cola', () => { selectedId = null; refreshQueue(); })]);
    }
  }

  function detailRow(dl, term, value) {
    dl.append(create('dt', '', term), create('dd', '', value === undefined || value === null || value === '' ? '—' : value));
  }

  function renderDetail(snapshotResponse) {
    const snapshot = snapshotResponse && typeof snapshotResponse === 'object' ? snapshotResponse : {};
    const data = (typeof snapshot.data === 'object' && snapshot.data) || {};
    const sla = slaView(snapshot && snapshot.sla, Number(snapshot && snapshot.now));
    recepcionState.hidden = true;
    recepcionQueue.hidden = true;
    recepcionDetail.hidden = false;
    recepcionDetailBody.replaceChildren();

    const heading = create('div', 'section-heading');
    const titleWrap = create('div');
    titleWrap.append(
      create('p', 'eyebrow', 'Detalle de la conversación'),
      create('h3', '', guestLabel(snapshot.contact_name))
    );
    heading.append(titleWrap, create('span', `risk risk-badge ${sla.css || ''}`.trim(), sla.label));
    recepcionDetailBody.append(heading);

    const dl = create('dl', 'detail-list');
    const checkin = typeof data.checkin === 'string' ? dateLabel(data.checkin) : null;
    const checkout = typeof data.checkout === 'string' ? dateLabel(data.checkout) : null;
    detailRow(dl, 'Estado del flujo', (typeof snapshot.step === 'string' && (STEP_LABELS[snapshot.step] || snapshot.step)) || '—');
    detailRow(dl, 'Estancia', checkin && checkout ? `${checkin} → ${checkout}` : '—');
    detailRow(dl, 'Huéspedes', data.adults ? `${plural(data.adults, 'adulto', 'adultos')} · ${plural(data.children ?? 0, 'niño', 'niños')}` : '—');
    detailRow(dl, 'Habitación', (typeof snapshot.room_name === 'string' && snapshot.room_name) || (checkin ? 'A definir por recepción' : '—'));
    detailRow(dl, 'Lectura PMS', (typeof data.read_label === 'string' && data.read_label) || (typeof data.read_at === 'string' && data.read_at) || '—');
    const prebooking = snapshot.prebooking;
    let prebookingText = 'Sin pre-reserva';
    if (prebooking && typeof prebooking === 'object') {
      if (prebooking.status === 'active') {
        const remaining = Number(prebooking.expires_at) - Number(snapshot.now);
        prebookingText = Number.isFinite(remaining) ? `Activa · vence en ${fmtWait(remaining)}` : 'Activa';
      } else {
        prebookingText = PREBOOKING_LABELS[prebooking.status] || prebooking.status;
      }
    }
    detailRow(dl, 'Pre-reserva', prebookingText);
    recepcionDetailBody.append(dl);

    const notesTitle = create('h3', 'console-notes-title', 'Notas privadas del turno');
    recepcionDetailBody.append(notesTitle);
    const notes = create('ol', 'console-notes');
    const noteItems = Array.isArray(snapshot && snapshot.notes) ? snapshot.notes : [];
    if (!noteItems.length) notes.append(create('li', 'console-note-empty', 'Sin notas privadas todavía.'));
    for (const note of noteItems.slice(0, 5)) {
      if (!note || typeof note !== 'object') continue;
      const item = create('li');
      item.append(create('p', '', typeof note.body === 'string' ? note.body : ''));
      item.append(create('small', '', `${note.author || '—'} · ${noteTimestamp(note.created_at)}`));
      notes.append(item);
    }
    recepcionDetailBody.append(notes);

    const pmsUrl = typeof (snapshot && snapshot.pms_url) === 'string' && /^https?:\/\//.test(snapshot.pms_url) ? snapshot.pms_url : null;
    const foot = create('p', 'small', 'El copiloto nunca confirma: la confirmación la hace una persona.');
    if (pmsUrl) {
      const link = create('a', 'text-button', 'Abrir la reserva en el PMS simulado');
      link.href = pmsUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      foot.append(' ', link);
    }
    recepcionDetailBody.append(foot);
  }

  function noteTimestamp(stamp) {
    const seconds = Number(stamp);
    if (!Number.isFinite(seconds)) return '';
    const date = new Date(seconds * 1000);
    return Number.isNaN(date.getTime()) ? '' :
      date.toLocaleString('es-CL', {dateStyle: 'short', timeStyle: 'short'});
  }

  get('recepcion-back').addEventListener('click', () => {
    selectedId = null;
    refreshQueue();
  });

  function startQueuePoll() {
    if (queuePoll) return;
    queuePoll = window.setInterval(() => {
      if (currentTab === 1 && demoSession === 'ready' && !selectedId) refreshQueue();
    }, 10000);
  }
  function stopQueuePoll() {
    if (!queuePoll) return;
    window.clearInterval(queuePoll);
    queuePoll = 0;
  }

  /* ---------- pestaña Admin: PMS simulado embebido, una persona confirma ---------- */

  let adminLoaded = false;

  function adminUrl() {
    return `${pmsBase}/admin${demoOn ? '?demo=1' : ''}`;
  }

  function loadAdminFrame() {
    adminLoaded = true;
    const frame = get('admin-frame');
    if (frame && frame.getAttribute('src') !== adminUrl()) frame.setAttribute('src', adminUrl());
  }

  /* ---------- arranque ---------- */

  syncChrome();
  selectTab(0);
  renderRecepcionGates();
  if (demoOn) requestDemoSession();
  probeDemoAvailability();
})();
