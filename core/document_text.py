"""문서 → 텍스트 단일 진입점. 확장자에 따라 추출기를 고른다.

`hwp_reader.extract_text`는 이름 그대로 HWP 계열만 다룬다. 그런데 화면과 CLI가
`.pdf`도 받는다고 안내하면서 그 함수를 부르고 있었다 — PDF를 넣으면 조용히
빈 문자열이 돌아와 "개정문 본문을 찾지 못했습니다"만 뜬다. 입법예고 자료는
대부분 PDF라 사실상 업로드가 통째로 막혀 있었다.

PDF는 kordoc으로 Markdown을 거친다. 다른 추출기를 쓰면 줄바꿈·표 구조가 달라져
`pdf_bill_text.unwrap()` 이하 파서의 거동이 CLI와 어긋난다 — 지금까지 검토 결과가
전부 kordoc 변환본 위에서 나왔으므로 같은 경로를 쓰는 게 맞다.

변환본은 원본 옆에 `.kordoc.md`로 캐시한다. 같은 파일을 다시 올려도 재변환하지
않는다(조특법안 기준 변환에 수십 초 걸린다).
"""
from __future__ import annotations

import shutil
import subprocess
import json
import tempfile
from pathlib import Path

PLAIN_SUFFIXES = frozenset({".md", ".txt"})
HWP_SUFFIXES = frozenset({".hwpx", ".hwp", ".hml"})
PDF_SUFFIXES = frozenset({".pdf"})
SUPPORTED = PLAIN_SUFFIXES | HWP_SUFFIXES | PDF_SUFFIXES

_CACHE_SUFFIX = ".kordoc.md"
_KORDOC_VERSION = "4.19.0"
_KORDOC_DIR = Path(__file__).resolve().parents[1] / "tools/document-converter/node_modules/kordoc"
_PDF_TIMEOUT = 180


class ExtractError(RuntimeError):
    """추출 실패 — 왜 실패했는지 사용자에게 그대로 보여주기 위한 예외."""


def kordoc_available() -> bool:
    return _converter_command() is not None


def _converter_command() -> list[str] | None:
    """Use a locked, already installed JS entrypoint; never run npm/npx on input."""
    node = shutil.which("node")
    if not node or Path(node).suffix.lower() in ('.cmd', '.bat', '.ps1'):
        return None
    try:
        package = json.loads((_KORDOC_DIR / 'package.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    entry = _KORDOC_DIR / 'dist/cli.js'
    if package.get('version') != _KORDOC_VERSION or not entry.is_file():
        return None
    return [str(Path(node).resolve()), str(entry.resolve())]


def pdf_to_markdown(path: Path, *, force: bool = False) -> Path:
    """PDF → Markdown (kordoc). 변환본 경로를 돌려준다."""
    cache = path.with_suffix(path.suffix + _CACHE_SUFFIX)
    if cache.is_file() and not force and cache.stat().st_mtime >= path.stat().st_mtime:
        return cache

    if not kordoc_available():
        raise ExtractError(
            "고정 버전 PDF 변환기 kordoc이 필요합니다 (Node.js). 프로젝트 폴더에서 "
            "`npm ci --prefix tools/document-converter --ignore-scripts`를 실행하거나 HWPX 파일을 올려 주세요."
        )
    command = _converter_command()
    if command is None:
        raise ExtractError('PDF 변환기 설치 상태가 바뀌었습니다. 다시 확인해 주세요.')
    # Never expose a partially written conversion as a valid cache after a
    # timeout/failure. Absolute paths cannot be interpreted as CLI options.
    try:
        with tempfile.TemporaryDirectory(prefix='.pdf-convert-', dir=path.resolve().parent) as folder:
            output = Path(folder) / 'converted.md'
            done = subprocess.run(
                [*command, str(path.resolve()), '-o', str(output), '--silent'],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                shell=False, timeout=_PDF_TIMEOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            if done.returncode != 0 or not output.is_file():
                raise ExtractError('PDF 변환에 실패했습니다. 파일 형식·암호 보호 여부를 확인해 주세요.')
            output.replace(cache)
    except subprocess.TimeoutExpired as exc:
        raise ExtractError('PDF 변환 제한 시간(180초)을 넘었습니다.') from exc
    return cache


def extract(path: str | Path, *, force: bool = False) -> str:
    """어떤 지원 형식이든 텍스트로. 실패하면 ExtractError를 던진다(조용히 빈 문자열 X)."""
    p = Path(path)
    suffix = p.suffix.lower()
    if not p.is_file():
        raise ExtractError(f"파일이 없습니다: {p}")

    if suffix in PLAIN_SUFFIXES:
        return p.read_text(encoding="utf-8", errors="replace")

    if suffix in PDF_SUFFIXES:
        return pdf_to_markdown(p, force=force).read_text(encoding="utf-8", errors="replace")

    if suffix in HWP_SUFFIXES:
        from core.hwp_reader import extract_text

        text = extract_text(p)
        if len(text) < 100:
            raise ExtractError(
                f"{p.name} 에서 본문을 거의 뽑지 못했습니다 "
                "(암호 보호·DRM 문서이거나 형식이 다를 수 있습니다)."
            )
        return text

    raise ExtractError(
        f"지원하지 않는 형식입니다: {suffix or '(확장자 없음)'} — "
        f"지원: {', '.join(sorted(s.lstrip('.') for s in SUPPORTED))}"
    )
