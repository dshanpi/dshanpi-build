import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('repository_optional', ROOT / 'scripts/repository_tool.py')
repository = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository)


class OptionalPackagesTests(unittest.TestCase):
    def exercise(self, extras, enabled=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / 'a1/product.json'
            config_path.parent.mkdir()
            config = dict(schema_version=1, product='a1', testing_suite='noble-testing',
                          component='a1', common_packages=[], forbidden_package_patterns=[],
                          required_packages=[dict(name='kernel', arch='arm64')],
                          release_meta=dict(core='a1-release-core', desktop='a1-release-desktop'))
            if enabled:
                config['optional_package_sets'] = {'axcl': [dict(name=p, arch='arm64') for p in ('runtime', 'driver', 'axcl')]}
            config_path.write_text(json.dumps(config))
            packages = root / 'packages'
            packages.mkdir()
            for name in ['kernel', 'a1-release-core', 'a1-release-desktop', *extras]:
                (packages / (name + '.deb')).write_bytes(name.encode())
            def fields(path):
                name = path.stem
                return dict(Package=name, Version='2026.10.09-2', Architecture='all' if '-release-' in name else 'arm64')
            args = argparse.Namespace(repository=root / 'repository', packages=packages,
                                      config=config_path, version='2026.10.09-2')
            with patch.object(repository, 'deb_fields', side_effect=fields):
                repository.add_release(args)
            result = json.loads((args.repository / 'catalog/releases/a1/2026.10.09-2.json').read_text())
            return {p['package'] for p in result['packages']}

    def test_base_release_does_not_require_optional_hardware(self):
        self.assertEqual(len(self.exercise([])), 3)

    def test_complete_optional_set_is_indexed(self):
        self.assertEqual(len(self.exercise(['runtime', 'driver', 'axcl'])), 6)

    def test_partial_optional_set_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, 'incomplete'):
            self.exercise(['runtime'])

    def test_other_board_cannot_publish_unconfigured_hardware(self):
        with self.assertRaisesRegex(SystemExit, 'unexpected'):
            self.exercise(['runtime', 'driver', 'axcl'], enabled=False)

    def test_unlisted_package_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, 'unexpected'):
            self.exercise(['unreviewed'])
