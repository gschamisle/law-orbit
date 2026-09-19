"""Allowlisted public-law snapshots; never package uploads, secrets or reports."""
from __future__ import annotations
import argparse
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
from urllib.parse import urlparse
import urllib.request

DOMAINS = ("tax", "procurement", "fsc", "housing", "environment")
BUNDLES = tuple(f"{domain}-universe/bundle.json" for domain in DOMAINS)
MANIFEST = "snapshot-manifest.json"
VERSION = re.compile(r"\d{8}-\d{6}")
LIMIT = 4 * 1024 ** 3


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_file(stream)


def sha256_file(stream) -> str:
    result = sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def allowed(name: str) -> bool:
    if name in BUNDLES or name == "local-tax-universe/current.json":
        return True
    return bool(re.fullmatch(
        r"local-tax-universe/versions/\d{8}-\d{6}/(?:central\.json|manifest\.json|(?:regions|reverse)/[a-f0-9]+\.json)", name))


def required_files(output: Path) -> list[str]:
    current = json.loads((output / "local-tax-universe/current.json").read_text(encoding="utf-8"))
    version = current.get("version", "")
    if current.get("domain") != "local_tax" or not VERSION.fullmatch(version):
        raise ValueError("Invalid local-tax current pointer")
    prefix = f"local-tax-universe/versions/{version}/"
    manifest = json.loads((output / (prefix + "manifest.json")).read_text(encoding="utf-8"))
    if manifest.get("domain") != "local_tax" or manifest.get("version") != version:
        raise ValueError("Local-tax manifest version mismatch")
    names = [*BUNDLES, "local-tax-universe/current.json", prefix + "manifest.json", prefix + "central.json"]
    for row in [*manifest.get("regions", []), *manifest.get("reverse_targets", [])]:
        if row.get("file"):
            names.append(prefix + row["file"])
    if len(names) != len(set(names)) or any(not allowed(n) for n in names):
        raise ValueError("Unexpected public-law snapshot paths")
    for name in names:
        path = output / name
        if not path.is_file() or path.is_symlink() or path.resolve().is_relative_to(output.resolve()) is False:
            raise ValueError("Missing or unsafe public-law snapshot file")
    return names


def complete(output: Path) -> bool:
    try:
        required_files(output)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def pack(output: Path, destination: Path) -> dict:
    names = required_files(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError("Snapshot destination already exists; choose a new filename")
    files = {}
    # Read each JSON once for validation and credential checks. No content is logged.
    from core.fsc_credentials import law_api_key
    keys = {os.environ.get(k, "") for k in ("LAW_API_KEY", "LAW_OC", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
    keys.add(law_api_key())
    for name in names:
        path = output / name
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        json.loads(text)
        if re.search(r"[?&](?:OC|LAW_API_KEY|api_key)=(?!REDACTED(?:[&\"\s<]|$))[^&\"\s<]+", text, re.I):
            raise ValueError("Snapshot contains a non-redacted authentication query")
        if any(key and key in text for key in keys):
            raise ValueError("Snapshot contains a configured credential")
        files[name] = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    manifest = {"schema": 1, "files": files}
    with tarfile.open(destination, "w:gz", compresslevel=6) as archive:
        blob = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        info = tarfile.TarInfo(MANIFEST); info.size = len(blob)
        archive.addfile(info, io.BytesIO(blob))
        for name in sorted(files):
            # Verify again to catch a collection update during packaging.
            path = output / name
            if digest(path) != files[name]["sha256"]:
                raise ValueError("Source changed while preparing snapshot; rebuild the package")
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0; info.uname = info.gname = ""; info.mode = 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    return {"archive": destination.name, "sha256": digest(destination),
            "files": len(files), "unpacked_bytes": sum(f["bytes"] for f in files.values()),
            "compressed_bytes": destination.stat().st_size}


def restore(archive_path: Path, output: Path, expected: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{64}", expected) or digest(archive_path) != expected:
        raise ValueError("Public-law archive checksum mismatch")
    if complete(output):
        return  # Never roll a newer, existing corpus back to the initial seed.
    targets = [*(f"{d}-universe" for d in DOMAINS), "local-tax-universe"]
    if any((output / name).exists() for name in targets):
        raise ValueError("Partial existing corpus: preserved; administrator recovery required")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-stage-", dir=output) as tmp:
        stage = Path(tmp)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > 5000 or sum(m.size for m in members) > LIMIT:
                raise ValueError("Archive exceeds public-law snapshot limits")
            names = [m.name for m in members]
            if len(names) != len(set(names)) or names.count(MANIFEST) != 1:
                raise ValueError("Duplicate or missing snapshot manifest")
            if any(not m.isfile() or not (m.name == MANIFEST or allowed(m.name)) for m in members):
                raise ValueError("Unexpected archive member (path or link)")
            info = archive.getmember(MANIFEST)
            if info.size > 2 * 1024 ** 2:
                raise ValueError("Snapshot manifest too large")
            manifest = json.load(archive.extractfile(info))
            if manifest.get("schema") != 1 or set(manifest["files"]) != set(names) - {MANIFEST}:
                raise ValueError("Snapshot inventory mismatch")
            for member in members:
                if member.name == MANIFEST:
                    continue
                record = manifest["files"][member.name]
                if member.size != record["bytes"]:
                    raise ValueError("Snapshot file size mismatch")
                path = stage / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if digest(path) != record["sha256"]:
                    raise ValueError("Snapshot file checksum mismatch")
        if set(required_files(stage)) != set(manifest["files"]):
            raise ValueError("Snapshot omits or adds active corpus files")
        moved = []
        try:
            for name in targets:
                if (output / name).exists():
                    raise ValueError("Corpus appeared during restoration; preserved")
                (stage / name).rename(output / name)
                moved.append(name)
        except BaseException:
            for name in reversed(moved):
                (output / name).rename(stage / name)
            raise
    (output / ".snapshot-installed.json").write_text(json.dumps({"sha256": expected}), encoding="utf-8")


def bootstrap(output: Path, url: str, expected: str) -> None:
    if complete(output):
        print("Public-law data ready (existing snapshot retained).", flush=True)
        return
    parsed = urlparse(url)
    # Seed packages are public release assets, with no credentials in the URL.
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.query or parsed.fragment
            or not parsed.path.startswith("/gschamisle/tax-amendment-assistant/releases/download/")
            or not re.fullmatch(r"[a-f0-9]{64}", expected)):
        raise ValueError("Set the public GitHub release URL and its SHA256 before first deploy")
    output.mkdir(parents=True, exist_ok=True)
    # Render runs one disk-attached instance. An exclusive file also prevents
    # accidental parallel bootstraps; stale locks are never deleted automatically.
    lock = output / ".snapshot-bootstrap.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    try:
        with tempfile.TemporaryDirectory(prefix=".snapshot-download-", dir=output) as tmp:
            archive = Path(tmp) / "laws.tar.gz"
            try:
                with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as dest:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > LIMIT:
                            raise ValueError("Snapshot download too large")
                        dest.write(chunk)
            except (OSError, ValueError):
                raise RuntimeError("Public-law snapshot download failed; check the release asset") from None
            restore(archive, output, expected)
    finally:
        lock.unlink()
    print("All six public-law corpora restored and verified.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "output")
    parser.add_argument("--archive", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(pack(args.output, args.archive), indent=2))


if __name__ == "__main__":
    main()
