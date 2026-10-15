"""Exercise package lifecycle behavior without touching host users/devices."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

COMPONENT = Path(__file__).resolve().parents[1] / 'packages/axcl-16g'


class AxclAccessTests(unittest.TestCase):
    def lifecycle(self, script='postinst', action='configure', *, group=True,
                  live=True, present=('axcl_host', 'msg_userdev'), tmpfiles_ok=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / 'bin'
            commands.mkdir()
            log = root / 'calls'
            log.touch()
            runtime = root / 'run'
            runtime.mkdir()
            nodes = root / 'nodes'
            nodes.mkdir()
            for name in present:
                (nodes / name).touch()
            control = socket.socket(socket.AF_UNIX)
            if live:
                control.bind(str(runtime / 'control'))
                (runtime / 'system').mkdir()
            for name in ('getent', 'addgroup', 'systemd-tmpfiles', 'udevadm', 'systemctl'):
                body = 'printf "%s\\n" "' + name + ' $*" >> "$CALL_LOG"\n'
                if name == 'getent':
                    body += 'exit ' + ('0' if group else '2') + '\n'
                if name == 'systemd-tmpfiles' and not tmpfiles_ok:
                    body += 'exit 37\n'
                path = commands / name
                path.write_text('#!/bin/sh\n' + body)
                path.chmod(0o755)
            text = (COMPONENT / script).read_text()
            text = text.replace('/run/udev/control', str(runtime / 'control'))
            text = text.replace('/run/systemd/system', str(runtime / 'system'))
            text = text.replace('/sys/class/misc/', str(nodes) + '/')
            result = subprocess.run(['sh', '-s', '--', action], input=text,
                                    text=True, capture_output=True,
                                    env={**os.environ, 'PATH': str(commands) + ':' + os.environ['PATH'],
                                         'CALL_LOG': str(log)})
            control.close()
            return result, log.read_text()

    def test_configure_live_existing_group_refreshes_only_present_nodes(self):
        result, calls = self.lifecycle()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('addgroup', calls)
        self.assertIn('systemd-tmpfiles --create /usr/lib/tmpfiles.d/dshanpi-axcl-access.conf', calls)
        self.assertEqual(calls.count('udevadm trigger'), 2)
        self.assertIn('udevadm settle', calls)
        self.assertIn('systemctl daemon-reload', calls)
        self.assertNotIn('systemctl start', calls)
        self.assertNotIn('systemctl enable', calls)

    def test_missing_group_is_created_before_log_access(self):
        result, calls = self.lifecycle(group=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(calls.index('addgroup --system render'), calls.index('systemd-tmpfiles'))

    def test_repeated_configure_is_safe_and_does_not_activate_hardware(self):
        first = self.lifecycle(present=())
        second = self.lifecycle(present=())
        self.assertEqual(first[0].returncode, 0)
        self.assertEqual(first[1], second[1])
        self.assertNotIn('udevadm trigger', first[1])

    def test_image_configuration_skips_unavailable_daemons(self):
        result, calls = self.lifecycle(live=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn('systemd-tmpfiles', calls)
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('systemctl', calls)

    def test_permission_failure_is_not_hidden(self):
        result, calls = self.lifecycle(tmpfiles_ok=False)
        self.assertEqual(result.returncode, 37)
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('systemctl', calls)

    def test_abort_does_not_apply_configuration(self):
        result, calls = self.lifecycle(action='abort-upgrade')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, '')

    def test_remove_refreshes_daemons_but_upgrade_postrm_does_nothing(self):
        result, calls = self.lifecycle(script='postrm', action='remove')
        self.assertEqual(result.returncode, 0)
        self.assertIn('udevadm control --reload-rules', calls)
        self.assertIn('systemctl daemon-reload', calls)
        self.assertNotIn('systemd-tmpfiles', calls)
        result, calls = self.lifecycle(script='postrm', action='upgrade')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, '')


if __name__ == '__main__':
    unittest.main()
