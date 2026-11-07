/* Chrome de la landing de marketing (/): revelado de secciones, barra fija y progreso de lectura.
   El simulador vive en /demo y sigue cargando demo.js + voice.js; esta página no los necesita.
   Sin dependencias: usa solo lo que ya estaba en la página. */
(() => {
  'use strict';

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
