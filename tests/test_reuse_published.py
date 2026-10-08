import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/reuse-published-packages.py'
spec = importlib.util.spec_from_file_location('reuse_published', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublishedPackageTests(unittest.TestCase):
    def test_first_publication_has_no_historical_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / 'repository'
            repository.mkdir()
            module.reuse(root / 'packages', repository, root / 'key.asc')

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
