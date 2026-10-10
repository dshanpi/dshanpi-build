import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('workspace', Path(__file__).resolve().parents[1] / 'scripts/checkout-workspace.py')
workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace)


class WorkspaceTests(unittest.TestCase):
    def test_pinned_checkout_retains_history_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            origin = root / 'origin'
            origin.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(origin), *args], text=True).strip()
            git('init', '-q', '-b', 'main')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'baseline', '--allow-empty')
            baseline = git('rev-parse', 'HEAD')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'next', '--allow-empty')
            head = git('rev-parse', 'HEAD')
            git('branch', 'apt-data')
            manifest = {'repositories': {name: {'url': str(origin), 'commit': 'self' if name == 'dshanpi-build' else head}
                                         for name in ['ArmBianOS', 'dshanpi-build', 'dspi-config']}}
            output = root / 'new host'
            resolved = workspace.checkout(output, manifest, head)
            self.assertEqual(resolved['dshanpi-build']['commit'], head)
            refs = subprocess.check_output(['git', '-C', str(output / 'dshanpi-build'), 'branch', '-r'], text=True)
            self.assertNotIn('apt-data', refs)
            subprocess.run(['git', '-C', str(output / 'ArmBianOS'), 'cat-file', '-e', baseline + '^{commit}'], check=True)
            with self.assertRaises(ValueError):
                workspace.checkout(output, manifest, head)

    def test_unpinned_input_is_rejected_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'new'
            manifest = {'repositories': {name: {'url': 'unused', 'commit': 'main'} for name in
                                         ['ArmBianOS', 'dshanpi-build', 'dspi-config']}}
            with self.assertRaises(ValueError):
                workspace.checkout(root, manifest, '0' * 40)
            self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
