/* Llamada de prueba del huésped: manos libres, como una llamada.
   El micrófono queda escuchando solo; cuando el huésped deja de hablar (una pausa corta) el turno se
   envía por el mismo chat y la respuesta se dice en voz alta con la voz de ElevenLabs (`/api/demo/tts`)
   o, si no está configurada, con la del navegador. Es una conversación por turnos: no hay audio en
   tiempo real ni interrupción a media frase, y no es una llamada telefónica. */
(() => {
  'use strict';
  const S = window.DemoShared;
  const $ = id => document.getElementById(id);
  const MAX_SPOKEN = 320;
  const SILENCE_MS = 1100;   // pausa que cierra el turno de quien habla
  const RESTART_MS = 250;    // respiro antes de volver a escuchar

  const config = window.COPILOTO_CONFIG || {};
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognitionSupported = Boolean(Ctor);
  const synth = window.speechSynthesis || null;

  let active = false;
  let listening = false;
  let muted = false;
  let speaking = false;
  let recognition = null;
  let audio = null;
  let transcript = '';
  let silenceTimer = 0;
  let restartTimer = 0;
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
    await new Promise(resolve => {
      audio.onended = resolve;
      audio.onerror = resolve;
    });
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

  function stopAudio() {
    speaking = false;
    if (audio) { try { audio.pause(); } catch (_) { /* nada */ } audio = null; }
    if (synth) synth.cancel();
  }

  // El asistente habla con el micrófono en pausa: sin esto se escucharía a sí mismo.
  async function say(text) {
    const spoken = speakable(text);
    if (!spoken) return;
    stopListening();
    speaking = true;
    setState('Hablando…');
    try {
      if (config.voice === true) await speakWithElevenLabs(spoken);
      else await speakWithBrowser(spoken);
    } catch (_) {
      // Si ElevenLabs falla, la llamada sigue con la voz del navegador: nunca queda muda.
      await speakWithBrowser(spoken);
    }
    speaking = false;
    if (!active) return;
    if (muted || !recognitionSupported) {
      setState(muted ? 'Micrófono en pausa' : 'Escribe abajo para responder');
      return;
    }
    beginListening();
  }

  function submit(said) {
    const text = String(said || '').trim();
    if (!text || !active) return;
    transcript = '';
    pushLine('guest', text);
    setState('Pensando…');
    window.DemoGuest?.send(text);
  }

  // Escucha continua: los resultados parciales se van juntando y una pausa corta cierra el turno.
  function beginListening() {
    if (!active || muted || listening || speaking || !recognitionSupported) return;
    if (!recognition) {
      recognition = new Ctor();
      recognition.lang = 'es-CL';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.onresult = event => {
        if (!active) return;
        let interim = '';
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const part = event.results[index][0]?.transcript || '';
          if (event.results[index].isFinal) transcript += ` ${part}`;
          else interim += part;
        }
        const pending = `${transcript} ${interim}`.trim();
        if (pending) {
          setState('Te escucho…', 'live');
          clearTimeout(silenceTimer);
          silenceTimer = setTimeout(() => {
            const said = `${transcript} ${interim}`.trim();
            clearTimeout(silenceTimer);
            if (said) { stopListening(); submit(said); }
          }, SILENCE_MS);
        }
      };
      recognition.onerror = event => {
        listening = false;
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          muted = true;
          setCallMic(false);
          setState('Sin permiso de micrófono: escribe abajo');
          return;
        }
        // «no-speech» y «aborted» son normales en una llamada: se reintenta al volver a escuchar.
        setState('Esperando tu voz…');
      };
      recognition.onend = () => {
        listening = false;
        if (!active || muted || speaking) return;
        clearTimeout(restartTimer);
        restartTimer = setTimeout(beginListening, RESTART_MS);
      };
    }
    try {
      recognition.start();
      listening = true;
      setState('Te escucho…', 'live');
    } catch (_) {
      // Si ya estaba activo el navegador lanza; se deja como estaba.
    }
  }

  function stopListening() {
    clearTimeout(silenceTimer);
    clearTimeout(restartTimer);
    if (recognition) { try { recognition.stop(); } catch (_) { /* nada */ } }
    listening = false;
  }

  function setCallMic(on) {
    const mic = $('guest-call-talk');
    if (mic) mic.dataset.state = on ? 'on' : 'off';
    const label = on ? 'Micrófono encendido: toca para silenciarlo' : 'Micrófono en pausa: toca para activarlo';
    if (mic) mic.setAttribute('aria-label', label);
  }

  function toggleMic() {
    if (!active || !recognitionSupported) return;
    muted = !muted;
    setCallMic(!muted);
    if (muted) { stopListening(); setState('Micrófono en pausa'); }
    else { setState('Te escucho…', 'live'); beginListening(); }
  }

  function open() {
    if (active) return;
    active = true;
    muted = false;
    transcript = '';
    startedAt = Date.now();
    log().replaceChildren();
    const composer = $('guest-call-form');
    if (composer) composer.hidden = true;
    const keyboard = $('guest-call-keyboard');
    if (keyboard) keyboard.textContent = 'Escribir en vez de hablar';
    panel().hidden = false;
    panel().setAttribute('aria-hidden', 'false');
    $('guest-call-toggle').setAttribute('aria-expanded', 'true');
    setCallMic(true);
    timer = setInterval(tick, 1000);
    tick();
    // La llamada arranca sola: el asistente saluda y, al terminar, el micrófono empieza a escuchar.
    say('Hola, soy el asistente virtual del hotel. ¿En qué te ayudo?');
  }

  function close() {
    if (!active) return;
    active = false;
    clearInterval(timer);
    stopListening();
    stopAudio();
    muted = false;
    transcript = '';
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
    $('guest-call-talk')?.addEventListener('click', toggleMic);
    const keyboard = $('guest-call-keyboard');
    const composer = $('guest-call-form');
    keyboard?.addEventListener('click', () => {
      const open = composer.hidden;
      composer.hidden = !open;
      keyboard.textContent = open ? 'Ocultar el teclado' : 'Escribir en vez de hablar';
      if (open) { stopListening(); $('guest-call-input')?.focus(); }
      else if (active && !muted) beginListening();
    });
    composer?.addEventListener('submit', event => {
      event.preventDefault();
      const input = $('guest-call-input');
      const text = String(input?.value || '').trim();
      if (!text) return;
      input.value = '';
      submit(text);
    });
    // Cuando el chat responde, la llamada lo dice en voz alta y vuelve a escuchar.
    const thread = $('guest-thread');
    if (thread && 'MutationObserver' in window) {
      const observer = new MutationObserver(() => {
        if (!active) return;
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
    toggle.hidden = false;
  }

  window.DemoVoice = {init, open, close, speakable, get active() { return active; }};
})();
