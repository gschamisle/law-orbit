// Reports contain only explicitly selected public metadata, never location/search/storage.
export const REPORT_TYPES = ['잘못된 연결', '빠진 조문·연결', '본문·시행일', '화면·동작', '기타'];
const clean = (value, max = 140) =>
  String(value || '')
    .replace(/[\x00-\x1f\x7f]/g, ' ')
    .slice(0, max)
    .trim();
export function reportContext({
  domain = '',
  law = '',
  reference = '',
  effective = '',
  version = '',
  builtAt = '',
  relatedLaw = '',
  relatedReference = '',
} = {}) {
  return Object.fromEntries(
    Object.entries({
      분야: clean(domain),
      법령: clean(law),
      조문: clean(reference),
      시행일: clean(effective, 12),
      '자료 판본': clean(version, 50),
      '수집 기준': clean(builtAt, 30),
      '열람 중인 연결 법령': clean(relatedLaw),
      '열람 중인 연결 조문': clean(relatedReference),
    }).filter(([, v]) => v),
  );
}
export function makeReport(type, description, context) {
  if (!REPORT_TYPES.includes(type)) throw Error('신고 유형을 선택해 주세요.');
  const message = String(description || '').trim();
  if (message.length < 5) throw Error('어떤 문제가 있었는지 5자 이상 적어 주세요.');
  if (message.length > 1200) throw Error('내용은 1,200자 이내로 적어 주세요.');
  const allowed = [
    '분야',
    '법령',
    '조문',
    '시행일',
    '자료 판본',
    '수집 기준',
    '열람 중인 연결 법령',
    '열람 중인 연결 조문',
  ];
  const fields = allowed
    .filter((k) => context[k])
    .map((k) => `- ${k}: ${clean(context[k])}`)
    .join('\n');
  const title =
    `[오류 신고] ${type} · ${clean(context.법령 || context.분야 || '법의 궤도', 65)} ${clean(context.조문, 25)}`.trim();
  const body = `## 문제 내용\n${message}\n\n## 확인 위치\n${fields || '- 선택된 법령 없음'}\n\n앱: https://gschamisle.github.io/law-orbit/\n\n---\n공개 법령 자료·화면에 대한 신고입니다. 연결 누락 여부와 법적 판단은 별도로 확인해야 합니다.`;
  const url = new URL('https://github.com/gschamisle/law-orbit/issues/new');
  url.searchParams.set('title', title);
  url.searchParams.set('body', body);
  return {
    title,
    body,
    url: url.href.length > 7400 ? 'https://github.com/gschamisle/law-orbit/issues/new' : url.href,
    copyRequired: url.href.length > 7400,
  };
}
export function installFeedback(getContext) {
  const $ = (id) => document.getElementById(id),
    dialog = $('feedback');
  let context = {};
  const refresh = () => {
    try {
      const report = makeReport($('feedback-type').value, $('feedback-description').value, context);
      $('feedback-send').href = report.url;
      $('feedback-send').removeAttribute('aria-disabled');
      $('feedback-status').textContent = report.copyRequired
        ? '내용이 길어 자동 채우기를 생략합니다. 신고 내용을 복사한 뒤 GitHub 작성 화면에 붙여 넣어 주세요.'
        : 'GitHub에서 내용을 확인한 뒤 제출합니다.';
      return report;
    } catch (error) {
      $('feedback-send').removeAttribute('href');
      $('feedback-send').setAttribute('aria-disabled', 'true');
      $('feedback-status').textContent = error.message;
      return null;
    }
  };
  const open = () => {
    context = reportContext(getContext());
    $('feedback-context').textContent =
      Object.entries(context)
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n') || '선택된 법령 없음';
    $('feedback-description').value = '';
    $('feedback-preview').hidden = true;
    refresh();
    dialog.showModal();
  };
  $('feedback-open').onclick = open;
  $('reading-report').onclick = open;
  $('feedback-type').replaceChildren(
    ...REPORT_TYPES.map((type) => {
      const option = document.createElement('option');
      option.value = type;
      option.textContent = type;
      return option;
    }),
  );
  $('feedback-type').onchange = refresh;
  $('feedback-description').oninput = refresh;
  $('feedback-send').onclick = (event) => {
    if (!refresh()) event.preventDefault();
  };
  $('feedback-copy').onclick = async () => {
    const report = refresh();
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report.title + '\n\n' + report.body);
      $('feedback-status').textContent = '신고 내용을 복사했습니다.';
    } catch {
      $('feedback-status').textContent =
        '자동 복사가 제한되었습니다. 아래 내용을 선택해 복사해 주세요.';
      $('feedback-preview').textContent = report.title + '\n\n' + report.body;
      $('feedback-preview').hidden = false;
    }
  };
}
