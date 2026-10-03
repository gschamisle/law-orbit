"""Check explicit test classification without importing or running test files.

Discovery only finds omissions. It never adds discovered files to a run list.
Edit test_suites.json after reviewing a new test's data and network dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ('offline', 'collected', 'api_local')
SUFFIXES = {'.py', '.mjs', '.cjs'}
MANUAL_ONLY = 'scripts/test_llm_review_golden.py'


def discovered_tests(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix()
            for path in (root / 'scripts').rglob('*')
            if path.is_file() and path.suffix in SUFFIXES
            and path.name.startswith(('test_', 'smoke_'))}


def inventory_errors(registry: dict, discovered: set[str]) -> list[str]:
    errors = []
    if registry.get('schema') != 1:
        errors.append('Unsupported test registry schema')
    suites = registry.get('suites', {})
    if not isinstance(suites, dict) or set(suites) != set(GROUPS):
        return errors + ['Expected offline, collected and api_local test groups']
    classified = {}
    for group in GROUPS:
        paths = suites[group]
        if not isinstance(paths, list):
            errors.append(f'{group}: expected an explicit list')
            continue
        for name in paths:
            if not isinstance(name, str):
                errors.append(f'{group}: non-string test path')
                continue
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts or '\\' in name
                    or len(path.parts) < 2 or path.parts[0] != 'scripts'
                    or path.suffix not in SUFFIXES
                    or not path.name.startswith(('test_', 'smoke_'))):
                errors.append(f'{group}: invalid test path {name}')
                continue
            if name in classified:
                errors.append(f'Duplicate classification: {name} ({classified[name]}, {group})')
            classified[name] = group
            if name == MANUAL_ONLY and group != 'api_local':
                errors.append(f'External AI/private-input test must remain api_local: {name}')
    errors.extend(f'Registered test does not exist: {name}'
                  for name in sorted(set(classified) - discovered))
    errors.extend(f'Unclassified test (review before running): {name}'
                  for name in sorted(discovered - set(classified)))
    dependencies = registry.get('dependencies', {})
    if not isinstance(dependencies, dict):
        errors.append('Expected test dependency notes')
        dependencies = {}
    for name, group in classified.items():
        if group != 'offline' and not str(dependencies.get(name, '')).strip():
            errors.append(f'Missing {group} dependency note: {name}')
    errors.extend(f'Dependency note has no classified test: {name}'
                  for name in sorted(set(dependencies) - set(classified)))
    return errors


def checked_registry(root: Path = ROOT) -> dict:
    registry = json.loads((root / 'scripts/test_suites.json').read_text(encoding='utf-8'))
    errors = inventory_errors(registry, discovered_tests(root))
    if errors:
        raise ValueError('\n'.join(errors))
    return registry


def main() -> int:
    try:
        registry = checked_registry()
    except (OSError, ValueError) as error:
        print(f'Test inventory check failed:\n{error}', file=sys.stderr)
        return 1
    counts = ', '.join(f'{group}={len(registry["suites"][group])}' for group in GROUPS)
    print(f'Test inventory classified: {counts}. No tests were imported or run.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
