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

    def test_purge_removes_legacy_manifests_and_only_unreferenced_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            product = 'dshanpi-r1'
            config = ROOT / 'products' / product / 'product.json'
            suite = 'noble-testing'
            component = product
            manifests = root / 'catalog/releases' / product
            manifests.mkdir(parents=True)
            pool = root / 'pool' / component
            pool.mkdir(parents=True)
            shared_file = pool / 'shared.deb'
            old_file = pool / 'old.deb'
            new_file = pool / 'new.deb'
            for path in (shared_file, old_file, new_file):
                path.write_bytes(path.name.encode())

            def package(name, version, path):
                return dict(package=name, version=version, architecture='arm64',
                            filename=path.relative_to(root).as_posix(),
                            sha256=repository.digest(path), component=component)

            shared = package('linux-image-vendor-rk35xx', '1', shared_file)
            old = package('legacy-only', '1', old_file)
            new = package('replacement-only', '2', new_file)
            old_version = '2026.10.08-1'
            new_version = '2026.10.10-1'
            (manifests / f'{old_version}.json').write_text(json.dumps(dict(
                product=product, version=old_version, suite=suite, packages=[shared, old])))
            (manifests / f'{old_version}.json.asc').write_text('signature')
            (manifests / f'{new_version}.json').write_text(json.dumps(dict(
                product=product, version=new_version, suite=suite, packages=[shared, new])))
            catalog = root / 'catalog/suites' / suite / f'{component}.tsv'
            repository.write_catalog(catalog, [shared, old, new])
            plan = root / 'plan.json'
            plan.write_text(json.dumps(dict(
                schema_version=1, product=product, suite=suite,
                replacement_version=new_version, purge_versions=[old_version])))

            result = root / 'result.json'
            args = argparse.Namespace(repository=root, config=config, plan=plan, result=result)
            repository.purge_releases(args)

            self.assertFalse((manifests / f'{old_version}.json').exists())
            self.assertFalse((manifests / f'{old_version}.json.asc').exists())
            self.assertTrue((manifests / f'{new_version}.json').exists())
            self.assertFalse(old_file.exists())
            self.assertTrue(shared_file.exists())
            self.assertTrue(new_file.exists())
            self.assertEqual(json.loads(result.read_text()), {
                'removed_pool_files': [old_file.relative_to(root).as_posix()]})
            self.assertEqual(
                {repository.identity(entry) for entry in repository.read_catalog(catalog)},
                {repository.identity(shared), repository.identity(new)})

    def test_purge_rejects_stable_promoted_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            product = 'dshanpi-r1'
            config = ROOT / 'products' / product / 'product.json'
            manifests = root / 'catalog/releases' / product
            manifests.mkdir(parents=True)
            old_version = '2026.10.08-1'
            new_version = '2026.10.10-1'
            for version, promoted in ((old_version, 'noble'), (new_version, None)):
                manifest = dict(product=product, version=version, suite='noble-testing', packages=[])
                if promoted:
                    manifest['promoted_to'] = promoted
                (manifests / f'{version}.json').write_text(json.dumps(manifest))
            plan = root / 'plan.json'
            plan.write_text(json.dumps(dict(
                schema_version=1, product=product, suite='noble-testing',
                replacement_version=new_version, purge_versions=[old_version])))
            with self.assertRaisesRegex(SystemExit, 'stable-promoted'):
                repository.purge_releases(argparse.Namespace(
                    repository=root, config=config, plan=plan, result=None))


if __name__ == '__main__':
    unittest.main()
