"""Run only explicitly reviewed offline tests; never discover tests for execution."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from scripts.check_test_inventory import ROOT, checked_registry


def offline_paths(registry: dict, runtime: str) -> list[str]:
    suffixes = {'.py'} if runtime == 'python' else {'.mjs', '.cjs'}
    return [name for name in registry['suites']['offline'] if Path(name).suffix in suffixes]


def command(name: str, node: str | None = None) -> list[str]:
    if name.endswith('.py'):
        return [sys.executable, '-B', '-X', 'utf8', '-m', name[:-3].replace('/', '.')]
    if not node:
        raise ValueError('Node.js is required for the registered offline browser tests')
    return [node, '--test', name]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('python', 'node'), default='python')
    parser.add_argument('--list', action='store_true', help='Print the reviewed run list without running it')
    parser.add_argument('--only', action='append', default=[], metavar='scripts/test_name.py',
                        help='Run only a named entry from the selected offline list; repeat as needed')
    args = parser.parse_args(argv)
    try:
        registry = checked_registry()
        paths = offline_paths(registry, args.runtime)
        unknown = set(args.only) - set(paths)
        if unknown:
            raise ValueError('Not a registered offline test for this runtime: ' + ', '.join(sorted(unknown)))
        if args.only:
            paths = [name for name in paths if name in args.only]
        if args.list:
            print('\n'.join(paths))
            return 0
        node = shutil.which('node') if args.runtime == 'node' else None
        commands = [(name, command(name, node)) for name in paths]
    except (OSError, ValueError) as error:
        print(f'Offline test selection failed:\n{error}', file=sys.stderr)
        return 1

    suites = registry['suites']
    print(f'Offline {args.runtime} suite: {len(commands)} explicitly registered commands.', flush=True)
    print(f'Not scheduled: collected={len(suites["collected"])}, api_local={len(suites["api_local"])}.', flush=True)
    print('Optional corpus cases report explicit skips in their own test results.\n', flush=True)
    failed = []
    for name, invocation in commands:
        print(f'--- {name} ---', flush=True)
        result = subprocess.run(invocation, cwd=ROOT)
        if result.returncode:
            failed.append(name)
    if failed:
        print(f'FAILED ({len(failed)}/{len(commands)}): ' + ', '.join(failed), file=sys.stderr)
        return 1
    print(f'OFFLINE COMMANDS COMPLETED ({len(commands)}); see individual results for skipped cases.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
