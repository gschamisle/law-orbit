// A public, approximate page-view counter. Never send reading/search state.
const PUBLIC_ORIGIN = 'https://gschamisle.github.io';
const PUBLIC_PATHS = new Set(['/law-orbit/', '/law-orbit/index.html']);
const BADGE =
  'https://hits.sh/gschamisle.github.io/law-orbit.svg?label=누적%20조회&color=9ed8c5&labelColor=092c28&style=flat';
const mounted = new WeakSet();

export function counterURL(href, { online = true, topLevel = true } = {}) {
  let url;
  try {
    url = new URL(href);
  } catch {
    return '';
  }
  if (!online || !topLevel || url.origin !== PUBLIC_ORIGIN || !PUBLIC_PATHS.has(url.pathname))
    return '';
  return BADGE;
}

export function mountPageviews(
  container,
  { href = location.href, online = navigator.onLine, topLevel = window.top === window.self } = {},
) {
  if (!container || mounted.has(container)) return;
  mounted.add(container);
  const src = counterURL(href, { online, topLevel });
  container.title =
    '도입 이후 공개 앱을 연 누적 횟수의 참고 지표입니다. 새로고침은 포함하고 분야·조문 전환은 더하지 않습니다. 고유 방문자 수는 아닙니다.';
  if (!src) {
    container.textContent = online ? '누적 조회 · 공개판에서 집계' : '누적 조회 · 오프라인';
    return;
  }
  const badge = container.ownerDocument.createElement('img');
  badge.alt = '누적 조회수';
  badge.height = 20;
  badge.referrerPolicy = 'no-referrer';
  // A slow or blocked service must not block the app or display a made-up zero.
  container.textContent = '누적 조회 · 불러오는 중';
  const timeout = setTimeout(() => {
    container.textContent = '누적 조회 · 연결 대기';
  }, 8000);
  badge.onload = () => {
    clearTimeout(timeout);
    container.replaceChildren(badge);
  };
  badge.onerror = () => {
    clearTimeout(timeout);
    container.textContent = '누적 조회 · 집계 연결 안 됨';
  };
  badge.src = src;
}
