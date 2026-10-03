"""The allowlist fails closed without importing unreviewed or live-AI tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_test_inventory as inventory
from scripts import run_offline_tests as runner


def registry():
    return {'schema': 1, 'suites': {
        'offline': ['scripts/test_fixture.py', 'scripts/test_browser.mjs'],
        'collected': ['scripts/test_corpus.py'],
        'api_local': [inventory.MANUAL_ONLY],
    }, 'dependencies': {
        'scripts/test_corpus.py': 'Separately collected local snapshot',
        inventory.MANUAL_ONLY: 'External AI and local private draft; manual only',
    }}


class TestInventoryTests(unittest.TestCase):
    def test_current_checkout_has_no_unclassified_or_missing_test(self):
        inventory.checked_registry()

    def test_discovery_reports_new_python_and_node_without_importing_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / 'scripts'
            scripts.mkdir()
            data = registry()
            for name in [n for paths in data['suites'].values() for n in paths]:
                (root / name).write_text('raise RuntimeError("must never import")', encoding='utf-8')
            for name in ('test_unreviewed.py', 'test_unreviewed.cjs'):
                (scripts / name).write_text('raise RuntimeError("must never import")', encoding='utf-8')
            (scripts / 'test_suites.json').write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unclassified test') as error:
                inventory.checked_registry(root)
            self.assertIn('test_unreviewed.py', str(error.exception))
            self.assertIn('test_unreviewed.cjs', str(error.exception))

    def test_missing_duplicate_and_invalid_paths_are_rejected(self):
        data = registry()
        discovered = {name for paths in data['suites'].values() for name in paths}
        self.assertEqual(inventory.inventory_errors(data, discovered), [])
        self.assertTrue(any('does not exist' in error for error in
                            inventory.inventory_errors(data, discovered - {'scripts/test_fixture.py'})))
        duplicate = copy.deepcopy(data)
        duplicate['suites']['collected'].append('scripts/test_fixture.py')
        self.assertTrue(any('Duplicate' in error for error in inventory.inventory_errors(duplicate, discovered)))
        unsafe = copy.deepcopy(data)
        unsafe['suites']['offline'].append('../test_elsewhere.py')
        self.assertTrue(any('invalid test path' in error for error in inventory.inventory_errors(unsafe, discovered)))

    def test_live_ai_cannot_be_reclassified_as_offline(self):
        data = registry()
        data['suites']['api_local'] = []
        data['suites']['offline'].append(inventory.MANUAL_ONLY)
        discovered = {name for paths in data['suites'].values() for name in paths}
        self.assertTrue(any('must remain api_local' in error for error in
                            inventory.inventory_errors(data, discovered)))

    def test_collected_and_private_dependencies_must_be_documented(self):
        data = registry()
        data['dependencies'] = {}
        discovered = {name for paths in data['suites'].values() for name in paths}
        errors = inventory.inventory_errors(data, discovered)
        self.assertEqual(sum('dependency note' in error for error in errors), 2)

    def test_runner_uses_only_explicit_offline_entries(self):
        data = registry()
        self.assertEqual(runner.offline_paths(data, 'python'), ['scripts/test_fixture.py'])
        self.assertEqual(runner.offline_paths(data, 'node'), ['scripts/test_browser.mjs'])
        with patch.object(runner, 'checked_registry', return_value=data), \
             patch.object(runner.subprocess, 'run') as run:
            self.assertEqual(runner.main(['--only', inventory.MANUAL_ONLY]), 1)
            self.assertEqual(runner.main(['--only', 'scripts/test_corpus.py']), 1)
            run.assert_not_called()

    def test_inventory_error_prevents_all_execution(self):
        with patch.object(runner, 'checked_registry', side_effect=ValueError('unclassified')), \
             patch.object(runner.subprocess, 'run') as run:
            self.assertEqual(runner.main([]), 1)
            run.assert_not_called()

    def test_missing_node_fails_instead_of_passing_or_skipping(self):
        with patch.object(runner, 'checked_registry', return_value=registry()), \
             patch.object(runner.shutil, 'which', return_value=None), \
             patch.object(runner.subprocess, 'run') as run:
            self.assertEqual(runner.main(['--runtime', 'node']), 1)
            run.assert_not_called()

    def test_list_mode_never_launches_a_test(self):
        with patch.object(runner, 'checked_registry', return_value=registry()), \
             patch.object(runner.subprocess, 'run') as run:
            self.assertEqual(runner.main(['--list']), 0)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
