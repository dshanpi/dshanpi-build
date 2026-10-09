"""Exercise the activation guard against the observed same-vermagic ABI failure."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AxclAbiGuardTests(unittest.TestCase):
    def guard(self, btf='y', layout='00000380'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'board').write_text('BOARD=dshanpi-a1\n')
            headers = root / 'modules/6.1.115-vendor-rk35xx/build'
            headers.mkdir(parents=True)
            (headers / '.config').write_text('CONFIG_DEBUG_INFO_BTF_MODULES=' + btf + '\n')
            commands = {
                'uname': 'echo 6.1.115-vendor-rk35xx',
                'zcat': 'echo CONFIG_DEBUG_INFO_BTF_MODULES=y',
                'modinfo': 'if [ "$1" = -n ]; then echo "$2.ko"; else echo "6.1.115-vendor-rk35xx SMP"; fi',
                'objdump': 'if [ "$2" = pwm_fan.ko ]; then echo "0 .gnu.linkonce.this_module 00000380"; else echo "0 .gnu.linkonce.this_module $TEST_LAYOUT"; fi',
                'lspci': 'echo "0000:01:00.0 0400: 1f4b:0650"',
                'modprobe': 'echo MUST_NOT_LOAD >&2; exit 99',
            }
            for name, body in commands.items():
                p = root / name
                p.write_text('#!/bin/sh\n' + body + '\n')
                p.chmod(0o755)
            script = (ROOT / 'packages/axcl-16g/dshanpi-axcl').read_text()
            script = script.replace('/etc/armbian-release', str(root / 'board'))
            script = script.replace('/lib/modules/', str(root / 'modules') + '/')
            script = script.replace('/lib/firmware/', str(root / 'firmware') + '/')
            result = subprocess.run(['bash', '-s', '--', 'check'], input=script, text=True,
                                    capture_output=True, env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'], 'TEST_LAYOUT': layout})
            self.assertNotIn('MUST_NOT_LOAD', result.stdout + result.stderr)
            return result

    def test_matching_abi_reaches_missing_firmware_check(self):
        result = self.guard()
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn('PASS: A1 identity and driver ABI', result.stdout)

    def test_changed_btf_config_rejected_before_loading(self):
        result = self.guard(btf='n')
        self.assertEqual(result.returncode, 2)
        self.assertIn('headers changed CONFIG_DEBUG_INFO_BTF_MODULES', result.stderr)

    def test_same_vermagic_wrong_module_layout_rejected(self):
        result = self.guard(layout='00000340')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Module layout mismatch', result.stderr)
