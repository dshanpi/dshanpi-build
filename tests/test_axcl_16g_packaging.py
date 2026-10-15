"""Guard the split-version AXCL 16GB compatibility package cohort."""
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'scripts/build-axcl-16g-packages.py'
SPEC = importlib.util.spec_from_file_location('build_axcl_16g_packages', MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
OPTIONAL_PATH = ROOT / 'scripts/build-release-optionals.py'
OPTIONAL_SPEC = importlib.util.spec_from_file_location('build_release_optionals', OPTIONAL_PATH)
OPTIONAL = importlib.util.module_from_spec(OPTIONAL_SPEC)
OPTIONAL_SPEC.loader.exec_module(OPTIONAL)


class Axcl16gPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads((ROOT / 'packages/axcl-16g/upstream.lock.json').read_text())
        cls.dependencies = MODULE.package_dependencies(cls.lock)

    def test_installed_size_excludes_imported_control_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'usr').mkdir(); (root / 'usr/payload').write_bytes(b'x' * 1025)
            (root / 'DEBIAN').mkdir(); (root / 'DEBIAN/control').write_bytes(b'a' * 9999)
            self.assertEqual(MODULE.installed_size_kib(root), 2)
            (root / 'DEBIAN/control').write_bytes(b'b' * 50000)
            self.assertEqual(MODULE.installed_size_kib(root), 2)

    def test_new_driver_identity_does_not_overwrite_published_package(self):
        self.assertEqual(self.lock['version'], '3.16.0+dshanpi.2026.10.15.2')
        self.assertEqual(self.lock['source_driver']['version'], '3.16.0+dshanpi2')
        self.assertNotEqual(self.lock['version'], self.lock['source_driver']['version'])

    def test_retained_payloads_are_hash_pinned(self):
        retained = self.lock['retained_packages']
        self.assertEqual(set(retained), {
            'dshanpi-axcl-runtime-16g',
            'dshanpi-axcl-firmware-16g',
        })
        for package in retained.values():
            self.assertEqual(package['version'], '3.16.0+dshanpi2')
            self.assertRegex(package['sha256'], r'^[0-9a-f]{64}$')

    def test_driver_targets_new_headers_exactly(self):
        revision = '25.11.0-trunk.20261010.1'
        self.assertEqual(self.lock['kernel_package_version'], revision)
        self.assertIn(f'linux-headers-vendor-rk35xx (= {revision})',
                      self.dependencies['dshanpi-axcl-dkms-16g'])

    def test_maintenance_meta_targets_new_image_and_bsp_but_retains_runtime_bytes(self):
        depends = self.dependencies['dshanpi-a1-axcl-16g']
        revision = self.lock['kernel_package_version']
        self.assertIn('dshanpi-axcl-runtime-16g (= 3.16.0+dshanpi2)', depends)
        self.assertIn('dshanpi-axcl-firmware-16g (= 3.16.0+dshanpi2)', depends)
        self.assertIn('dshanpi-axcl-dkms-16g (= 3.16.0+dshanpi.2026.10.15.2)', depends)
        self.assertIn(f'linux-image-vendor-rk35xx (= {revision})', depends)
        self.assertIn(f'armbian-bsp-cli-dshanpi-a1-vendor (= {revision})', depends)

    def test_full_release_overrides_component_platform_version(self):
        release_version = '25.11.0-trunk.20261101.2'
        package_version = OPTIONAL.release_package_version('3.16.0', '2026.11.01-2')
        dependencies = MODULE.package_dependencies(
            self.lock, package_version, release_version, complete_cohort=True)
        self.assertEqual(package_version, '3.16.0+dshanpi.2026.11.01.2')
        self.assertIn(f'linux-headers-vendor-rk35xx (= {release_version})',
                      dependencies['dshanpi-axcl-dkms-16g'])
        self.assertIn(f'dshanpi-axcl-runtime-16g (= {package_version})',
                      dependencies['dshanpi-a1-axcl-16g'])
        self.assertIn(f'dshanpi-axcl-firmware-16g (= {package_version})',
                      dependencies['dshanpi-a1-axcl-16g'])
        self.assertIn(f'dshanpi-axcl-dkms-16g (= {package_version})',
                      dependencies['dshanpi-a1-axcl-16g'])
        self.assertIn(f'linux-image-vendor-rk35xx (= {release_version})',
                      dependencies['dshanpi-a1-axcl-16g'])

    def test_a1_full_release_selects_axcl_16g(self):
        config = json.loads((ROOT / 'products/dshanpi-a1/product.json').read_text())
        self.assertEqual(config['release_package_sets'], ['axcl-16g'])
        self.assertEqual(config['release_optional_selectors'], ['dshanpi-a1-axcl-16g'])


if __name__ == '__main__':
    unittest.main()
