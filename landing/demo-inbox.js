/* Bandeja de recepción de la demo. Una lectura por ciclo trae la lista y el detalle abierto.
   Acción principal según el estado: «Tomar solicitud» o «Enviar respuesta». Una respuesta lleva su llave
   de idempotencia: «Reintentar» no la duplica. El reloj de primera respuesta corre desde el ingreso de la
   consulta comercial (servidor); tomar la solicitud no lo reinicia y un acuse no lo detiene. */
(() => {
  'use strict';
  const S = window.DemoShared;
  const $ = id => document.getElementById(id);
  const NAME_KEY = 'copiloto-demo-recepcion';
  const POLL_MS = 4000;
  const SUGGESTED_UNKNOWN = 'Estoy verificando los cupos para esas fechas y te confirmo por aquí en unos minutos.';
  // La sugerencia sale de la lectura que recepción acaba de hacer, nunca de un cupo supuesto.
  const suggestion = result => {
    const offer = result && result.ok && result.offers[0];
    if (!offer) return SUGGESTED_UNKNOWN;
    const room = offer.name.replace(/^Habitación\s+/i, '');
    return `Hay disponibilidad en ${room} para esas fechas. ¿Quieres avanzar con la reserva?`;
  };

  // `generation` sube con cada cambio de caso: una carga o acción que empezó con otra generación ya no manda
  // en la pantalla. `queued` pide otra lectura cuando la selección cambió con una carga en curso.
  const state = {
    me: null, items: [], selected: null, generation: 0, detail: null, fetchedAt: Date.now(),
    detailFetchedAt: Date.now(), amber: 120, target: 180, filter: 'todas', search: '', draft: {}, kind: 'answer',
    sending: false, retry: null, inventory: {}, pollTimer: 0, tickTimer: 0, loading: false, queued: false,
    stickBottom: false
  };

  // El detalle solo vale si es el del caso seleccionado: nunca se actúa sobre un detalle de otro caso.
  const currentDetail = () => (state.detail && state.detail.id === state.selected ? state.detail : null);
  const stillSelected = (id, generation) => state.selected === id && state.generation === generation;

  // ---------- sesión de recepción ----------

  async function enter(name) {
    // Entra a la corrida de esta página con la llave de operador de este navegador (id estable en el servidor).
    const body = {name, operator_key: S.operatorKey()};
    if (S.run) body.run = S.run;
    await S.api('/api/demo/session', {method: 'POST', body, staff: true});
    S.store.set('localStorage', NAME_KEY, name);
    state.me = name;
    $('inbox-name').textContent = name;
  }

  function askIdentity() {
    const dialog = $('identity-dialog');
    const field = $('identity-input');
    field.value = state.me || S.store.get('localStorage', NAME_KEY) || 'Sofía';
    $('identity-error').hidden = true;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    field.focus();
    field.select();
  }

  async function submitIdentity(event) {
    event.preventDefault();
    const name = $('identity-input').value.trim().replace(/\s+/g, ' ');
    try {
      await enter(name);
      $('identity-dialog').close?.();
      $('identity-dialog').removeAttribute('open');
      state.detail = null;
      state.selected = null;
      state.generation += 1;
      await refresh();
      $('inbox-identity').focus();
    } catch (error) {
      $('identity-error').hidden = false;
      $('identity-error').textContent = error.message;
    }
  }

  // ---------- lectura ----------

  async function refresh() {
    if (!state.me) return;
    if (state.loading) { state.queued = true; return; }
    state.loading = true;
    // La carga recuerda qué caso y qué generación pidió: si la persona cambia de caso, no pisa la pantalla.
    const ticket = {id: state.selected, generation: state.generation};
    try {
      const path = '/api/panel/requests' + (ticket.id ? `?selected=${ticket.id}` : '');
      const data = await S.api(path, {staff: true});
      state.fetchedAt = Date.now();
      state.items = data.requests;
      state.amber = data.amber_s;
      state.target = data.target_s;
      $('inbox-error').hidden = true;
      $('inbox-live').textContent = `En vivo · actualizado ${S.time(data.now)}`;
      if (stillSelected(ticket.id, ticket.generation)) {
        const detail = data.selected && data.selected.id === ticket.id ? data.selected : null;
        if (ticket.id && !detail) {
          // El caso ya no está en esta bandeja (p. ej. otra corrida): se suelta la selección.
          state.selected = null;
          state.generation += 1;
        }
        state.detail = detail;
        state.detailFetchedAt = state.fetchedAt;
      } else {
        state.queued = true;
      }
      renderList();
      renderDetail();
    } catch (error) {
      if (error.status === 401 && state.me) {
        try { await enter(state.me); } catch (_) { /* se muestra el error */ }
      }
      showError(error.message, refresh);
      $('inbox-live').textContent = 'Sin conexión';
    } finally {
      state.loading = false;
      if (state.queued) {
        state.queued = false;
        refresh();
      } else {
        schedule();
      }
    }
  }

  function schedule() {
    clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(() => (document.hidden ? schedule() : refresh()), POLL_MS);
  }

  function showError(text, retry) {
    const box = $('inbox-error');
    box.hidden = false;
    box.querySelector('span').textContent = text;
    state.retry = retry;
  }

  // ---------- lista ----------

  function visibleItems() {
    const query = state.search.trim().toLowerCase();
    return state.items.filter(item => {
      if (state.filter !== 'todas' && item.status !== state.filter) return false;
      if (!query) return true;
      return [item.code, item.preview, S.summary(item), item.assignee].join(' ').toLowerCase().includes(query);
    });
  }

  function waiting(item) {
    // Pendiente en turno: espera en vivo con color de riesgo. El resto: hora de ingreso.
    if (item.status === 'pendiente' && item.in_shift) {
      const seconds = S.liveElapsed(item.measurement, state.fetchedAt);
      return {text: S.clock(seconds), tone: S.waitTone(seconds, state.amber, state.target), live: true};
    }
    return {text: S.time(item.commercial_at), tone: '', live: false};
  }

  function renderList() {
    const list = $('inbox-items');
    list.textContent = '';
    const items = visibleItems();
    $('inbox-empty').hidden = items.length > 0;
    $('inbox-empty').textContent = state.items.length
      ? 'Ninguna solicitud coincide con el filtro.'
      : 'Aún no hay solicitudes. Envía una desde el chat del huésped.';
    for (const item of items) {
      const li = S.el('li');
      const button = S.el('button', 'item');
      button.type = 'button';
      button.dataset.id = item.id;
      if (item.id === state.selected) button.setAttribute('aria-current', 'true');
      const icon = S.el('span', 'ico');
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '💬';
      const badge = S.el('span', 'badge', item.status_label);
      badge.dataset.tone = S.tone(item.status);
      const wait = waiting(item);
      const when = S.el('span', 'when', wait.text);
      if (wait.live) { when.dataset.live = '1'; when.title = 'Espera desde el ingreso de la consulta'; }
      if (wait.tone) when.dataset.tone = wait.tone;
      button.append(icon, S.el('span', 'code', item.code), badge, S.el('span', 'sub', S.summary(item)), when);
      if (!item.in_shift && item.status === 'pendiente') button.append(S.el('span', 'flag', 'Fuera de turno'));
      else if (item.status === 'en_atencion' && item.last_guest_at && item.last_guest_at > (item.first_answer_at || 0)
        && item.first_answer_at) button.append(S.el('span', 'flag', 'Nuevo mensaje del huésped'));
      button.addEventListener('click', () => select(item.id));
      li.append(button);
      list.append(li);
    }
  }

  async function select(id) {
    const shown = currentDetail();
    if (shown) state.draft[shown.id] = currentDraft();
    state.selected = id;
    state.generation += 1;
    // Hasta que llegue el detalle del caso nuevo no hay acciones: nada puede apuntar al caso anterior.
    state.detail = null;
    renderList();
    renderDetail();
    await refresh();
    $('case-messages').focus({preventScroll: true});
  }

  // ---------- detalle ----------

  function currentDraft() {
    const field = $('reply-text');
    return field ? field.value : '';
  }

  const EVENT_TEXT = {
    request_created: event => `Solicitud ${event.payload.code} enviada a recepción`,
    request_taken: event => `${event.payload.assignee} tomó la solicitud`,
    human_first_reply: () => 'Primera respuesta pertinente: se detuvo el reloj',
    sla_breached: event => `Meta vencida: ${S.clock(event.payload.elapsed_s)} sin respuesta pertinente`,
    request_closed: () => 'Solicitud cerrada',
    night_capture: () => 'Ingresó fuera de turno'
  };

  function renderThread(detail) {
    const box = $('case-messages');
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
    box.textContent = '';
    const events = detail.events
      .filter(event => EVENT_TEXT[event.kind])
      .map(event => ({ts: event.ts, line: `${EVENT_TEXT[event.kind](event)} · ${S.time(event.ts)}`}));
    const entries = [
      ...detail.messages.map(message => ({ts: message.created_at, message})),
      ...events
    ].sort((a, b) => a.ts - b.ts || (a.message ? -1 : 1));
    let previousRole = null;
    for (const entry of entries) {
      if (entry.message) {
        S.messageNodes(entry.message, 'staff', previousRole).forEach(node => box.append(node));
        previousRole = entry.message.role;
      } else {
        box.append(S.el('p', 'event-line', entry.line));
        previousRole = null;
      }
    }
    // Tras una acción propia (tomar, responder) el hilo baja siempre hasta lo último.
    if (atBottom || state.stickBottom || box.dataset.case !== String(detail.id)) box.scrollTop = box.scrollHeight;
    state.stickBottom = false;
    box.dataset.case = detail.id;
  }

  function renderAction(detail) {
    const box = $('case-action');
    const keep = box.dataset.case === String(detail.id) && box.dataset.mode === 'reply' && detail.actions.reply;
    if (keep) { updateSendButton(); return; }
    box.textContent = '';
    box.dataset.case = detail.id;
    box.dataset.mode = '';
    if (detail.status === 'cerrada') {
      box.append(S.el('p', '', `Solicitud cerrada ${S.dateTime(detail.closed_at)}. Si el huésped escribe de nuevo, el asistente lo atiende y una consulta nueva crea otra solicitud.`));
      return;
    }
    if (detail.actions.take) {
      box.append(S.el('p', '', 'Pendiente de recepción. Al tomarla quedas como responsable y el estado pasa a «En atención». El reloj sigue corriendo desde el ingreso de la consulta.'));
      const take = S.el('button', 'button-sm primary', 'Tomar solicitud');
      take.type = 'button';
      take.id = 'take-request';
      take.addEventListener('click', () => act('take'));
      box.append(take);
      return;
    }
    if (!detail.actions.reply) {
      box.append(S.el('p', '', `La atiende ${detail.assignee}. Solo la persona responsable responde en este hilo.`));
      return;
    }
    box.dataset.mode = 'reply';
    const form = S.el('form', 'reply-form');
    const label = S.el('label', 'sr-only', 'Respuesta al huésped');
    label.htmlFor = 'reply-text';
    const field = S.el('textarea');
    field.id = 'reply-text';
    field.maxLength = 1000;
    field.placeholder = 'Escribe la respuesta al huésped…';
    field.value = state.draft[detail.id] || '';
    field.addEventListener('input', updateSendButton);
    field.addEventListener('keydown', event => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); form.requestSubmit(); }
    });
    const kinds = S.el('fieldset', 'reply-kind');
    kinds.append(S.el('legend', '', 'Tipo de mensaje'));
    [['answer', 'Respuesta (cuenta para la meta)'], ['ack', 'Acuse (no detiene el reloj)']]
      .forEach(([value, text]) => {
        const option = S.el('label');
        const radio = S.el('input');
        radio.type = 'radio';
        radio.name = 'reply-kind';
        radio.value = value;
        radio.checked = state.kind === value;
        radio.addEventListener('change', () => { state.kind = value; });
        option.append(radio, document.createTextNode(text));
        kinds.append(option);
      });
    const row = S.el('div', 'action-row');
    const hint = S.el('span', 'hint', 'Ctrl + Enter envía');
    hint.style.color = 'var(--muted)';
    hint.style.fontSize = '.78rem';
    const send = S.el('button', 'button-sm primary', 'Enviar respuesta');
    send.type = 'submit';
    send.id = 'reply-send';
    row.append(hint, send);
    form.append(label, field, kinds, row);
    form.addEventListener('submit', event => { event.preventDefault(); reply(); });
    box.append(form);
    updateSendButton();
  }

  function updateSendButton() {
    const button = $('reply-send');
    const field = $('reply-text');
    if (button && field) button.disabled = state.sending || !field.value.trim();
  }

  function fact(term, value, extra, pendingValue = false) {
    const row = S.el('div');
    const dd = S.el('dd');
    if (value instanceof Node) dd.append(value);
    else dd.append(S.el('span', pendingValue ? 'pending-value' : '', value));
    if (extra) dd.append(S.el('small', '', extra));
    row.append(S.el('dt', '', term), dd);
    return row;
  }

  function renderCard(detail) {
    $('card-code').textContent = detail.code;
    const facts = $('card-facts');
    facts.textContent = '';
    const status = S.el('span', 'badge', detail.status_label);
    status.dataset.tone = S.tone(detail.status);
    const stay = S.stayRange(detail.checkin, detail.checkout);
    const guests = S.guests(detail);
    const measure = detail.measurement;
    const clock = S.el('span', 'clock');
    clock.dataset.live = measure.state === 'en_curso' || measure.state === 'vencida' ? '1' : '';
    const seconds = S.liveElapsed(measure, state.detailFetchedAt);
    clock.textContent = seconds == null ? '—' : S.clock(seconds);
    const reservation = S.el('span', 'badge', detail.reservation_label);
    reservation.dataset.tone = detail.reservation_status === 'confirmada' ? 'green' : 'amber';
    facts.append(
      fact('Estado', status),
      fact('Responsable', detail.assignee || 'Sin asignar', null, !detail.assignee),
      fact('Ingreso', S.dateTime(detail.commercial_at), 'Hora del servidor al entrar la consulta'),
      fact('Estadía', stay ? `${stay} · ${detail.nights} ${detail.nights === 1 ? 'noche' : 'noches'}` : 'Pendiente: sin fechas', null, !stay),
      fact('Huéspedes', guests || 'Pendiente: sin informar', null, !guests),
      fact('Canal', detail.channel_label),
      fact('Motivo', detail.reason_label),
      fact('Primera respuesta', clock, measure.state === 'fuera_de_turno'
        ? measure.label : `${measure.label} · meta ${S.clock(measure.target_s)}`),
      fact('Reserva', reservation, 'La confirma recepción en su sistema. Responder no reserva.')
    );
    $('inventory-check').disabled = !detail.actions.inventory;
    $('case-close').hidden = !detail.actions.close;
    renderInventory(detail);
    renderMeasure(detail);
  }

  function renderInventory(detail) {
    const box = $('inventory-result');
    const result = state.inventory[detail.id];
    box.textContent = '';
    if (!detail.checkin) { box.append(S.el('p', '', 'Sin fechas: pídeselas al huésped antes de verificar.')); return; }
    if (!result) return;
    if (result.ok) {
      box.append(S.el('p', '', `${result.source} · lectura ${result.read_at.slice(11, 16)} · preliminar`));
      const list = S.el('ul');
      if (!result.offers.length) list.append(S.el('li', '', 'Sin cupo para esas fechas y huéspedes.'));
      result.offers.forEach(offer => list.append(S.el('li', '',
        `${offer.name.replace(/^Habitación\s+/i, '')}: ${offer.available_units} libre${offer.available_units === 1 ? '' : 's'} · $${offer.nightly_price_clp.toLocaleString('es-CL')} por noche`)));
      if (result.more) list.append(S.el('li', '', `y ${result.more} tipo${result.more === 1 ? '' : 's'} más en el PMS`));
      box.append(list);
    } else {
      box.append(S.el('p', 'warn', `Disponibilidad por verificar: ${result.reason}. No informes cupos; responde con un seguimiento honesto.`));
    }
    if (detail.actions.reply) {
      const text = suggestion(result);
      const use = S.el('button', 'link-button', 'Usar respuesta sugerida');
      use.type = 'button';
      use.addEventListener('click', () => {
        const field = $('reply-text');
        if (!field) return;
        field.value = text;
        state.kind = 'answer';
        document.querySelector('input[name="reply-kind"][value="answer"]').checked = true;
        updateSendButton();
        field.focus();
      });
      box.append(use);
    }
  }

  const MEASURE_TEXT = {
    inbound: 'Mensaje del huésped', handoff: 'Traspaso a recepción', commercial_started: 'Consulta comercial registrada',
    request_created: 'Solicitud creada', request_taken: 'Asignación', human_ack: 'Acuse (no detiene el reloj)',
    human_first_reply: 'Primera respuesta pertinente', sla_breached: 'Meta vencida', pms_read: 'Lectura del PMS',
    request_closed: 'Cierre', night_capture: 'Captura fuera de turno', location_shown: 'Ubicación mostrada',
    faq_answered: 'FAQ respondida', prebooking_created: 'Pre-reserva auxiliar'
  };

  function renderMeasure(detail) {
    const box = $('card-measure');
    box.textContent = '';
    box.append(S.el('p', '',
      'El reloj parte cuando entra la consulta comercial (hora del servidor) y se detiene con la primera ' +
      'respuesta marcada como «Respuesta a la consulta». La pertinencia la declara quien responde: un acuse no ' +
      'detiene el reloj. Tomar la solicitud no lo reinicia. Fuera de turno no cuenta para la meta.'));
    if (detail.faq.length) {
      box.append(S.el('p', '', 'Ubicación y FAQ (meta < 10 s, desde el ingreso del mensaje):'));
      const faq = S.el('ol');
      detail.faq.forEach(item => faq.append(S.el('li', '',
        `${item.faq_id}: ${item.latency_s.toFixed(3)} s ${item.met ? '· dentro de la meta' : '· fuera de la meta'}`)));
      box.append(faq);
    }
    box.append(S.el('p', '', 'Eventos registrados (segundos desde el ingreso):'));
    const list = S.el('ol');
    detail.events.forEach(event => {
      const offset = Math.round(event.ts - detail.commercial_at);
      list.append(S.el('li', '', `+${S.clock(offset)} · ${MEASURE_TEXT[event.kind] || event.kind}`));
    });
    box.append(list);
  }

  function renderDetail() {
    const detail = currentDetail();
    $('case-empty').hidden = Boolean(detail);
    $('case-thread').hidden = !detail;
    $('case-card').hidden = !detail;
    $('inventory-check').disabled = !detail || !detail.actions.inventory;
    if (!detail) {
      const loading = state.selected && state.items.find(entry => entry.id === state.selected);
      const empty = $('case-empty');
      empty.textContent = '';
      empty.append(S.el('p', '', loading ? `Cargando ${loading.code}…`
        : 'Elige una solicitud para ver la conversación, el contexto y la acción que corresponde.'));
      $('case-action').dataset.case = '';
      $('case-action').textContent = '';
      return;
    }
    $('case-code').textContent = detail.code;
    $('case-status').textContent = detail.status_label;
    $('case-status').dataset.tone = S.tone(detail.status);
    $('case-sub').textContent = `${detail.channel_label} · ${detail.contact_name || 'Huésped'} · ${S.time(detail.commercial_at)}`;
    renderThread(detail);
    renderAction(detail);
    renderCard(detail);
  }

  // ---------- acciones ----------

  // Aplica la respuesta de una acción solo si su caso sigue seleccionado; si no, la lista se refresca sola.
  function applyResult(id, generation, detail) {
    if (!detail || detail.id !== id || !stillSelected(id, generation)) return false;
    state.detail = detail;
    state.detailFetchedAt = Date.now();
    renderDetail();
    return true;
  }

  async function act(action, target = null) {
    const detail = target || currentDetail();
    if (!detail) return;
    const {id, code} = detail;
    const generation = state.generation;
    const button = action === 'take' ? $('take-request') : $('case-close');
    if (button) button.disabled = true;
    try {
      const data = await S.api(`/api/panel/requests/${id}/${action}`, {method: 'POST', staff: true});
      $('case-action').dataset.mode = 'stale';
      state.stickBottom = true;
      if (applyResult(id, generation, data) && action === 'take') $('reply-text')?.focus();
    } catch (error) {
      if (error.data && error.data.request) applyResult(id, generation, error.data.request);
      showError(`${code}: ${error.message}`, () => act(action, {id, code}));
    } finally {
      if (button) button.disabled = false;
      refresh();
    }
  }

  // Un envío lleva su caso, su llave y su texto desde el primer intento: reintentar repite exactamente eso,
  // aunque la persona ya esté mirando otro caso.
  async function reply(retryWith = null) {
    if (state.sending) return;
    let pending = retryWith;
    if (!pending) {
      const detail = currentDetail();
      const field = $('reply-text');
      if (!detail || !field || $('case-action').dataset.case !== String(detail.id)) return;
      pending = {requestId: detail.id, code: detail.code, clientId: S.newId(), body: field.value.trim(), kind: state.kind};
    }
    if (!pending.body) return;
    const generation = state.generation;
    state.sending = true;
    updateSendButton();
    if ($('reply-send')) $('reply-send').textContent = 'Enviando…';
    try {
      const data = await S.api(`/api/panel/requests/${pending.requestId}/reply`, {method: 'POST', staff: true,
        body: {body: pending.body, kind: pending.kind, client_id: pending.clientId}});
      state.draft[pending.requestId] = '';
      $('inbox-error').hidden = true;
      state.stickBottom = true;
      const field = $('reply-text');
      if (field && $('case-action').dataset.case === String(pending.requestId)) field.value = '';
      applyResult(pending.requestId, generation, data.request);
    } catch (error) {
      // El texto queda en su borrador y el reintento usa el MISMO caso, llave y texto: no se duplica.
      state.draft[pending.requestId] = pending.body;
      showError(`No se envió la respuesta a ${pending.code}. ${error.message}`, () => reply(pending));
    } finally {
      state.sending = false;
      if ($('reply-send')) $('reply-send').textContent = 'Enviar respuesta';
      updateSendButton();
      refresh();
    }
  }

  async function checkInventory() {
    const detail = currentDetail();
    if (!detail) return;
    const {id} = detail;
    const generation = state.generation;
    const button = $('inventory-check');
    button.disabled = true;
    button.textContent = 'Consultando…';
    try {
      const data = await S.api(`/api/panel/requests/${id}/inventory`, {method: 'POST', staff: true,
        body: {simulate_down: $('inventory-down').checked}});
      // La lectura queda guardada con su caso: si la persona cambió de caso, se ve al volver a él.
      state.inventory[id] = data;
      applyResult(id, generation, data.request);
    } catch (error) {
      showError(`${detail.code}: ${error.message}`, checkInventory);
    } finally {
      button.textContent = 'Consultar el PMS';
      const shown = currentDetail();
      button.disabled = !(shown && shown.actions.inventory);
    }
  }

  function tick() {
    // Relojes en vivo sin pedir nada al servidor: elapsed del servidor + tiempo desde la lectura.
    document.querySelectorAll('#inbox-items .when[data-live="1"]').forEach(node => {
      const item = state.items.find(entry => String(entry.id) === node.parentElement.dataset.id);
      if (!item) return;
      const wait = waiting(item);
      node.textContent = wait.text;
      if (wait.tone) node.dataset.tone = wait.tone; else delete node.dataset.tone;
    });
    const clock = document.querySelector('#card-facts .clock[data-live="1"]');
    const shown = currentDetail();
    if (clock && shown) clock.textContent = S.clock(S.liveElapsed(shown.measurement, state.detailFetchedAt));
  }

  async function init() {
    $('identity-form').addEventListener('submit', submitIdentity);
    $('inbox-identity').addEventListener('click', askIdentity);
    $('inbox-filter').addEventListener('change', event => { state.filter = event.target.value; renderList(); });
    $('inbox-search').addEventListener('input', event => { state.search = event.target.value; renderList(); });
    $('inventory-check').addEventListener('click', checkInventory);
    $('case-close').addEventListener('click', () => {
      if (window.confirm('¿Cerrar la solicitud? El hilo vuelve al asistente.')) act('close');
    });
    $('inbox-error').querySelector('button').addEventListener('click', () => state.retry && state.retry());
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    state.tickTimer = setInterval(tick, 1000);
    const saved = S.store.get('localStorage', NAME_KEY);
    if (!saved) { askIdentity(); return; }
    try {
      await enter(saved);
      await refresh();
    } catch (error) {
      showError(error.message, init);
    }
  }

  window.DemoInbox = {init, refresh, select};
})();
