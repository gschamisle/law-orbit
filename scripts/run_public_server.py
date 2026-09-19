"""Start the public, upload-free Streamlit app after restoring its law data."""
from __future__ import annotations
import os
from pathlib import Path
import sys

from scripts.galaxy_snapshot import bootstrap

ROOT = Path(__file__).resolve().parents[1]


def command(port: str) -> list[str]:
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("Invalid PORT")
    return [sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.address=0.0.0.0", "--server.port=" + port,
            "--server.headless=true", "--browser.gatherUsageStats=false",
            "--server.fileWatcherType=none", "--server.enableStaticServing=false"]


def main() -> None:
    # This entry point is deliberately always public/read-only, even if an
    # inherited optional-feature flag was set on the hosting account.
    os.environ["PUBLIC_GALAXY_ONLY"] = "1"
    for key in ("ENABLE_WIP_TABS", "ENABLE_DRAFT_TAB", "ENABLE_HWPX_OUTPUT"):
        os.environ[key] = "0"
    cmd = command(os.environ.get("PORT", "10000"))
    bootstrap(ROOT / "output", os.environ.get("GALAXY_SNAPSHOT_URL", ""),
              os.environ.get("GALAXY_SNAPSHOT_SHA256", ""))
    os.chdir(ROOT)
    os.execv(sys.executable, cmd)


if __name__ == "__main__":
    main()
