/* Presentation only: keep tab/session, chat, voice and queue ownership in their modules.
   Loaded after console.js so every journey follows the existing tab click path. */
(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const tabs = {
    huesped: get('tab-huesped'),
    recepcion: get('tab-recepcion'),
    admin: get('tab-admin')
  };
  function showView(view) {
    const tab = tabs[view];
    if (!tab) return;
    tab.click();
    tab.focus();
  }
  document.querySelectorAll('[data-demo-view]').forEach(button => {
    button.addEventListener('click', () => showView(button.dataset.demoView));
  });

  // demo.js owns hidden / aria-expanded / counts. Only reveal its closed ancestor;
  // never toggle the trace twice or open it automatically after a reply.
  get('toggle-actions')?.addEventListener('click', () => {
    const trace = get('actions-panel');
    const diagnostics = get('demo-diagnostics');
    if (trace && !trace.hidden && diagnostics) {
      diagnostics.open = true;
      trace.scrollIntoView({block: 'nearest'});
    }
  });

  function revealChannel() {
    showView('huesped');
    const channel = get('demo-channel');
    if (channel) channel.open = true;
  }
  document.querySelectorAll('a[href="#canal"]').forEach(anchor => {
    anchor.addEventListener('click', revealChannel);
  });
  // Also support pasted links and history navigation; no Chatwoot SDK side effects.
  const revealHash = () => { if (window.location.hash === '#canal') revealChannel(); };
  window.addEventListener('hashchange', revealHash);
  revealHash();

  const expand = get('admin-expand');
  const workspace = get('admin-console');
  if (expand && workspace) {
    expand.addEventListener('click', () => {
      const expanded = workspace.classList.toggle('is-expanded');
      expand.setAttribute('aria-expanded', String(expanded));
      expand.textContent = expanded ? 'Reducir PMS' : 'Ampliar PMS';
    });
  }
})();
