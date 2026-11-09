/* Administración en /demo: abre solo el PMS configurado, nunca una copia simulada de sus escrituras.
   /admin?demo=1 deja que el servidor valide DEMO_MODE y cree su cookie HttpOnly; no usamos tokens. */
(() => {
  'use strict';
  const config = window.COPILOTO_CONFIG || {};
  const $ = id => document.getElementById(`admin-${id}`);
  let initialized = false;
  let reachable = false;
  let opened = false;

  function pmsBase() {
    if (typeof config.pmsUrl !== 'string' || !config.pmsUrl.trim()) return null;
    try {
      const url = new URL(window.DemoShared.resolveUrl(config.pmsUrl));
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null;
      return url.toString().replace(/\/+$/, '');
    } catch (_) { return null; }
  }

  async function check(base) {
    reachable = false;
    opened = false;
    $('frame').hidden = true;
    $('frame').removeAttribute('src');
    $('open').hidden = true;
    $('retry').disabled = true;
    $('status').textContent = 'Viendo si el servicio PMS de prueba responde…';
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      // PMS no expone CORS. Una respuesta opaca prueba conectividad, NO autenticación ni DEMO_MODE.
      const response = await fetch(`${base}/health`, {method: 'GET', mode: 'no-cors', credentials: 'omit',
        cache: 'no-store', redirect: 'follow', signal: controller.signal});
      if (response.type !== 'opaque' && !response.ok) throw new Error('unavailable');
      reachable = true;
      $('open').hidden = false;
      $('status').textContent = 'El servicio responde. Abre el PMS de prueba para que el servidor valide el acceso demo, sin introducir credenciales.';
    } catch (_) {
      $('status').textContent = 'El servicio de Administración/PMS no está disponible. Enciende el PMS de prueba y reintenta. Este panel no simula reservas.';
    } finally {
      clearTimeout(timer);
      $('retry').disabled = false;
    }
  }

  function init() {
    if (initialized) return;
    initialized = true;
    if (config.staticDemo) {
      $('status').textContent = 'Administración/PMS no disponible en esta versión estática. No hay servicio de administración: aquí no se crean ni se guardan reservas.';
      return;
    }
    const base = pmsBase();
    if (!base) {
      $('status').textContent = 'El servicio de Administración/PMS no está configurado. No se crean ni se guardan reservas desde esta vista.';
      return;
    }
    $('retry').hidden = false;
    $('retry').addEventListener('click', () => check(base));
    $('open').addEventListener('click', () => {
      if (!reachable || opened) return;
      opened = true;
      $('frame').src = `${base}/admin?demo=1`;
      $('frame').hidden = false;
      $('status').textContent = 'El PMS valida el modo demo en su servidor. Si muestra un error o pide credenciales, el acceso demo no está disponible; no introduzcas tokens. Las acciones del PMS no se vinculan con la corrida del chat.';
    });
    check(base);
  }

  window.DemoAdmin = {init};
})();
