import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/reuse-published-packages.py'
spec = importlib.util.spec_from_file_location('reuse_published', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublishedPackageTests(unittest.TestCase):
    @staticmethod
    def write_config(root, component='dshanpi-r1', common_packages=None):
        config = root / 'product.json'
        config.write_text(json.dumps({
            'component': component,
            'common_packages': common_packages or [],
        }))
        return config

    @staticmethod
    def build_package(root, output, payload):
        build_name = output.relative_to(root).as_posix().replace('/', '-')
        package = root / (build_name + '-root')
        control = package / 'DEBIAN'
        control.mkdir(parents=True)
        (control / 'control').write_text(
            'Package: board-files\nVersion: 1.0\nArchitecture: all\n'
            'Maintainer: Test <test@example.invalid>\nDescription: test\n')
        data = package / 'usr/share/board-files'
        data.mkdir(parents=True)
        (data / 'board').write_text(payload)
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(package), str(output)],
                       check=True, capture_output=True)

    def test_first_publication_has_no_historical_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / 'repository'
            repository.mkdir()
            module.reuse(root / 'packages', repository, root / 'key.asc',
                         self.write_config(root))

    def test_unrelated_board_component_does_not_define_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packages = root / 'packages'
            packages.mkdir()
            repository = root / 'repository'
            unrelated = repository / 'pool/dshanpi-a1/b/board-files'
            unrelated.mkdir(parents=True)
            self.build_package(root, unrelated / 'board-files_1.0_all.deb', 'a1\n')
            self.build_package(root, packages / 'board-files_1.0_all.deb', 'r1\n')
            with mock.patch.object(module.subprocess, 'run'):
                module.reuse(packages, repository, root / 'key.asc',
                             self.write_config(root))

    def test_same_board_component_still_rejects_changed_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packages = root / 'packages'
            packages.mkdir()
            repository = root / 'repository'
            published = repository / 'pool/dshanpi-r1/b/board-files'
            published.mkdir(parents=True)
            self.build_package(root, published / 'board-files_1.0_all.deb', 'published\n')
            self.build_package(root, packages / 'board-files_1.0_all.deb', 'changed\n')
            with mock.patch.object(module.subprocess, 'run'):
                with self.assertRaisesRegex(ValueError, 'increment its version'):
                    module.reuse(packages, repository, root / 'key.asc',
                                 self.write_config(root))

    def test_only_nonfunctional_metadata_can_reuse_published_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / 'package'
            control = package / 'DEBIAN'
            control.mkdir(parents=True)
            payload = package / 'usr/share/example'
            payload.mkdir(parents=True)
            data = payload / 'data'
            data.write_text('original payload\n')

            def build(name, installed_size='4', md5='a  one\nb  two\n', depends='libc6'):
                (control / 'control').write_text(
                    'Package: test-reuse\nVersion: 1.0\nArchitecture: all\n'
                    'Maintainer: Test <test@example.invalid>\nDescription: test\n'
                    f'Installed-Size: {installed_size}\nDepends: {depends}\n')
                (control / 'md5sums').write_text(md5)
                for path in [package, *package.rglob('*')]:
                    os.utime(path, (1600000000, 1600000000))
                output = root / f'{name}.deb'
                subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(package), str(output)],
                               check=True, capture_output=True)
                return output

            original = build('original')
            metadata = build('metadata', '8', 'b  two\na  one\n')
            self.assertNotEqual(original.read_bytes(), metadata.read_bytes())
            self.assertTrue(module.equivalent(original, metadata))
            self.assertFalse(module.equivalent(original, build('dependency', depends='libc6, systemd')))
            self.assertFalse(module.equivalent(original, build('checksum', md5='c  one\nb  two\n')))
            (control / 'postinst').write_text('#!/bin/sh\necho changed\n')
            (control / 'postinst').chmod(0o755)
            self.assertFalse(module.equivalent(original, build('script')))
            (control / 'postinst').unlink()
            data.chmod(0o755)
            self.assertFalse(module.equivalent(original, build('mode')))
            data.chmod(0o644)
            data.write_text('changed payload\n')
            self.assertFalse(module.equivalent(original, build('payload')))


if __name__ == '__main__':
    unittest.main()
