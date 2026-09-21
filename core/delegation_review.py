"""Local draft comparison through the same engine used in the public reader."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compare(before, after, *, meta, new_article=False, deleted_article=False, before_date='', after_date=''):
    node = shutil.which('node')
    if not node:
        raise ValueError('로컬 위임 비교에는 Node.js 22 이상이 필요합니다. 공개 수집 자료 열람은 브라우저에서 사용할 수 있습니다.')
    payload = dict(before=before, after=after, options=dict(meta=meta, newArticle=new_article,
                   deletedArticle=deleted_article, beforeDate=before_date, afterDate=after_date))
    try:
        result = subprocess.run([node, str(ROOT / 'scripts/delegation_review_bridge.mjs')],
            input=json.dumps(payload, ensure_ascii=False), text=True, encoding='utf-8',
            capture_output=True, timeout=20, cwd=ROOT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        raise ValueError('로컬 비교 시간이 초과됐습니다. 조문 한 개의 본문인지 확인해 주세요.') from None
    try:
        response = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError('로컬 비교 엔진을 실행하지 못했습니다.') from None
    if not response.get('ok'):
        raise ValueError(response.get('error', '입력 조문을 확인해 주세요.'))
    return response['result']
