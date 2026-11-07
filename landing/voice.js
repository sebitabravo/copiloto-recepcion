(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const panel = get('voice-demo');
  if (!panel) return;
  const config = window.COPILOTO_CONFIG || {};
  const copilotoUrl = config.copilotoUrl || 'http://localhost:8100';
  // demo.js carga antes y expone el resolutor de la demo: en una visita por LAN reescribe
  // localhost al host de la página (con su protocolo) para que el panel de voz no apunte al
  // propio equipo del visitante. Sin resolutor disponible, la URL cruda es el respaldo.
  const resolver = window.resolveDemoUrl || (value => String(value));
  const baseUrl = resolver(copilotoUrl).replace(/\/+$/, '');
  const sessionKey = 'bordeluz-demo-session';
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const log = get('voice-log');
  const stateLabel = get('voice-state');
  const talk = get('voice-talk');
  const langSelect = get('voice-lang');
  const LANG_CODES = {es: 'es-CL', en: 'en-US'};
  const currentLang = () => (langSelect && langSelect.value === 'en' ? 'en' : 'es');
  const typed = get('voice-form');
  const typedInput = get('voice-typed-input');
  let inCall = false;
  let busy = false;
  let listening = false;
  let recognition = null;
  let audio = null;
  let callVersion = 0;
  let pending = null;
  let settlePlayback = null;
  let timerId = 0;
  let startedAt = 0;
  function tickTimer() {
    const label = get('call-timer');
    if (!label) return;
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    label.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }
  function startTimer() { startedAt = Date.now(); tickTimer(); window.clearInterval(timerId); timerId = window.setInterval(tickTimer, 1000); }
  function stopTimer() { window.clearInterval(timerId); timerId = 0; }

  function create(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }
  function sessionId() {
    try {
      const stored = window.sessionStorage.getItem(sessionKey);
      if (stored && /^[A-Za-z0-9-]{16,64}$/.test(stored)) return stored;
    } catch (_) { /* Sin almacenamiento: se usa un id propio de esta llamada. */ }
    if (!sessionId.fallback) sessionId.fallback = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : `voz-${Date.now()}-${Math.random().toString(16).slice(2)}`.padEnd(16, '0');
    return sessionId.fallback;
  }
  function setState(text) { stateLabel.textContent = text; }
  function addLine(who, text, className = '') {
    const item = create('li', `voice-line ${className}`.trim());
    item.append(create('strong', '', who), create('span', '', text));
    log.append(item);
    log.scrollTop = log.scrollHeight;
  }
  function updateControls() {
    get('voice-start').hidden = inCall;
    get('voice-hangup').hidden = !inCall;
    talk.hidden = !inCall || !Recognition;
    typed.hidden = !inCall;
    talk.disabled = busy;
    typedInput.disabled = busy;
    talk.textContent = listening ? 'Escuchando… toca para enviar' : 'Tocar para hablar';
    talk.setAttribute('aria-pressed', String(listening));
  }
  const canSpeakBrowser = Boolean(window.speechSynthesis && window.SpeechSynthesisUtterance);
  function stopAudio() {
    if (audio) { audio.pause(); audio = null; }
    if (canSpeakBrowser) window.speechSynthesis.cancel();
    if (settlePlayback) { settlePlayback(); settlePlayback = null; }
  }
  // Voz del navegador: sin costo y sin servidor. Si el navegador no avisa el fin, un tiempo de seguridad libera la espera.
  function speakBrowser(text, language) {
    return new Promise(resolve => {
      stopAudio();
      settlePlayback = resolve;
      const utterance = new SpeechSynthesisUtterance(text);
      // Chileno primero; después latinoamericano; la voz castellana solo como último recurso
      const wanted = language === 'en' ? ['en-US', 'en'] : ['es-CL', 'es-MX', 'es-419', 'es-US', 'es'];
      const voices = window.speechSynthesis.getVoices();
      const voice = wanted
        .map(code => voices.find(item => item.lang.replace('_', '-').toLowerCase().startsWith(code.toLowerCase())))
        .find(Boolean);
      utterance.lang = language === 'en' ? 'en-US' : 'es-CL';
      if (voice) utterance.voice = voice;
      utterance.rate = 0.95;
      const safety = window.setTimeout(resolve, Math.max(4000, text.length * 90));
      utterance.onend = () => { window.clearTimeout(safety); resolve(); };
      utterance.onerror = () => { window.clearTimeout(safety); resolve(); };
      window.speechSynthesis.speak(utterance);
    });
  }
  function play(base64, format) {
    return new Promise(resolve => {
      stopAudio();
      settlePlayback = resolve;
      const mime = format === 'wav' ? 'audio/wav' : 'audio/mpeg';
      audio = new Audio(`data:${mime};base64,${base64}`);
      audio.addEventListener('ended', resolve, {once:true});
      audio.addEventListener('error', resolve, {once:true});
      audio.play().catch(resolve);
    });
  }
  async function request(path, body, controller) {
    const timer = window.setTimeout(() => controller.abort(), 60000);
    try {
      const response = await fetch(baseUrl + path, {method:body === undefined ? 'GET' : 'POST', credentials:'omit',
        cache:'no-store', signal:controller.signal,
        ...(body === undefined ? {} : {headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw {status:response.status, message:data.detail || 'La voz no está disponible ahora.'};
      return data;
    } catch (error) {
      if (error && error.status) throw error;
      throw {status:0, message:'No pudimos conectar con el asistente. Revisa que el servidor esté encendido.'};
    } finally { window.clearTimeout(timer); }
  }
  async function speakReply(data, version) {
    addLine('Asistente virtual', data.reply);
    (data.events || []).filter(event => event && event.type === 'handoff')
      .forEach(() => addLine('Sistema', 'Se avisó a una persona de recepción (simulado).', 'system'));
    const spokenText = data.spoken || data.reply;
    const language = data.spoken_language || data.language || currentLang();
    if (data.audio_b64) {
      setState('Hablando…');
      await play(data.audio_b64, data.audio_format);
    } else if (canSpeakBrowser && spokenText) {
      setState('Hablando (voz del navegador)…');
      await speakBrowser(spokenText, language);
    } else if (data.voice_error) {
      addLine('Sistema', 'Sin audio por ahora: puedes leer la respuesta.', 'system');
    }
    if (version === callVersion) setState('Tu turno: toca para hablar o escribe abajo.');
  }
  async function send(text) {
    const message = text.trim();
    if (!message || busy || !inCall) return;
    // Mismo límite del simulador: se rechaza en lugar de truncar en silencio.
    if (message.length > 400) {
      addLine('Sistema', 'El mensaje debe tener 400 caracteres o menos.', 'system');
      setState('Mensaje demasiado largo. Acórtalo e intenta de nuevo.');
      return;
    }
    const version = callVersion;
    const controller = new AbortController();
    pending = controller;
    busy = true;
    addLine('Tú', message, 'guest');
    setState('Pensando…');
    updateControls();
    try {
      const data = await request('/api/demo/voice', {session_id:sessionId(), message}, controller);
      if (version === callVersion) await speakReply(data, version);
    } catch (error) {
      if (version === callVersion) {
        addLine('Sistema', error.message || 'No se pudo enviar el mensaje.', 'system');
        setState('Hubo un problema. Intenta de nuevo.');
      }
    } finally {
      if (version === callVersion) { busy = false; updateControls(); }
    }
  }
  function listen() {
    if (!Recognition || busy) return;
    if (listening) { recognition.stop(); return; }
    stopAudio();
    recognition = new Recognition();
    recognition.lang = LANG_CODES[currentLang()];
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.addEventListener('result', event => {
      const transcript = event.results[0] && event.results[0][0] ? event.results[0][0].transcript : '';
      send(transcript);
    });
    recognition.addEventListener('error', event => {
      const reason = event.error === 'not-allowed' ? 'Permite el micrófono en el navegador para hablar.' :
        (event.error === 'no-speech' ? 'No te escuché. Intenta de nuevo.' : 'No pude reconocer la voz. Puedes escribir abajo.');
      addLine('Sistema', reason, 'system');
    });
    recognition.addEventListener('end', () => { listening = false; updateControls(); });
    try {
      recognition.start();
    } catch (_) {
      // Un arranque fallido no puede dejar la UI clavada en “Escuchando…”.
      recognition = null;
      listening = false;
      setState('No se pudo activar el micrófono. Intenta de nuevo o escribe abajo.');
      updateControls();
      return;
    }
    listening = true;
    setState('Escuchando…');
    updateControls();
  }
  async function startCall() {
    inCall = true;
    if (panel) panel.hidden = false;
    startTimer();
    callVersion += 1;
    const version = callVersion;
    log.replaceChildren();
    const controller = new AbortController();
    pending = controller;
    busy = true;
    setState('Conectando…');
    updateControls();
    // El botón que tenía el foco se ocultó: se lleva el foco a colgar para no perderlo en el body.
    const hangupButton = get('voice-hangup');
    if (hangupButton) hangupButton.focus();
    try {
      const data = await request(`/api/demo/voice/greeting?lang=${currentLang()}`, undefined, controller);
      if (version === callVersion) {
        await speakReply({reply:data.text, spoken:data.text, language:data.language, audio_b64:data.audio_b64,
          voice_error:data.voice_error}, version);
      }
    } catch (error) {
      if (version === callVersion) {
        addLine('Sistema', error.message, 'system');
        setState('No se pudo conectar. Cuelga e intenta de nuevo.');
      }
    } finally {
      if (version === callVersion) { busy = false; updateControls(); }
    }
  }
  function hangUp() {
    callVersion += 1;
    inCall = false;
    stopTimer();
    if (panel) panel.hidden = true;
    busy = false;
    if (pending) { pending.abort(); pending = null; }
    if (recognition && listening) recognition.abort();
    stopAudio();
    setState('Llamada terminada.');
    updateControls();
    const startButton = get('voice-start');
    if (startButton) startButton.focus();
  }

  get('voice-start').addEventListener('click', startCall);
  get('voice-hangup').addEventListener('click', hangUp);
  talk.addEventListener('click', listen);
  typed.addEventListener('submit', event => {
    event.preventDefault();
    const text = typedInput.value;
    typedInput.value = '';
    send(text);
  });

  fetch(`${baseUrl}/api/demo/status`, {credentials:'omit', cache:'no-store'})
    .then(response => response.json())
    .then(status => {
      if (status.voice !== true) {
        // Sin voz configurada el icono sigue disponible: la pantalla de llamada explicará el estado real.
        get('voice-support').hidden = true;
        return;
      }
      get('voice-support').hidden = Boolean(Recognition);
      updateControls();
    })
    .catch(() => { /* Sin servidor, el panel de voz no se muestra. */ });
})();
