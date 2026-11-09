/* Chrome de la landing de marketing (/): revelado de secciones, barra fija y progreso de lectura.
   El simulador vive en /demo y sigue cargando demo.js + voice.js; esta página no los necesita.
   Sin dependencias: usa solo lo que ya estaba en la página. */
(() => {
  'use strict';

  // Enlaces a los servicios de la demo (bandeja, PMS, métricas): salen de config.js, que genera
  // scripts/seed-chatwoot.sh. Sin config se derivan del host de la página con los puertos del stack;
  // sin JS quedan apuntando a la consola /demo, que también los enlaza.
  const config = window.COPILOTO_CONFIG || {};
  const pageHost = port => `${location.protocol}//${location.hostname}:${port}`;
  const trim = value => String(value).replace(/\/+$/, '');
  // Demo por LAN: misma regla que demo.js. Si la página no corre en localhost pero la config sí
  // apunta ahí, se usa el host y el protocolo de la página conservando puerto y ruta.
  const resolve = raw => {
    try {
      const url = new URL(raw, location.href);
      const local = host => host === 'localhost' || host === '127.0.0.1';
      if (!local(location.hostname) && local(url.hostname)) {
        url.hostname = location.hostname;
        url.protocol = location.protocol;
      }
      return url.toString();
    } catch (_) { return null; }
  };
  const copiloto = trim(config.copilotoUrl || pageHost(8100));
  // Publicado sin backend (`staticDemo`, lo escribe el build estático) no hay PMS ni métricas a los
  // que saltar: esos enlaces se quedan en la consola /demo, que es donde la versión estática explica
  // qué sí y qué no está disponible. Solo el sitio servido con el stack completo usa los puertos.
  const staticDemo = config.staticDemo === true;
  // La bandeja de recepción es /demo?vista=recepcion (enlace fijo); Chatwoot solo existe con el stack completo.
  const services = staticDemo ? {} : {
    pms: `${trim(config.pmsUrl || pageHost(8200))}/admin`,
    metrics: `${copiloto}/metricas`,
  };
  document.querySelectorAll('a[data-service]').forEach(link => {
    const href = services[link.dataset.service] && resolve(services[link.dataset.service]);
    if (href && /^https?:/.test(href)) link.href = href;
    else if (staticDemo) {
      // Sin servicio no se abre una pestaña: el enlace lleva a la consola, en la misma pestaña.
      link.removeAttribute('target');
      link.removeAttribute('rel');
    }
  });

  // Barra fija: borde y progreso de lectura cuando la página ya se desplazó.
  const topbar = document.getElementById('topbar');
  const progress = document.getElementById('scroll-progress');
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

  // Revelado suave de las secciones de marketing: mismo selector y clases que en la página de la demo.
  if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
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
})();
