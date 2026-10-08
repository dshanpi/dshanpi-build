import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('repository_tool', ROOT / 'scripts/repository_tool.py')
repository = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository)


class LifecycleTests(unittest.TestCase):
    def test_withdraw_preserves_shared_dependencies_and_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            product = 'dshanpi-r1'
            config = ROOT / 'products' / product / 'product.json'
            manifests = root / 'catalog/releases' / product
            manifests.mkdir(parents=True)
            shared = dict(package='linux-image-vendor-rk35xx', version='1',
                          architecture='arm64', filename='pool/kernel.deb',
                          sha256='a' * 64, component=product)
            entries = [shared]
            for version in ('2026.10.08-1', '2026.10.08-2'):
                meta = dict(shared, package=product + '-release-core', version=version,
                            architecture='all', filename='pool/' + version + '.deb')
                entries.append(meta)
                (manifests / (version + '.json')).write_text(json.dumps(dict(
                    product=product, version=version, suite='noble-testing', packages=[shared, meta])))
            catalog = root / 'catalog/suites/noble-testing' / (product + '.tsv')
            repository.write_catalog(catalog, entries)
            args = argparse.Namespace(repository=root, config=config, version='2026.10.08-1')
            repository.withdraw_release(args)
            remaining = repository.read_catalog(catalog)
            self.assertEqual({repository.identity(x) for x in remaining},
                             {repository.identity(entries[0]), repository.identity(entries[2])})
            with self.assertRaisesRegex(SystemExit, 'withdrawn'):
                repository.promote_release(args)


if __name__ == '__main__':
    unittest.main()
