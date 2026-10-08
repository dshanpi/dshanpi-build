from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/compress-deb.sh'


class CompressionTests(unittest.TestCase):
    def test_payload_identity_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control = root / 'package/DEBIAN'
            control.mkdir(parents=True)
            (control / 'control').write_text(
                'Package: test-cohort\nVersion: 1.0\nArchitecture: all\n'
                'Maintainer: Test <test@example.invalid>\nDescription: test\n')
            payload = root / 'package/usr/share/example'
            payload.mkdir(parents=True)
            (payload / 'data').write_bytes(b'unchanged contents\n' * 500)
            (payload / 'link').symlink_to('data')
            original = root / 'original.deb'
            subprocess.run(['dpkg-deb', '-Znone', '--root-owner-group', '--build',
                            str(root / 'package'), str(original)], check=True, capture_output=True)
            outputs = [root / 'first.deb', root / 'second.deb']
            for output in outputs:
                subprocess.run([str(SCRIPT), str(original), str(output)], check=True)
                for option in ('--ctrl-tarfile', '--fsys-tarfile'):
                    self.assertEqual(subprocess.check_output(['dpkg-deb', option, str(original)]),
                                     subprocess.check_output(['dpkg-deb', option, str(output)]))
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            self.assertLess(outputs[0].stat().st_size, original.stat().st_size)


if __name__ == '__main__':
    unittest.main()
