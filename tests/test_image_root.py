from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify-image-root.py'


class ImageTests(unittest.TestCase):
    def test_requires_actual_installed_cohort_and_board_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                'var/lib/dpkg/status': 'Package: dshanpi-r1-release-core\nStatus: install ok installed\nVersion: 2026.10.08-1\nDepends: dspi-config (= 1.0.2-1)\n\nPackage: dspi-config\nStatus: install ok installed\nVersion: 1.0.2-1\n',
                'usr/share/dspi-config/boards/dshanpi-r1/system.conf': 'apt_components=common dshanpi-r1\n',
                'usr/share/dspi-config/boards/dshanpi-r1/overlays.tsv': '',
                'etc/apt/sources.list.d/dshanpi.sources': 'URIs: https://apt.100ask.net\nSuites: noble\nComponents: common dshanpi-r1\nSigned-By: /usr/share/keyrings/dshanpi-archive-keyring.gpg\n',
                'usr/share/keyrings/dshanpi-archive-keyring.gpg': 'test key bytes',
                'etc/armbian-release': 'BOARD=dshanpi-r1\n',
                'boot/armbianEnv.txt': 'fdtfile=rockchip/rk3568-dshapi-r1.dtb\n',
                'boot/dtb/rockchip/rk3568-dshapi-r1.dtb': 'test dtb bytes',
            }
            for name, contents in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
            command = ['python3', str(SCRIPT), str(root), 'dshanpi-r1', '2026.10.08-1']
            subprocess.run(command, check=True, capture_output=True)
            status = root / 'var/lib/dpkg/status'
            status.write_text(files['var/lib/dpkg/status'].replace('Version: 1.0.2-1', 'Version: 1.0.1-1'))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('missing or wrong dependency', result.stderr)
            status.write_text(files['var/lib/dpkg/status'])
            (root / 'boot/armbianEnv.txt').write_text('fdtfile=rockchip/wrong-board.dtb\n')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('wrong boot device tree', result.stderr)
            (root / 'boot/armbianEnv.txt').write_text(files['boot/armbianEnv.txt'])
            (root / 'boot/dtb/rockchip/rk3568-dshapi-r1.dtb').unlink()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('boot device tree is missing', result.stderr)


if __name__ == '__main__':
    unittest.main()
