"""Store local uploads under app-generated names, never client-supplied paths."""
from hashlib import sha256
from pathlib import Path, PureWindowsPath
import tempfile

from core.document_text import ExtractError, SUPPORTED

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def save_upload(uploaded, folder: Path) -> Path:
    name = str(uploaded.name)
    if (not name or any(ord(c) < 32 for c in name)
            or any(c in name for c in '/\\:') or PureWindowsPath(name).is_absolute()):
        raise ExtractError('파일 이름에는 경로나 제어 문자를 사용할 수 없습니다.')
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED:
        raise ExtractError('지원하지 않는 업로드 파일 형식입니다.')
    data = uploaded.getbuffer()
    if not 0 < len(data) <= MAX_UPLOAD_BYTES:
        raise ExtractError('빈 파일 또는 50MB를 넘는 파일은 올릴 수 없습니다.')
    folder = Path(folder)
    if folder.is_symlink():
        raise ExtractError('업로드 폴더는 바로가기일 수 없습니다.')
    folder.mkdir(parents=True, exist_ok=True)
    folder = folder.resolve()
    digest = sha256(data).hexdigest()
    target = folder / (digest + suffix)
    if target.is_symlink():
        raise ExtractError('업로드 저장 경로가 올바르지 않습니다.')
    if target.exists():
        if target.stat().st_size == len(data) and sha256(target.read_bytes()).hexdigest() == digest:
            return target
        raise ExtractError('기존 업로드 파일 검증에 실패했습니다.')
    # Same-content uploads can reuse conversion caches. Temporary files cannot
    # overwrite another file; replace never follows a destination symlink.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix='.upload-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
