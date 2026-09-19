'use strict';
/* Quiet, local synthesis. No audio files, network requests or autoplay. */
function createGalaxySound({root, button, slider, readout, volumeButton, env = globalThis}) {
  const notes = [293.665, 329.628, 369.994, 440, 493.883, 587.33];
  const voices = new Set();
  let context, master, filter, limiter, echo, feedback, wet;
  let wanted = false, visible = true, disposed = false, busy = false;
  let ambientTimer, suspendTimer, lastHover = null, lastNote = -Infinity;
  let lastTrail = {x: 0, y: 0, at: -Infinity};
  let volume = Math.min(.30, Math.max(0, Number(slider.value) / 100));
  const doc = root.ownerDocument;
  const volumePanel = slider.parentElement;
  let volumeTimer, volumeDragging = false;
  const now = () => env.performance.now();
  const audible = () => wanted && visible && !doc.hidden && !disposed && context?.state === 'running';
  const hash = text => [...String(text)].reduce((n, c) => (n * 31 + c.charCodeAt(0)) >>> 0, 0);

  function hideVolume(restoreFocus = false) {
    env.clearTimeout(volumeTimer); volumeTimer = undefined;
    volumePanel.hidden = true;
    volumeButton.setAttribute('aria-expanded', 'false');
    if (restoreFocus && doc.activeElement === slider) volumeButton.focus();
  }
  function scheduleVolumeHide() {
    env.clearTimeout(volumeTimer);
    if (!volumeDragging) volumeTimer = env.setTimeout(() => hideVolume(true), 3000);
  }
  function showVolume() {
    if (!wanted || !visible || doc.hidden || disposed) return;
    volumePanel.hidden = false;
    volumeButton.setAttribute('aria-expanded', 'true');
    scheduleVolumeHide();
  }
  function toggleVolume() {
    if (volumePanel.hidden) showVolume(); else hideVolume(true);
  }
  function startVolumeDrag() { volumeDragging = true; env.clearTimeout(volumeTimer); }
  function endVolumeDrag() {
    if (!volumeDragging) return;
    volumeDragging = false;
    if (!volumePanel.hidden) scheduleVolumeHide();
  }
  function volumeKey(event) {
    if (event.key === 'Escape') { event.preventDefault(); hideVolume(true); }
  }
  function display() {
    button.textContent = wanted ? '소리 끄기' : '소리 켜기';
    button.setAttribute('aria-pressed', String(wanted));
    volumeButton.hidden = !wanted;
    if (!wanted) hideVolume();
    readout.textContent = `${Math.round(volume * 100)}%`;
    root.dataset.soundState = wanted ? (audible() ? 'playing' : 'paused') : 'off';
  }
  function initialize() {
    const Audio = env.AudioContext || env.webkitAudioContext;
    if (!Audio) throw new Error('AudioContext unavailable');
    context = new Audio();
    master = context.createGain(); master.gain.value = 0;
    filter = context.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = 2600;
    limiter = context.createDynamicsCompressor();
    limiter.threshold.value = -18; limiter.knee.value = 12; limiter.ratio.value = 6;
    limiter.attack.value = .003; limiter.release.value = .25;
    filter.connect(master); master.connect(limiter); limiter.connect(context.destination);
    echo = context.createDelay(2); echo.delayTime.value = .29;
    feedback = context.createGain(); feedback.gain.value = .16;
    wet = context.createGain(); wet.gain.value = .18;
    filter.connect(echo); echo.connect(feedback); feedback.connect(echo);
    echo.connect(wet); wet.connect(master);
  }
  function note(frequency, delay = 0, strength = .055, duration = 1.5, pan = 0, attack = .035) {
    if (!audible() || volume === 0 || voices.size >= 8) return;
    const at = context.currentTime + delay;
    const envelope = context.createGain(), stereo = context.createStereoPanner();
    const fundamental = context.createOscillator(), harmonic = context.createOscillator(), shimmer = context.createGain();
    const voice = {envelope, nodes: [fundamental, harmonic, shimmer, envelope, stereo], oscillators: [fundamental, harmonic]};
    voices.add(voice);
    stereo.pan.value = Math.min(.7, Math.max(-.7, pan));
    envelope.gain.setValueAtTime(.00001, at);
    envelope.gain.exponentialRampToValueAtTime(strength, at + attack);
    envelope.gain.exponentialRampToValueAtTime(.00001, at + duration);
    fundamental.type = harmonic.type = 'sine';
    fundamental.frequency.value = frequency; harmonic.frequency.value = frequency * 2.002;
    shimmer.gain.value = .12;
    fundamental.connect(envelope); harmonic.connect(shimmer); shimmer.connect(envelope);
    envelope.connect(stereo); stereo.connect(filter);
    fundamental.onended = () => { voices.delete(voice); voice.nodes.forEach(n => n.disconnect()); };
    voice.oscillators.forEach(o => { o.start(at); o.stop(at + duration + .05); });
  }
  function ambient() {
    if (!audible()) return;
    const start = Math.floor(now() / 9000) % notes.length;
    note(notes[start], 0, .024, 5.5, -.35, 1.3);
    note(notes[(start + 3) % notes.length], 2.2, .018, 4.5, .35, 1.0);
    ambientTimer = env.setTimeout(ambient, 9000);
  }
  function silence() {
    hideVolume(); volumeDragging = false;
    env.clearTimeout(ambientTimer); ambientTimer = undefined;
    if (!context || context.state === 'closed') return;
    master.gain.cancelScheduledValues(context.currentTime);
    master.gain.setTargetAtTime(0, context.currentTime, .045);
    for (const voice of voices) {
      voice.envelope.gain.cancelScheduledValues(context.currentTime);
      voice.envelope.gain.setTargetAtTime(.00001, context.currentTime, .035);
      voice.oscillators.forEach(o => { try { o.stop(context.currentTime + .18); } catch {} });
    }
    env.clearTimeout(suspendTimer);
    suspendTimer = env.setTimeout(() => {
      if (!disposed && (!wanted || !visible || doc.hidden) && context.state !== 'closed') {
        context.suspend().catch(() => {});
      }
    }, 240);
  }
  async function synchronize() {
    if (!wanted || !visible || doc.hidden || disposed) { silence(); display(); return; }
    env.clearTimeout(suspendTimer);
    try {
      if (!context) initialize();
      await context.resume();
      // A user may leave the page while the browser processes the audio gesture.
      if (!wanted || !visible || doc.hidden || disposed) { silence(); display(); return; }
      if (context.state !== 'running') throw new Error('Audio gesture required');
      master.gain.cancelScheduledValues(context.currentTime);
      master.gain.setTargetAtTime(volume, context.currentTime, .16);
      if (ambientTimer === undefined) ambient();
      button.title = '낮은 바탕음과 별을 지날 때의 작은 반짝임 소리';
      display();
    } catch {
      wanted = false; silence(); display();
      root.dataset.soundState = 'unavailable';
      button.title = '소리를 시작하지 못했습니다. 브라우저의 소리 허용 상태를 확인해 주세요.';
    }
  }
  async function toggle() {
    if (busy || disposed) return;
    busy = true; wanted = !wanted;
    try { await synchronize(); if (wanted) showVolume(); } finally { busy = false; }
  }
  function setVolume() {
    volume = Math.min(.30, Math.max(0, Number(slider.value) / 100 || 0));
    if (audible()) master.gain.setTargetAtTime(volume, context.currentTime, .12);
    display(); showVolume();
  }
  function hover(id, x = .5) {
    if (!id) { lastHover = null; return; }
    if (!audible() || id === lastHover || now() - lastNote < 220) return;
    lastHover = id; lastNote = now();
    const n = hash(id) % notes.length;
    note(notes[n] * 2, 0, .065, 1.45, x * 1.2 - .6);
    note(notes[(n + 2) % notes.length] * 2, .11, .029, 1.65, x * 1.2 - .5);
  }
  function trail(x, y) {
    if (!audible() || now() - lastTrail.at < 1400 || Math.hypot(x - lastTrail.x, y - lastTrail.y) < .08) return;
    lastTrail = {x, y, at: now()};
    note(notes[Math.min(5, Math.floor(x * 6))] * 2, 0, .017, 1.8, x * 1.2 - .6, .12);
  }
  function setVisible(next) { visible = next; synchronize(); }
  function onVisibility() { synchronize(); }
  function dispose() {
    disposed = true; wanted = false; silence();
    env.clearTimeout(suspendTimer); env.clearTimeout(ambientTimer);
    observer?.disconnect();
    button.removeEventListener('click', toggle); slider.removeEventListener('input', setVolume);
    volumeButton.removeEventListener('click', toggleVolume);
    volumeButton.removeEventListener('keydown', volumeKey); slider.removeEventListener('keydown', volumeKey);
    slider.removeEventListener('pointerdown', startVolumeDrag);
    env.removeEventListener('pointerup', endVolumeDrag); env.removeEventListener('pointercancel', endVolumeDrag);
    doc.removeEventListener('visibilitychange', onVisibility); env.removeEventListener('pagehide', dispose);
    if (context && context.state !== 'closed') context.close().catch(() => {});
    display();
  }
  button.addEventListener('click', toggle); slider.addEventListener('input', setVolume);
  volumeButton.addEventListener('click', toggleVolume);
  volumeButton.addEventListener('keydown', volumeKey); slider.addEventListener('keydown', volumeKey);
  slider.addEventListener('pointerdown', startVolumeDrag);
  env.addEventListener('pointerup', endVolumeDrag); env.addEventListener('pointercancel', endVolumeDrag);
  doc.addEventListener('visibilitychange', onVisibility); env.addEventListener('pagehide', dispose);
  const observer = env.IntersectionObserver ? new env.IntersectionObserver(entries => {
    const entry = entries[entries.length - 1]; setVisible(entry.isIntersecting && entry.intersectionRatio > .02);
  }, {threshold: [0, .02]}) : null;
  observer?.observe(root);
  display();
  return {hover, trail, dispose, hideVolume};
}
if (typeof module !== 'undefined' && module.exports) module.exports = {createGalaxySound};
