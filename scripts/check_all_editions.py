"""Check every published field's editions; do not replace or deploy legal data."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import urlopen

from core.edition_watch import check, save
from core.fsc_collection import LawTransport
from core.fsc_credentials import law_api_key
from scripts.fetch_static_release import fetch

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_RELEASE = 'https://raw.githubusercontent.com/gschamisle/law-orbit/main/static-web-release.json'
PUBLIC_MANIFEST = 'https://gschamisle.github.io/law-orbit/manifest.json'


@contextmanager
def lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'check.lock'
    # Never terminate an existing job or remove somebody else's lock.
    handle = path.open('x', encoding='utf-8')
    try:
        handle.write(datetime.now(timezone.utc).isoformat())
        handle.close()
        yield
    finally:
        handle.close()
        path.unlink()


def run(site=None, output=None, metadata=None, workers=3):
    output = Path(output or ROOT / 'output/all-edition-checks').resolve()
    public = site is None and metadata is None
    metadata = Path(metadata or ROOT / 'static-web-release.json')
    try:
        with lock(output):
            try:
                if public:
                    # Local development branches can be ahead of the public
                    # site. Pin to main AND the live manifest before checking.
                    with urlopen(PUBLIC_RELEASE, timeout=40) as response:
                        spec = json.load(response)
                    with urlopen(PUBLIC_MANIFEST, timeout=40) as response:
                        live = json.load(response)
                    if live['version'] != spec['data_version']:
                        raise ValueError('Public deployment is still changing')
                    metadata = output / 'public-release.json'
                    save(metadata, spec)
                spec = json.loads(metadata.read_text(encoding='utf-8'))
                selected = Path(site) if site else output / 'sites' / spec['data_version']
                if not selected.exists():
                    fetch(metadata, selected)
                manifest = json.loads((selected / 'manifest.json').read_text(encoding='utf-8'))
                if manifest['version'] != spec['data_version']:
                    raise ValueError('Snapshot differs from the pinned public release')
                key = law_api_key()
                if not key:
                    raise ValueError('No API credential configured')
                return check(selected, LawTransport(key, attempts=3, timeout=40, reuse_connections=True),
                             output, workers=workers, progress=lambda s: print(s, flush=True))
            except Exception:
                failure_path = output / 'last-failure.json'
                latest_path = output / 'latest.json'
                def previous_time(path):
                    try:
                        return json.loads(path.read_text(encoding='utf-8')).get('checked_at', '')
                    except (OSError, ValueError):
                        return ''
                previous_failure = previous_time(failure_path)
                # An identical initialization failure is quiet until a later
                # successful check has recovered from it. Keep prior reports.
                notify = not previous_failure or previous_time(latest_path) > previous_failure
                result = dict(status='failed', reason='판본 점검을 완료하지 못했습니다. 인증 설정·네트워크·고정 공개 자료를 확인해 주세요.',
                              checked_at=datetime.now(timezone.utc).isoformat(), notification_needed=notify)
                save(failure_path, result)
                return result
    except FileExistsError:
        return dict(status='busy', reason='다른 점검 실행의 잠금을 보존했습니다.', notification_needed=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--site', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--metadata', type=Path)
    p.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    a = p.parse_args()
    result = run(a.site, a.output, a.metadata, a.workers)
    print(json.dumps({k: v for k, v in result.items() if k not in ('actionable', 'domains')}, ensure_ascii=False, indent=2))
    if result.get('status') == 'failed' or result.get('provider_failures'):
        raise SystemExit(1)
