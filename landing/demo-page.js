/* Orquesta /demo: qué vista se ve (partida, huésped, recepción o administración), el turno y el arranque
   de cada rol. Con ?vista=huesped o ?vista=recepcion la página carga SOLO ese rol: así se presenta en
   dos ventanas, cada una con su credencial (el huésped nunca abre sesión de recepción). */
(() => {
  'use strict';
  const S = window.DemoShared;
  const $ = id => document.getElementById(id);
  const SHIFT_KEY = 'copiloto-demo-turno';
  const VIEWS = ['ambas', 'huesped', 'recepcion', 'admin'];
  const started = {huesped: false, recepcion: false, admin: false};
  let status = null;
  let run = null;

  /* Corrida de esta presentación: la emite el servidor. Va en la URL (?corrida=), así una recarga o «Abrir … en
     otra ventana» siguen en la MISMA corrida, y otra presentación (otra corrida) no ve estos casos. */
  async function ensureRun() {
    const params = new URLSearchParams(location.search);
    const asked = params.get('corrida');
    let notice = '';
    if (asked && /^[A-Za-z0-9_-]{16,32}$/.test(asked)) {
      try {
        await S.api(`/api/demo/run/${encodeURIComponent(asked)}`);
        return {id: asked, notice};
      } catch (error) {
        if (error.status !== 404) throw error;
        notice = 'La corrida del enlace venció: empezamos una nueva.';
      }
    }
    const created = await S.api('/api/demo/run', {method: 'POST'});
    params.set('corrida', created.run);
    try { history.replaceState(null, '', `${location.pathname}?${params}${location.hash}`); } catch (_) { /* */ }
    return {id: created.run, notice};
  }

  function linkWindows() {
    document.querySelectorAll('a[href*="vista="]').forEach(link => {
      try {
        const url = new URL(link.getAttribute('href'), location.href);
        url.searchParams.set('corrida', run);
        link.href = url.pathname + url.search;
      } catch (_) { /* el enlace queda como estaba */ }
    });
  }

  function initialView() {
    const asked = new URLSearchParams(location.search).get('vista');
    if (VIEWS.includes(asked)) return asked;
    // En un teléfono la vista partida no cabe: arranca en el chat, con el selector a mano.
    return window.matchMedia('(max-width: 760px)').matches ? 'huesped' : 'ambas';
  }

  function shiftScenario() { return $('shift-scenario').value; }

  function describeShift() {
    const box = $('shift-status');
    if (!status) return;
    const shift = status.shift;
    const scenario = shiftScenario();
    const open = scenario ? scenario === 'open' : shift.in_shift;
    const hours = `${shift.start}–${shift.end}, hora de Chile`;
    box.textContent = '';
    const label = S.el('b', '', open ? 'Recepción en turno' : 'Recepción fuera de turno');
    box.append(label, document.createTextNode(open
      ? ` · ${hours}. La meta de primera respuesta es de 3 minutos.`
      : ` · ${hours}. Las solicitudes quedan guardadas; responde desde las ${shift.next_opening}.`));
    if (scenario) box.append(document.createTextNode(' (simulado para esta sesión)'));
    // La barra del marco, como en el hero de la portada: dirección y estado del turno.
    const tag = run ? ` · corrida ${run.slice(0, 6)}` : '';
    $('app-addr').textContent = `copiloto.bordeluz.demo · ${open ? 'recepción en turno' : 'fuera de turno'}${tag} · datos de prueba`;
  }

  function start(view) {
    if (view === 'admin' && !started.admin) {
      started.admin = true;
      window.DemoAdmin.init();
    }
    if ((view === 'ambas' || view === 'huesped') && !started.huesped) {
      started.huesped = true;
      window.DemoGuest.init({status, shift: shiftScenario});
      window.DemoVoice?.init();
    }
    if ((view === 'ambas' || view === 'recepcion') && !started.recepcion) {
      started.recepcion = true;
      window.DemoInbox.init();
    }
  }

  function setView(view) {
    document.body.dataset.view = view;
    $('guest-view').hidden = view !== 'ambas' && view !== 'huesped';
    $('inbox-view').hidden = view !== 'ambas' && view !== 'recepcion';
    $('admin-view').hidden = view !== 'admin';
    document.querySelectorAll('[data-view-option]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.viewOption === view));
    });
    // Administración no depende de que el servidor del chat esté encendido.
    if (status || view === 'admin') start(view);
  }

  async function loadStatus() {
    let notice = '';
    try {
      status = await S.api('/api/demo/status');
      const current = await ensureRun();
      run = current.id;
      notice = current.notice;
    } catch (error) {
      status = null;
      $('shift-status').textContent = `${error.message} Comprueba que el servidor de la demo esté encendido.`;
      setTimeout(loadStatus, 5000);
      return;
    }
    S.setRun(run);
    linkWindows();
    describeShift();
    if (notice) $('shift-status').append(document.createTextNode(` ${notice}`));
    start(document.body.dataset.view);
  }

  function init() {
    const saved = S.store.get('sessionStorage', SHIFT_KEY);
    if (saved === 'open' || saved === 'closed') $('shift-scenario').value = saved;
    $('shift-scenario').addEventListener('change', () => {
      S.store.set('sessionStorage', SHIFT_KEY, shiftScenario());
      describeShift();
    });
    document.querySelectorAll('[data-view-option]').forEach(button => {
      button.addEventListener('click', () => setView(button.dataset.viewOption));
    });
    setView(initialView());
    loadStatus();
  }

  init();
})();
