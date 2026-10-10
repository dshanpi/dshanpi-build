"""Exercise the staged-source boundary, without trusting .gitignore alone."""
from pathlib import Path
import subprocess
import tempfile
import unittest

CHECKER = Path(__file__).resolve().parents[1] / 'tools/check-repository-hygiene.py'


class HygieneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')

    def git(self, *args):
        subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)

    def add(self, name, content=b'fixture\n'):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        self.git('add', '-f', '--', name)

    def result(self):
        return subprocess.run(['python3', str(CHECKER), '--root', str(self.root)], capture_output=True)

    def test_rejects_staged_cache(self):
        self.add('lib/__pycache__/module.pyc')
        self.assertNotEqual(self.result().returncode, 0)

    def test_rejects_staged_build_output(self):
        self.add('output/images/example.img')
        self.assertNotEqual(self.result().returncode, 0)

    def test_ignores_untracked_local_cache(self):
        (self.root / '__pycache__').mkdir()
        (self.root / '__pycache__/local.pyc').write_bytes(b'local')
        self.add('source.py')
        self.assertEqual(self.result().returncode, 0)

    def test_allows_vendor_archive_public_key_and_evidence(self):
        self.add('packages/example/vendor/source.tar.gz', b'\x1f\x8bfixture')
        self.add('packages/example/upstream.lock.json', b'{"sha256":"fixture"}')
        self.add('keys/archive.asc', b'-----BEGIN PGP PUBLIC KEY BLOCK-----\n')
        self.add('products/board/releases/1.validation/test.log')
        self.assertEqual(self.result().returncode, 0)

    def test_rejects_key_in_index_even_if_worktree_was_cleaned(self):
        self.add('docs/accidental.txt', b'-----BEGIN OPENSSH PRIVATE KEY-----\nTEST_ONLY\n')
        (self.root / 'docs/accidental.txt').write_text('removed locally only\n')
        result = self.result()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b'TEST_ONLY', result.stderr)


if __name__ == '__main__':
    unittest.main()
