/* Plano de ocupación (Recepción) y dashboard (Administración) de /demo.
   Las dos vistas leen la misma ruta, GET /api/panel/occupancy: en local la sirve el copiloto con datos del PMS
   y en la versión estática la responde static-demo.js con datos simulados. Son de solo lectura.
   Las funciones puras (buildPlan, computeKpis) no tocan el DOM; todo texto del servidor entra con textContent. */
(() => {
  'use strict';
  const DAY_MS = 86400000;
  const TZ = 'America/Santiago';
  const WEEKDAYS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
  const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const RANGE_DAYS = 14;
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const toDay = iso => { const [y, m, d] = String(iso).split('-').map(Number); return Date.UTC(y, m - 1, d) / DAY_MS; };
  const fromDay = day => new Date(day * DAY_MS).toISOString().slice(0, 10);
  const addDays = (iso, count) => fromDay(toDay(iso) + count);
  const nights = booking => toDay(booking.checkout) - toDay(booking.checkin);

  function todayIso() {
    return new Intl.DateTimeFormat('en-CA', {timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit'})
      .format(new Date());
  }

  function lastName(fullName) {
    const parts = String(fullName || '').trim().split(/\s+/).filter(Boolean);
    return parts.length ? parts[parts.length - 1] : 'Sin nombre';
  }

  const people = booking => (booking.adults || 0) + (booking.children || 0);

  /* Columnas = días del rango; una reserva ocupa las noches [checkin, checkout): el día de salida queda libre. */
  function buildPlan(data) {
    const start = toDay(data.start);
    const count = Math.max(0, Number(data.days) || 0);
    const columns = [];
    for (let index = 0; index < count; index += 1) {
      const iso = fromDay(start + index);
      const weekday = new Date((start + index) * DAY_MS).getUTCDay();
      columns.push({iso, day: Number(iso.slice(8)), month: MONTHS[Number(iso.slice(5, 7)) - 1],
        weekday: WEEKDAYS[weekday], weekend: weekday === 0 || weekday === 6});
    }
    const byUnit = new Map((data.units || []).map(unit => [unit.room_id, []]));
    for (const booking of data.bookings || []) {
      const first = Math.max(toDay(booking.checkin), start);
      const last = Math.min(toDay(booking.checkout), start + count);
      const span = last - first;
      if (span <= 0 || !byUnit.has(booking.room_id)) continue;
      byUnit.get(booking.room_id).push({
        booking, column: first - start, span,
        cutStart: toDay(booking.checkin) < start, cutEnd: toDay(booking.checkout) > start + count,
        label: `${people(booking)} ${lastName(booking.guest_name)}`
      });
    }
    const rows = (data.units || []).map(unit => ({
      unit, bars: byUnit.get(unit.room_id).sort((a, b) => a.column - b.column)
    }));
    return {columns, rows};
  }

  /* Indicadores del día `today` y del rango completo. `occupied` cuenta unidades; `inHouse`, personas. */
  function computeKpis(data, today) {
    const units = data.units || [];
    const bookings = data.bookings || [];
    const total = units.length;
    const now = toDay(today);
    const staying = bookings.filter(b => toDay(b.checkin) <= now && toDay(b.checkout) > now);
    const start = toDay(data.start);
    const count = Math.max(0, Number(data.days) || 0);
    const perDay = [];
    for (let index = 0; index < count; index += 1) {
      const day = start + index;
      const occupied = bookings.filter(b => toDay(b.checkin) <= day && toDay(b.checkout) > day).length;
      perDay.push({iso: fromDay(day), occupied, pct: total ? Math.round((occupied / total) * 100) : 0});
    }
    const perType = new Map();
    for (const unit of units) {
      const entry = perType.get(unit.code) || {code: unit.code, short: unit.short, name: unit.name, units: 0, nights: 0};
      entry.units += 1;
      perType.set(unit.code, entry);
    }
    const typeOf = new Map(units.map(unit => [unit.room_id, unit.code]));
    for (const booking of bookings) {
      const entry = perType.get(typeOf.get(booking.room_id));
      if (!entry) continue;
      const first = Math.max(toDay(booking.checkin), start);
      const last = Math.min(toDay(booking.checkout), start + count);
      entry.nights += Math.max(0, last - first);
    }
    const types = [...perType.values()].map(entry => ({
      ...entry, pct: entry.units && count ? Math.round((entry.nights / (entry.units * count)) * 100) : 0
    }));
    return {
      total,
      occupied: staying.length,
      occupancyPct: total ? Math.round((staying.length / total) * 100) : 0,
      arrivals: bookings.filter(b => b.checkin === today).length,
      departures: bookings.filter(b => b.checkout === today).length,
      inHouse: staying.reduce((sum, b) => sum + people(b), 0),
      bySource: {ia: bookings.filter(b => b.source === 'ia').length,
        personal: bookings.filter(b => b.source !== 'ia').length},
      perDay, types
    };
  }

  const formatDate = iso => `${Number(iso.slice(8))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`;
  const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;

  function load(start, days) {
    const S = window.DemoShared;
    return S.api(`/api/panel/occupancy?start=${start}&days=${days}`, {staff: true});
  }

  function svg(tag, attrs = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, String(value));
    return node;
  }

  /* ---------- plano ---------- */

  function mountPlan(root) {
    const S = window.DemoShared;
    const el = S.el;
    const state = {start: todayIso(), data: null, token: 0};
    const toolbar = el('div', 'occ-toolbar');
    const range = el('span', 'occ-range');
    range.setAttribute('role', 'status');
    const button = (text, label, onClick) => {
      const node = el('button', 'button-sm', text);
      node.type = 'button';
      node.setAttribute('aria-label', label);
      node.addEventListener('click', onClick);
      return node;
    };
    toolbar.append(
      button('Hoy', 'Ir a hoy', () => go(todayIso())),
      button('←', 'Semana anterior', () => go(addDays(state.start, -7))),
      button('→', 'Semana siguiente', () => go(addDays(state.start, 7))),
      range
    );
    const message = el('p', 'occ-message');
    message.setAttribute('role', 'status');
    const scroller = el('div', 'occ-scroll');
    scroller.tabIndex = 0;
    scroller.setAttribute('role', 'region');
    scroller.setAttribute('aria-label', 'Plano de ocupación por habitación y día');
    const detail = el('div', 'occ-detail');
    detail.setAttribute('role', 'status');
    detail.setAttribute('aria-live', 'polite');
    const legend = el('p', 'occ-legend', 'Cada barra es una estadía: ocupa las noches desde la llegada hasta el día anterior a la salida. Solo lectura.');
    root.append(toolbar, message, scroller, detail, legend);

    function showDetail(booking, unit) {
      detail.textContent = '';
      detail.append(el('h4', '', `${booking.guest_name} · Hab. ${unit.number}`));
      const facts = el('dl', 'occ-facts');
      const origin = booking.source === 'ia' ? 'Asistente con IA' : 'Recepción';
      const rows = [
        ['Llegada', formatDate(booking.checkin)], ['Salida', formatDate(booking.checkout)],
        ['Noches', nights(booking)],
        ['Personas', `${plural(booking.adults, 'adulto', 'adultos')}${booking.children ? `, ${plural(booking.children, 'niño', 'niños')}` : ''}`],
        ['Origen', origin], ['Reserva', `#${booking.booking_id}`]
      ];
      for (const [term, value] of rows) facts.append(el('dt', '', term), el('dd', '', value));
      detail.append(facts);
    }

    function render() {
      const data = state.data;
      scroller.textContent = '';
      detail.textContent = '';
      const plan = buildPlan(data);
      const today = todayIso();
      const grid = el('div', 'occ-grid');
      grid.style.setProperty('--occ-days', plan.columns.length);
      const head = el('div', 'occ-row occ-head');
      head.append(el('div', 'occ-label occ-corner', 'Habitación'));
      for (const column of plan.columns) {
        const cell = el('div', 'occ-day');
        cell.append(el('span', 'occ-wd', column.weekday), el('b', '', column.day));
        if (column.weekend) cell.classList.add('is-weekend');
        if (column.iso === today) { cell.classList.add('is-today'); cell.setAttribute('aria-current', 'date'); }
        head.append(cell);
      }
      grid.append(head);
      for (const row of plan.rows) {
        const line = el('div', 'occ-row');
        const label = el('div', 'occ-label');
        label.append(el('b', '', `Hab. ${row.unit.number}`), el('span', '', row.unit.short));
        label.title = row.unit.name;
        line.append(label);
        plan.columns.forEach((column, index) => {
          const cell = el('div', 'occ-cell');
          cell.style.gridColumn = String(index + 2);
          if (column.weekend) cell.classList.add('is-weekend');
          if (column.iso === today) cell.classList.add('is-today');
          line.append(cell);
        });
        for (const bar of row.bars) {
          const node = el('button', 'occ-bar');
          node.type = 'button';
          node.style.gridColumn = `${bar.column + 2} / span ${bar.span}`;
          if (bar.booking.source === 'ia') node.classList.add('is-ia');
          if (bar.cutStart) node.classList.add('cut-start');
          if (bar.cutEnd) node.classList.add('cut-end');
          node.append(el('span', 'occ-guest', `👥 ${bar.label}`));
          if (bar.booking.source === 'ia') node.append(el('i', 'occ-chip', 'IA'));
          node.setAttribute('aria-label',
            `Hab. ${row.unit.number}, ${bar.booking.guest_name}, ${formatDate(bar.booking.checkin)} al ${formatDate(bar.booking.checkout)}`);
          node.addEventListener('click', () => showDetail(bar.booking, row.unit));
          line.append(node);
        }
        grid.append(line);
      }
      scroller.append(grid);
      range.textContent = `${formatDate(data.start)} – ${formatDate(addDays(data.start, data.days - 1))}`;
      message.textContent = data.simulated ? 'Datos de prueba: PMS simulado.' : '';
      if (!plan.rows.length) message.textContent = 'El PMS no devolvió habitaciones.';
    }

    async function go(start) {
      if (start) state.start = start;
      const token = ++state.token;
      message.textContent = 'Cargando el plano…';
      try {
        const data = await load(state.start, RANGE_DAYS);
        if (token !== state.token) return;
        state.data = data;
        render();
      } catch (error) {
        if (token !== state.token) return;
        message.textContent = error.status === 503
          ? 'El PMS no responde ahora. Reintenta en unos segundos.' : error.message;
      }
    }

    go();
    return {reload: () => go()};
  }

  /* ---------- dashboard ---------- */

  function dayChart(kpis) {
    const width = 560, height = 160, top = 12, bottom = 26, left = 30;
    const plotH = height - top - bottom;
    const slot = (width - left) / Math.max(kpis.perDay.length, 1);
    const chart = svg('svg', {viewBox: `0 0 ${width} ${height}`, class: 'occ-chart', role: 'img',
      'aria-label': `Ocupación por día, de ${formatDate(kpis.perDay[0].iso)} a ${formatDate(kpis.perDay[kpis.perDay.length - 1].iso)}`});
    for (const tick of [0, 50, 100]) {
      const y = top + plotH - (tick / 100) * plotH;
      chart.append(svg('line', {x1: left, x2: width, y1: y, y2: y, class: 'occ-grid-line'}));
      const label = svg('text', {x: left - 4, y: y + 3, class: 'occ-axis', 'text-anchor': 'end'});
      label.textContent = `${tick}%`;
      chart.append(label);
    }
    kpis.perDay.forEach((entry, index) => {
      const barH = (entry.pct / 100) * plotH;
      const x = left + index * slot + 3;
      const bar = svg('rect', {x, y: top + plotH - barH, width: Math.max(slot - 6, 2), height: barH, rx: 3, class: 'occ-col'});
      const tip = svg('title');
      tip.textContent = `${formatDate(entry.iso)}: ${entry.occupied} de ${kpis.total} (${entry.pct}%)`;
      bar.append(tip);
      chart.append(bar);
      const label = svg('text', {x: x + (slot - 6) / 2, y: height - 8, class: 'occ-axis', 'text-anchor': 'middle'});
      label.textContent = String(Number(entry.iso.slice(8)));
      chart.append(label);
    });
    return chart;
  }

  function mountDashboard(root, {onOpenPlan} = {}) {
    const S = window.DemoShared;
    const el = S.el;
    const message = el('p', 'occ-message', 'Cargando indicadores…');
    message.setAttribute('role', 'status');
    root.append(message);

    function tile(value, label) {
      const node = el('div', 'occ-kpi');
      node.append(el('b', '', value), el('span', '', label));
      return node;
    }

    function render(data) {
      const today = todayIso();
      const kpis = computeKpis(data, today);
      root.textContent = '';
      const head = el('div', 'occ-dash-head');
      head.append(el('h3', '', 'Resumen de hoy'));
      if (onOpenPlan) {
        const open = el('button', 'button-sm', 'Ver plano de ocupación');
        open.type = 'button';
        open.addEventListener('click', onOpenPlan);
        head.append(open);
      }
      const tiles = el('div', 'occ-kpis');
      tiles.append(
        tile(`${kpis.occupancyPct}%`, `ocupación hoy (${kpis.occupied} de ${kpis.total})`),
        tile(kpis.arrivals, 'llegadas hoy'),
        tile(kpis.departures, 'salidas hoy'),
        tile(kpis.inHouse, 'huéspedes en casa'),
        tile(`${kpis.bySource.ia} / ${kpis.bySource.personal}`, 'reservas IA / recepción')
      );
      const byDay = el('section', 'occ-block');
      byDay.append(el('h4', '', `Ocupación por día · próximos ${kpis.perDay.length} días`));
      if (kpis.perDay.length) byDay.append(dayChart(kpis));
      const table = el('details', 'occ-table');
      table.append(el('summary', '', 'Ver como tabla'));
      const body = el('table');
      const headRow = el('tr');
      for (const text of ['Día', 'Ocupadas', 'Ocupación']) headRow.append(el('th', '', text));
      body.append(headRow);
      for (const entry of kpis.perDay) {
        const row = el('tr');
        row.append(el('td', '', formatDate(entry.iso)), el('td', '', `${entry.occupied} de ${kpis.total}`), el('td', '', `${entry.pct}%`));
        body.append(row);
      }
      table.append(body);
      byDay.append(table);
      const byType = el('section', 'occ-block');
      byType.append(el('h4', '', 'Ocupación por tipo de habitación'));
      const list = el('ul', 'occ-types');
      for (const type of kpis.types) {
        const item = el('li');
        item.append(el('span', 'occ-type-name', `${type.short} · ${plural(type.units, 'unidad', 'unidades')}`));
        const track = el('span', 'occ-track');
        const fill = el('i');
        fill.style.width = `${type.pct}%`;
        track.append(fill);
        item.append(track, el('b', '', `${type.pct}%`));
        item.title = type.name;
        list.append(item);
      }
      byType.append(list);
      root.append(head, tiles, byDay, byType);
      if (data.simulated) root.append(el('p', 'occ-legend', 'Datos de prueba: PMS simulado.'));
    }

    async function reload() {
      try {
        render(await load(todayIso(), RANGE_DAYS));
      } catch (error) {
        root.textContent = '';
        const text = el('p', 'occ-message', error.status === 401 ? 'Identifícate para ver los indicadores.'
          : error.status === 503 ? 'El PMS no responde ahora: sin indicadores.' : error.message);
        text.setAttribute('role', 'alert');
        root.append(text);
      }
    }

    reload();
    return {reload};
  }

  /* ---------- montaje en la página ---------- */

  const byId = id => document.getElementById(id);

  // Recepción: «Solicitudes | Plano de ocupación». El plano usa la sesión que la bandeja ya tiene.
  function initReception() {
    const tabRequests = byId('inbox-tab-requests');
    const tabPlan = byId('inbox-tab-plan');
    const planBox = byId('occupancy-plan');
    if (!tabRequests || !tabPlan || !planBox) return;
    const body = document.querySelector('#inbox-view .inbox-body');
    let plan = null;
    let wanted = false;

    function show(planOn) {
      wanted = false;
      tabRequests.setAttribute('aria-pressed', String(!planOn));
      tabPlan.setAttribute('aria-pressed', String(planOn));
      planBox.hidden = !planOn;
      body.hidden = planOn;
      if (!planOn) return;
      if (plan) plan.reload(); else plan = mountPlan(planBox);
    }

    tabRequests.addEventListener('click', () => show(false));
    tabPlan.addEventListener('click', () => {
      if (window.DemoInbox.me()) { show(true); return; }
      wanted = true;
      window.DemoInbox.identify();
    });
    window.DemoInbox.onEnter(() => { if (wanted) show(true); });
  }

  // Administración: dashboard arriba. Sin sesión de demo pide identificarse; nunca crea otra ni pisa al operador.
  async function initAdmin() {
    const box = byId('admin-dashboard');
    if (!box) return;
    const S = window.DemoShared;
    let mounted = false;
    const mount = () => {
      if (mounted) return;
      mounted = true;
      box.textContent = '';
      mountDashboard(box, {onOpenPlan: () => {
        const view = document.querySelector('[data-view-option="recepcion"]');
        if (view) view.click();
        const tab = byId('inbox-tab-plan');
        if (tab) tab.click();
      }});
    };
    const ask = () => {
      box.textContent = '';
      const note = S.el('p', 'occ-message', 'Identifícate para ver los indicadores del hotel.');
      const login = S.el('button', 'button-sm primary', 'Identificarse');
      login.type = 'button';
      login.addEventListener('click', () => window.DemoInbox.identify());
      box.append(note, login);
    };
    window.DemoInbox.onEnter(mount);
    try {
      const session = await S.api('/api/demo/session', {staff: true});
      if (session && session.name) mount(); else ask();
    } catch (_) {
      ask();
    }
  }

  window.DemoOccupancy = {buildPlan, computeKpis, mountPlan, mountDashboard, initReception, initAdmin, todayIso};
})();
