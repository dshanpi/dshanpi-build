"""Signed repository/SSH transfer simulations; no remote credentials or board needed."""
import gzip
import hashlib
import importlib.util
import json
import lzma
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ssh_repository', ROOT / 'scripts/ssh-repository.py')
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class SSHPublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        cls.key_root = Path(cls.keys.name)
        cls.env = dict(os.environ, GNUPGHOME=str(cls.key_root / 'gnupg'))
        Path(cls.env['GNUPGHOME']).mkdir(mode=0o700)
        subprocess.run(['gpg', '--batch', '--passphrase', '', '--quick-gen-key',
                        'APT SSH Test <apt@example.invalid>', 'ed25519', 'sign', '0'],
                       env=cls.env, check=True, capture_output=True)
        cls.fingerprint = subprocess.check_output(
            ['gpg', '--batch', '--with-colons', '--list-secret-keys'], env=cls.env,
            stderr=subprocess.DEVNULL, text=True).split('fpr:::::::::')[1].split(':')[0]
        cls.public = cls.key_root / 'public.asc'
        cls.public.write_bytes(subprocess.check_output(
            ['gpg', '--batch', '--armor', '--export', cls.fingerprint], env=cls.env))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['gpgconf', '--kill', 'gpg-agent'], env=cls.env, capture_output=True)
        cls.keys.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.server = self.root / 'server'
        SERVER.initialize(self.server)
        self.counter = 0

    def fixture(self, name, previous='unrelated-pages-predecessor', payloads=None,
                operation=None, removed=None):
        repo = self.root / name
        repo.mkdir()
        (repo / 'catalog/releases').mkdir(parents=True)
        payloads = payloads if payloads is not None else {'fixture_1_arm64.deb': b'original bytes'}
        for filename, content in payloads.items():
            path = repo / 'pool/common/f/fixture' / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        packages = ''
        for i, (filename, content) in enumerate(payloads.items()):
            packages += ('Package: fixture\nVersion: ' + str(i + 1) + '\nArchitecture: arm64\n'
                         'Filename: pool/common/f/fixture/' + filename + '\nSize: ' + str(len(content)) +
                         '\nSHA256: ' + hashlib.sha256(content).hexdigest() + '\n\n')
        for suite in ('noble', 'noble-testing'):
            directory = repo / 'dists' / suite
            index = directory / 'common/binary-arm64/Packages'
            index.parent.mkdir(parents=True)
            index.write_text(packages)
            index.with_name('Packages.gz').write_bytes(gzip.compress(packages.encode(), mtime=0))
            index.with_name('Packages.xz').write_bytes(lzma.compress(packages.encode()))
            release = 'Suite: ' + suite + '\n'
            if suite.endswith('-testing'):
                release += 'NotAutomatic: yes\nButAutomaticUpgrades: no\n'
            release += 'SHA256:\n'
            for path in sorted(index.parent.iterdir()):
                release += f' {SERVER.digest(path)} {path.stat().st_size} {path.relative_to(directory)}\n'
            (directory / 'Release').write_text(release)
        publication = dict(schema_version=1, channel='testing', product='dshanpi-a1',
                           suite='noble-testing', component='dshanpi-a1', version='2026.10.15-1',
                           expected_base_state_sha256=(previous if len(previous) == 64 else 'a' * 64))
        if operation:
            publication['operation'] = operation
        if removed is not None:
            publication['removed_pool_files'] = removed
        (repo / 'PUBLICATION.json').write_text(json.dumps(publication))
        self.sign(repo)
        result = subprocess.run([str(ROOT / 'scripts/prepare-apt-site.sh'), str(repo), str(self.public)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return repo

    def sign(self, repo):
        subprocess.run([str(ROOT / 'scripts/sign-repository.sh'), str(repo), self.fingerprint],
                       env=self.env, check=True, capture_output=True)

    def stage(self, candidate, bootstrap=False, link=False):
        self.counter += 1
        job = f'20261015T120000Z-{SERVER.digest(candidate / "SHA256SUMS")[:16]}-{self.counter}'
        previous = SERVER.prepare(self.server, job, '--bootstrap' if bootstrap else 'publish')
        upload = self.server / 'incoming' / job
        command = ['rsync', '-rlp', '--checksum', '--chmod=D755,F644', '--delay-updates']
        if link:
            command.append('--link-dest=' + previous)
        command += [str(candidate) + '/', str(upload / 'repository') + '/']
        subprocess.run(command, check=True, capture_output=True)
        shutil.copy2(ROOT / 'scripts/verify-repository.py', upload / 'control')
        shutil.copy2(self.public, upload / 'control')
        return job

    def commit(self, candidate, job, bootstrap=False):
        SERVER.publish(self.server, job, SERVER.digest(candidate / 'SHA256SUMS'),
                       self.public.name, bootstrap)

    def bootstrap(self):
        candidate = self.fixture('initial')
        self.commit(candidate, self.stage(candidate, bootstrap=True), bootstrap=True)
        return SERVER.current_release(self.server)

    def test_migration_preserves_signed_bytes_and_retries_identical_state(self):
        previous = self.bootstrap()
        before = (previous / 'SHA256SUMS.asc').read_bytes()
        same = self.root / 'initial'
        self.commit(same, self.stage(same, bootstrap=True), bootstrap=True)
        self.assertEqual(SERVER.current_release(self.server), previous)
        self.assertEqual((previous / 'SHA256SUMS.asc').read_bytes(), before)

    def test_empty_server_requires_explicit_migration(self):
        with self.assertRaisesRegex(ValueError, 'migration'):
            SERVER.prepare(self.server, '20261015T120000Z-' + 'a' * 16 + '-1', 'publish')

    def test_update_reuses_hardlinks_and_preserves_previous_snapshot(self):
        previous = self.bootstrap()
        candidate = self.fixture('update', SERVER.digest(previous / 'SHA256SUMS'), {
            'fixture_1_arm64.deb': b'original bytes', 'fixture_2_arm64.deb': b'new bytes'})
        job = self.stage(candidate, link=True)
        old_payload = previous / 'pool/common/f/fixture/fixture_1_arm64.deb'
        uploaded = self.server / 'incoming' / job / 'repository' / old_payload.relative_to(previous)
        self.assertEqual(old_payload.stat().st_ino, uploaded.stat().st_ino)
        self.commit(candidate, job)
        self.assertNotEqual(SERVER.current_release(self.server), previous)
        self.assertEqual(old_payload.read_bytes(), b'original bytes')

    def test_corrupt_upload_does_not_switch(self):
        previous = self.bootstrap()
        candidate = self.fixture('corrupt', SERVER.digest(previous / 'SHA256SUMS'))
        job = self.stage(candidate)
        payload = self.server / 'incoming' / job / 'repository/pool/common/f/fixture/fixture_1_arm64.deb'
        payload.write_bytes(b'transfer interrupted')
        with self.assertRaises(subprocess.CalledProcessError):
            self.commit(candidate, job)
        self.assertEqual(SERVER.current_release(self.server), previous)

    def test_wrong_signature_does_not_switch(self):
        previous = self.bootstrap()
        candidate = self.fixture('bad-signature', SERVER.digest(previous / 'SHA256SUMS'))
        job = self.stage(candidate)
        (self.server / 'incoming' / job / 'repository/SHA256SUMS.asc').write_text('invalid')
        with self.assertRaises(subprocess.CalledProcessError):
            self.commit(candidate, job)
        self.assertEqual(SERVER.current_release(self.server), previous)

    def test_stale_candidate_cannot_overwrite_new_publication(self):
        previous = self.bootstrap()
        base = SERVER.digest(previous / 'SHA256SUMS')
        first = self.fixture('first', base)
        stale = self.fixture('stale', base, {'fixture_1_arm64.deb': b'original bytes',
                                           'fixture_2_arm64.deb': b'late bytes'})
        late_job = self.stage(stale)
        self.commit(first, self.stage(first))
        current = SERVER.current_release(self.server)
        with self.assertRaises(subprocess.CalledProcessError):
            self.commit(stale, late_job)
        self.assertEqual(SERVER.current_release(self.server), current)

    def test_signed_historical_payload_change_rejected_without_mutating_live_hardlink(self):
        previous = self.bootstrap()
        candidate = self.fixture('changed', SERVER.digest(previous / 'SHA256SUMS'),
                                 {'fixture_1_arm64.deb': b'replaced bytes'})
        job = self.stage(candidate, link=True)
        with self.assertRaisesRegex(ValueError, 'historical pool'):
            self.commit(candidate, job)
        self.assertEqual((previous / 'pool/common/f/fixture/fixture_1_arm64.deb').read_bytes(), b'original bytes')
        self.assertEqual(SERVER.current_release(self.server), previous)

    def test_unsigned_pool_removal_rejected_and_explicit_signed_purge_allowed(self):
        previous = self.bootstrap()
        candidate = self.fixture('removal', SERVER.digest(previous / 'SHA256SUMS'),
                                 {'fixture_2_arm64.deb': b'new bytes'})
        with self.assertRaisesRegex(ValueError, 'pool removal'):
            self.commit(candidate, self.stage(candidate))
        publication = candidate / 'PUBLICATION.json'
        data = json.loads(publication.read_text())
        data.update(operation='purge', removed_pool_files=['pool/common/f/fixture/fixture_1_arm64.deb'])
        publication.write_text(json.dumps(data))
        self.sign(candidate)
        self.commit(candidate, self.stage(candidate))
        self.assertFalse((SERVER.current_release(self.server) / 'pool/common/f/fixture/fixture_1_arm64.deb').exists())
        self.assertTrue((previous / 'pool/common/f/fixture/fixture_1_arm64.deb').exists())

    def test_migration_refuses_to_overwrite_different_existing_state(self):
        previous = self.bootstrap()
        candidate = self.fixture('different', SERVER.digest(previous / 'SHA256SUMS'))
        with self.assertRaisesRegex(ValueError, 'migration cannot overwrite'):
            self.commit(candidate, self.stage(candidate, bootstrap=True), bootstrap=True)
        self.assertEqual(SERVER.current_release(self.server), previous)

    def test_failed_atomic_switch_keeps_previous_release(self):
        previous = self.bootstrap()
        candidate = self.fixture('failed-switch', SERVER.digest(previous / 'SHA256SUMS'))
        job = self.stage(candidate)
        with mock.patch.object(SERVER.os, 'replace', side_effect=OSError('simulated switch failure')):
            with self.assertRaisesRegex(OSError, 'switch failure'):
                self.commit(candidate, job)
        self.assertEqual(SERVER.current_release(self.server), previous)
        self.assertFalse((self.server / ('.current-' + job)).is_symlink())

    def test_symlink_upload_and_escaped_current_rejected(self):
        candidate = self.fixture('symlinks')
        job = self.stage(candidate, bootstrap=True)
        (self.server / 'incoming' / job / 'repository/escape').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            self.commit(candidate, job, bootstrap=True)
        (self.server / 'current').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'outside release'):
            SERVER.current_release(self.server)

    def test_real_sshpass_authentication_and_nested_environment_scrubbing(self):
        # Exercise the real PTY/password helper without network or system users.
        # sshpass scrubs SSHPASS before spawning its child: a nested copy would
        # therefore send that scrubbed value, not the actual supplied password.
        prompt = self.root / 'password-prompt.py'
        prompt.write_text("""import os, sys, termios
fd = os.open('/dev/tty', os.O_RDWR)
original = termios.tcgetattr(fd)
noecho = original.copy()
noecho[3] &= ~termios.ECHO
termios.tcsetattr(fd, termios.TCSANOW, noecho)
os.write(fd, b'Password: ')
value = b''
while not value.endswith(b'\\n'):
    value += os.read(fd, 1)
termios.tcsetattr(fd, termios.TCSANOW, original)
os.close(fd)
sys.exit(0 if value.rstrip(b'\\r\\n') == os.environ['APT_TEST_EXPECT_PASSWORD'].encode() else 5)
""")
        env = dict(self.env, SSHPASS=' fixture-token ', APT_TEST_EXPECT_PASSWORD=' fixture-token ')
        for command, expected in [(['sshpass', '-e'], 0),
                                  (['sshpass', '-e', 'sshpass', '-e'], 5)]:
            result = subprocess.run(command + ['python3', str(prompt)], env=env,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, expected)

    def test_full_shell_transport_migration_fetch_and_update(self):
        # Real rsync and streamed remote Python, with SSH/auth transport replaced
        # by a local command adapter. This exercises shell argument handling too.
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'sshpass').write_text('#!/bin/sh\n[ "$1" = -e ] || exit 90\n[ "${APT_TEST_SSHPASS_ACTIVE:-}" != 1 ] || exit 92\nexport APT_TEST_SSHPASS_ACTIVE=1\n[ "$SSHPASS" = "$APT_TEST_EXPECT_PASSWORD" ] || exit 91\nshift\nexec "$@"\n')
        (bin_dir / 'ssh').write_text('''#!/bin/sh
while [ "$1" = -p ] || [ "$1" = -o ] || [ "$1" = -l ]; do shift 2; done
shift
if [ "${APT_TEST_FAIL_RSYNC:-}" = 1 ]; then
    case "$*" in *--server*) exit 77 ;; esac
fi
exec sh -c "$*"
''')
        for p in bin_dir.iterdir():
            p.chmod(0o755)
        env = dict(self.env, PATH=str(bin_dir) + ':' + os.environ['PATH'], HOST=' \tlocalhost\r\n ',
                   USERNAME=' fixture ', PASSWORD=' fixture-password ', PORT=' 22\r\n',
                   APT_TEST_EXPECT_PASSWORD=' fixture-password ',
                   APT_SERVER_ROOT=str(self.server))
        candidate = self.fixture('transport')
        def run(*args, success=True):
            result = subprocess.run(args, env=env, capture_output=True, text=True)
            if success:
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0)
        run(str(ROOT / 'scripts/fetch-apt.sh'), str(self.root / 'empty'), str(self.public), success=False)
        run(str(ROOT / 'scripts/publish-apt.sh'), str(candidate), str(self.public), '--bootstrap')
        fetched = self.root / 'fetched'
        run(str(ROOT / 'scripts/fetch-apt.sh'), str(fetched), str(self.public))
        self.assertEqual((fetched / 'SHA256SUMS').read_bytes(), (candidate / 'SHA256SUMS').read_bytes())
        updated = self.fixture('transport-update', SERVER.digest(fetched / 'SHA256SUMS'))
        run(str(ROOT / 'scripts/publish-apt.sh'), str(updated), str(self.public))
        self.assertEqual(SERVER.digest(SERVER.current_release(self.server) / 'SHA256SUMS'),
                         SERVER.digest(updated / 'SHA256SUMS'))
        current = SERVER.current_release(self.server)
        env['APT_TEST_FAIL_RSYNC'] = '1'
        run(str(ROOT / 'scripts/publish-apt.sh'), str(updated), str(self.public), success=False)
        self.assertEqual(SERVER.current_release(self.server), current)
        env.pop('APT_TEST_FAIL_RSYNC')
        env['HOST'] = '-oProxyCommand=invalid'
        run(str(ROOT / 'scripts/fetch-apt.sh'), str(self.root / 'invalid'), str(self.public), success=False)


if __name__ == '__main__':
    unittest.main()
