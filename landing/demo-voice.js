/* Llamada de prueba del huésped: reconoce la voz del navegador, envía el texto por el mismo chat y
   responde con la voz de ElevenLabs (`/api/demo/tts`) o, si no está configurada, con la del navegador.
   No es una llamada telefónica: no hay audio en tiempo real ni interrupción, se habla por turnos. */
(() => {
  'use strict';
  const S = window.DemoShared;
  const $ = id => document.getElementById(id);
  const MAX_SPOKEN = 320;

  const config = window.COPILOTO_CONFIG || {};
  const recognitionSupported = Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  const synth = window.speechSynthesis || null;

  let active = false;
  let listening = false;
  let recognition = null;
  let audio = null;
  let timer = 0;
  let startedAt = 0;

  const panel = () => $('guest-call');
  const state = () => $('call-state');
  const log = () => $('call-log');

  // Lo que se lee en voz alta: sin enlaces, sin listas y acotado (una llamada no lee un párrafo).
  function speakable(text) {
    return String(text || '')
      .replace(/https?:\/\/\S+/g, 'te lo envío por escrito')
      .replace(/[$]\s?(\d{1,3})(?:[.,](\d{3}))*/g, (_, first) => `${first} mil pesos`)
      .replace(/[*_`#]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, MAX_SPOKEN);
  }

  function setState(text, tone = '') {
    const el = state();
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone;
  }

  function pushLine(role, text) {
    const box = log();
    if (!box || !text) return;
    const line = document.createElement('p');
    line.className = role === 'guest' ? 'call-line guest' : 'call-line assistant';
    line.textContent = text;
    box.append(line);
    box.scrollTop = box.scrollHeight;
  }

  function tick() {
    if (!active) return;
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    const clock = $('call-clock');
    if (clock) clock.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }

  async function speakWithElevenLabs(text) {
    const response = await fetch('/api/demo/tts', {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({text, language: 'es'}),
    });
    if (!response.ok) throw new Error(`tts ${response.status}`);
    const blob = await response.blob();
    audio = new Audio(URL.createObjectURL(blob));
    await audio.play();
  }

  function speakWithBrowser(text) {
    if (!synth) return Promise.resolve();
    return new Promise(resolve => {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'es-CL';
      utterance.rate = 1.02;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      synth.speak(utterance);
    });
  }

  async function say(text) {
    const spoken = speakable(text);
    if (!spoken) return;
    setState('Hablando…');
    try {
      if (config.voice === true) await speakWithElevenLabs(spoken);
      else await speakWithBrowser(spoken);
    } catch (_) {
      // Si ElevenLabs falla, la llamada sigue con la voz del navegador: nunca queda muda.
      await speakWithBrowser(spoken);
    }
    if (active) setState(recognitionSupported ? 'Toca el micrófono para responder' : 'Escribe abajo para responder');
  }

  function stopAudio() {
    if (audio) { try { audio.pause(); } catch (_) { /* nada */ } audio = null; }
    if (synth) synth.cancel();
  }

  function listen() {
    if (!recognitionSupported || listening || !active) return;
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new Ctor();
    recognition.lang = 'es-CL';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    listening = true;
    setState('Escuchando…', 'live');
    recognition.onresult = event => {
      const said = String(event.results?.[0]?.[0]?.transcript || '').trim();
      listening = false;
      if (!said) { setState('No te escuché: toca el micrófono otra vez'); return; }
      pushLine('guest', said);
      setState('Pensando…');
      window.DemoGuest?.send(said);
    };
    recognition.onerror = () => { listening = false; setState('No pude usar el micrófono: escribe abajo'); };
    recognition.onend = () => { listening = false; };
    try { recognition.start(); } catch (_) { listening = false; setState('No pude usar el micrófono: escribe abajo'); }
  }

  function stopListening() {
    if (recognition) { try { recognition.stop(); } catch (_) { /* nada */ } recognition = null; }
    listening = false;
  }

  function open() {
    if (active) return;
    active = true;
    startedAt = Date.now();
    log().replaceChildren();
    const composer = $('guest-call-form');
    if (composer) composer.hidden = true;
    const keyboard = $('guest-call-keyboard');
    if (keyboard) keyboard.textContent = 'Escribir en vez de hablar';
    panel().hidden = false;
    panel().setAttribute('aria-hidden', 'false');
    $('guest-call-toggle').setAttribute('aria-expanded', 'true');
    setState(recognitionSupported ? 'Toca el micrófono y habla' : 'Este navegador no reconoce voz: escribe abajo');
    timer = setInterval(tick, 1000);
    tick();
    say('Hola, soy el asistente virtual del hotel. ¿En qué te ayudo?');
  }

  function close() {
    if (!active) return;
    active = false;
    clearInterval(timer);
    stopListening();
    stopAudio();
    recognition = null;
    panel().hidden = true;
    panel().setAttribute('aria-hidden', 'true');
    $('guest-call-toggle').setAttribute('aria-expanded', 'false');
    setState('');
    $('guest-call-toggle')?.focus();
  }

  function init() {
    const toggle = $('guest-call-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', () => (active ? close() : open()));
    $('guest-call-hangup')?.addEventListener('click', close);
    // «Escribir en vez de hablar»: el compositor aparece solo cuando hace falta, sin cargar la pantalla.
    const keyboard = $('guest-call-keyboard');
    const composer = $('guest-call-form');
    keyboard?.addEventListener('click', () => {
      const open = composer.hidden;
      composer.hidden = !open;
      keyboard.textContent = open ? 'Ocultar el teclado' : 'Escribir en vez de hablar';
      if (open) $('guest-call-input')?.focus();
    });
    $('guest-call-talk')?.addEventListener('click', () => (listening ? stopListening() : listen()));
    $('guest-call-form')?.addEventListener('submit', event => {
      event.preventDefault();
      const input = $('guest-call-input');
      const text = String(input?.value || '').trim();
      if (!text) return;
      input.value = '';
      pushLine('guest', text);
      setState('Pensando…');
      window.DemoGuest?.send(text);
    });
    // Cuando el chat responde, la llamada lo dice en voz alta.
    const thread = $('guest-thread');
    if (thread && 'MutationObserver' in window) {
      const observer = new MutationObserver(() => {
        if (!active) return;
        // Se lee la última respuesta completa: las burbujas «cont» son continuación de la anterior.
        const bubbles = thread.querySelectorAll('.chat-bubble.assistant');
        const last = bubbles[bubbles.length - 1];
        const text = last
          ? [...last.querySelectorAll('p')].map(p => p.textContent.trim()).filter(Boolean).join(' ')
          : '';
        if (!text || text === say.last) return;
        say.last = text;
        pushLine('assistant', text);
        say(text);
      });
      observer.observe(thread, {childList: true, subtree: true});
    }
    // Si la versión estática no tiene voz configurada, el botón igual sirve: usa la voz del navegador.
    toggle.hidden = false;
  }

  window.DemoVoice = {init, open, close, speakable, get active() { return active; }};
})();
