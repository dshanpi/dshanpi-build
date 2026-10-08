import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class CameraDirectoryUpgrade(unittest.TestCase):
    def test_upgrade_repairs_owned_trees_without_following_symlinks(self):
        script = (Path(__file__).resolve().parents[1] / 'scripts/build-reviewed-camera.sh').read_text()
        postinst = script.split("<<'EOF'\n", 1)[1].split('\nEOF\n', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            owned = [root / p for p in ('etc/iqfiles', 'usr/include/IspFec', 'usr/include/rkaiq/algos')]
            for directory in owned:
                directory.mkdir(parents=True)
                directory.chmod(0o777)
            outside = root / 'outside'
            outside.mkdir(mode=0o700)
            (owned[0] / 'external').symlink_to(outside, target_is_directory=True)
            (root / 'etc').chmod(0o750)
            subprocess.run(['sh', '-s', 'configure'], input=postinst, text=True,
                           env={**os.environ, 'DPKG_ROOT': str(root)}, check=True)
            for directory in owned:
                self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
            self.assertEqual(outside.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / 'etc').stat().st_mode & 0o777, 0o750)


if __name__ == '__main__':
    unittest.main()
