/* Orquesta /demo: qué vista se ve (partida, huésped o recepción), el escenario de turno y el arranque
   de cada rol. Con ?vista=huesped o ?vista=recepcion la página carga SOLO ese rol: así se presenta en
   dos ventanas, cada una con su credencial (el huésped nunca abre sesión de recepción). */
(() => {
  'use strict';
  const S = window.DemoShared;
  const $ = id => document.getElementById(id);
  const SHIFT_KEY = 'copiloto-demo-turno';
  const VIEWS = ['ambas', 'huesped', 'recepcion'];
  const started = {huesped: false, recepcion: false};
  let status = null;

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
    $('app-addr').textContent = `copiloto.bordeluz.demo · ${open ? 'recepción en turno' : 'fuera de turno'} · datos de prueba`;
  }

  function start(view) {
    if ((view === 'ambas' || view === 'huesped') && !started.huesped) {
      started.huesped = true;
      window.DemoGuest.init({status, shift: shiftScenario});
    }
    if ((view === 'ambas' || view === 'recepcion') && !started.recepcion) {
      started.recepcion = true;
      window.DemoInbox.init();
    }
  }

  function setView(view) {
    document.body.dataset.view = view;
    document.querySelectorAll('[data-view-option]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.viewOption === view));
    });
    if (status) start(view);
  }

  async function loadStatus() {
    try {
      status = await S.api('/api/demo/status');
    } catch (error) {
      $('shift-status').textContent = `${error.message} Comprueba que el servidor de la demo esté encendido.`;
      setTimeout(loadStatus, 5000);
      return;
    }
    describeShift();
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
