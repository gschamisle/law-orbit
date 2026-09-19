"""Run this checkout locally, reusing a local credential only in this process."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from core.fsc_credentials import law_api_key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8503)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('invalid port')
    key = law_api_key()
    env = {**os.environ, 'PYTHONUTF8':'1'}
    if key:
        env['LAW_API_KEY'] = key
    return subprocess.call([sys.executable, '-m', 'streamlit', 'run', 'app.py',
                            '--server.address', '127.0.0.1', '--server.port', str(args.port),
                            '--browser.gatherUsageStats', 'false', '--server.headless', 'true'],
                           cwd=Path(__file__).resolve().parents[1], env=env)


if __name__ == '__main__':
    raise SystemExit(main())
