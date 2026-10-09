import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RemoteFailureTests(unittest.TestCase):
    def run_script(self, script, fail):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = root / 'git'
            git.write_text('#!/bin/sh\nfor arg do\n'
                           'if [ "$arg" = ls-remote ]; then exit ' + ('128' if fail else '0') + '; fi\n'
                           'if [ "$arg" = get-url ]; then echo https://invalid.example/repo; exit 0; fi\n'
                           'done\nexit 0\n')
            git.chmod(0o755)
            destination = root / 'repository'
            if script == 'publish-pages.sh':
                destination.mkdir()
            result = subprocess.run(['bash', str(ROOT / 'scripts' / script), str(destination),
                                     str(ROOT / 'keys/dshanpi-archive.asc')],
                                    env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH']},
                                    capture_output=True, text=True)
            return result, destination.exists()

    def test_fetch_refuses_failed_remote_lookup(self):
        result, exists = self.run_script('fetch-pages.sh', True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot read Pages state', result.stderr)
        self.assertFalse(exists)

    def test_publish_refuses_failed_remote_lookup(self):
        result, _ = self.run_script('publish-pages.sh', True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot read Pages state', result.stderr)

    def test_successful_empty_remote_can_initialize(self):
        result, exists = self.run_script('fetch-pages.sh', False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(exists)
