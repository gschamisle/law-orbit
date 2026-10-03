'use strict';
// Shared by the embedded galaxy and the self-contained HTML download.
function createGalaxyGestures({
  canvas,
  getZoom,
  onZoom,
  onRotate,
  onTap,
  onHover,
  onLeave,
  onActive,
  enabled = true,
  env = globalThis,
}) {
  enabled = Boolean(enabled);
  const points = new Map();
  let distance = null,
    multiple = false;
  const clamp = (value) => Math.max(0.4, Math.min(2.8, value));
  const local = (e) => {
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const separation = () => {
    const [a, b] = points.values();
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : null;
  };
  function down(e) {
    if (!enabled) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    const p = local(e);
    points.set(e.pointerId, { ...p, ox: p.x, oy: p.y, moved: false });
    canvas.setPointerCapture(e.pointerId);
    if (points.size > 1) multiple = true;
    distance = separation();
    onActive(true);
    onLeave();
  }
  function move(e) {
    if (!enabled) return;
    const next = local(e),
      p = points.get(e.pointerId);
    if (!p) {
      if (e.pointerType !== 'touch' && !points.size) onHover(next.x, next.y);
      return;
    }
    const dx = next.x - p.x,
      dy = next.y - p.y;
    Object.assign(p, next);
    p.moved ||= Math.hypot(p.x - p.ox, p.y - p.oy) >= 6;
    if (points.size > 1) {
      const current = separation();
      if (distance > 0 && current > 0) onZoom(clamp((getZoom() * current) / distance));
      distance = current;
    } else onRotate(dx, dy);
  }
  function end(e, cancelled = false) {
    if (!enabled) return;
    const p = points.get(e.pointerId);
    if (!p) return;
    const next = local(e);
    const tap = !cancelled && !multiple && !p.moved && Math.hypot(next.x - p.ox, next.y - p.oy) < 6;
    points.delete(e.pointerId);
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    distance = separation();
    if (!points.size) {
      multiple = false;
      onActive(false);
    }
    if (tap) onTap(next.x, next.y);
  }
  const up = (e) => end(e),
    cancel = (e) => end(e, true);
  function clear() {
    const ids = [...points.keys()];
    points.clear();
    distance = null;
    multiple = false;
    for (const id of ids) if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id);
    onActive(false);
    onLeave();
  }
  function setEnabled(value) {
    enabled = Boolean(value);
    if (!enabled) clear();
  }
  const leave = () => {
    if (enabled) onLeave();
  };
  const wheel = (e) => {
    if (!enabled) return;
    e.preventDefault();
    onZoom(clamp(getZoom() * Math.exp(-e.deltaY * 0.001)));
  };
  const events = {
    pointerdown: down,
    pointermove: move,
    pointerup: up,
    pointercancel: cancel,
    lostpointercapture: cancel,
    pointerleave: leave,
    wheel,
  };
  for (const [type, handler] of Object.entries(events))
    canvas.addEventListener(type, handler, type === 'wheel' ? { passive: false } : undefined);
  env.addEventListener('blur', clear);
  return {
    setEnabled,
    clear,
    dispose() {
      clear();
      for (const [type, handler] of Object.entries(events))
        canvas.removeEventListener(type, handler);
      env.removeEventListener('blur', clear);
    },
  };
}

// Inline touch maps begin in page-scroll mode; interaction is an explicit choice.
function createGalaxyTouchMode({
  root,
  canvas,
  button,
  hint,
  gestures,
  env = globalThis,
  doc = env.document,
}) {
  const media = env.matchMedia('(pointer: coarse)'),
    cleanups = [];
  let interactive = false,
    buttonVisible = true,
    disposed = false;
  function render() {
    const touch = media.matches,
      active = touch && interactive;
    root.dataset.touchMode = touch ? (active ? 'interact' : 'scroll') : 'desktop';
    button.hidden = !touch;
    button.textContent = active ? '조작 종료' : '지도 조작';
    button.setAttribute(
      'aria-label',
      active ? '지도 조작 종료, 페이지 스크롤로 돌아가기' : '지도 조작',
    );
    button.title = active ? '페이지 스크롤로 돌아가기' : '지도 회전·확대·조문 선택';
    button.setAttribute('aria-pressed', String(active));
    hint.hidden = !touch;
    hint.textContent = active
      ? '지도 조작 중 · 한 손가락 회전, 두 손가락 확대'
      : '화면을 밀어 스크롤 · 지도를 움직이려면 지도 조작';
    canvas.tabIndex = touch && !active ? -1 : 0;
    canvas.setAttribute(
      'aria-label',
      touch
        ? active
          ? '지도 조작 중. 한 손가락으로 회전, 두 손가락으로 확대·축소. 조작 종료 버튼으로 페이지 스크롤로 돌아갑니다.'
          : '법령 연결 지도. 화면을 밀어 스크롤합니다. 지도를 움직이려면 지도 조작 버튼을 누르세요.'
        : '드래그로 회전, 스크롤로 확대·축소. 방향키로 회전, 더하기와 빼기로 확대. 법령 선택 목록으로도 탐색할 수 있습니다.',
    );
    gestures.setEnabled(!touch || active);
  }
  function reset() {
    if (disposed) return;
    interactive = false;
    gestures.clear();
    render();
  }
  function toggle() {
    if (disposed || !media.matches || (!interactive && !buttonVisible)) return;
    interactive = !interactive;
    render();
  }
  function keydown(e) {
    if (e.key !== 'Escape' || !media.matches || !interactive) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    reset();
    button.focus();
  }
  function listen(target, type, handler, options) {
    target.addEventListener(type, handler, options);
    cleanups.push(() => target.removeEventListener(type, handler, options));
  }
  listen(button, 'click', toggle);
  listen(doc, 'keydown', keydown, true);
  listen(env, 'blur', reset);
  listen(env, 'pagehide', reset);
  listen(doc, 'visibilitychange', () => {
    if (doc.hidden) reset();
  });
  listen(doc, 'fullscreenchange', reset);
  if (media.addEventListener) listen(media, 'change', reset);
  else {
    media.addListener(reset);
    cleanups.push(() => media.removeListener(reset));
  }
  if (env.IntersectionObserver) {
    const observer = new env.IntersectionObserver(
      (entries) => {
        if (disposed) return;
        for (const entry of entries) {
          if (entry.target !== button) continue;
          buttonVisible = entry.isIntersecting && entry.intersectionRatio >= 0.75;
          if (media.matches && interactive && !buttonVisible) reset();
        }
      },
      { threshold: [0, 0.75, 1] },
    );
    observer.observe(button);
    cleanups.push(() => observer.disconnect());
  }
  render();
  return {
    dispose() {
      if (disposed) return;
      reset();
      disposed = true;
      for (const cleanup of cleanups) cleanup();
    },
  };
}
if (typeof module !== 'undefined' && module.exports)
  module.exports = { createGalaxyGestures, createGalaxyTouchMode };
