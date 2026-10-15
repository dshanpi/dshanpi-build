"""Reject cross-capacity inputs and preserve 16GB release behavior."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

BUILDER = load('builder8', 'build-axcl-16g-packages.py')
GATE = load('gate8', 'validate-hardware-evidence.py')

class Axcl8gTests(unittest.TestCase):
    def test_rejects_wrong_pac_before_any_package_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # The firmware hash check is also exercised in the package build
            # acceptance; CLI must reject an attempt to override 16GB's PAC.
            result = subprocess.run(['python3', str(ROOT/'scripts/build-axcl-16g-packages.py'),
                                     str(root/'out'), '--firmware', str(root/'wrong.pac')],
                                    capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('8GB only', result.stderr)
            self.assertFalse((root/'out').exists())

    def test_8gb_rejects_16gb_retained_source_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['python3', str(ROOT/'scripts/build-axcl-8g-packages.py'),
                                     directory, '--previous-driver', '/nonexistent'],
                                    capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('independently pinned', result.stderr)

    def test_capacity_gate_requires_8gb_not_previous_16gb_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); product=root/'products/dshanpi-a1'; (product/'releases').mkdir(parents=True)
            (product/'product.json').write_text(json.dumps({'release_package_sets':['axcl-16g']}))
            (product/'releases/test.lock.json').write_text(json.dumps({'maintenance_adapter':'axcl-8g'}))
            manifest=root/'catalog/releases/dshanpi-a1/test.json';manifest.parent.mkdir(parents=True);manifest.write_text('{}')
            log=root/'board.log';log.write_text('test evidence')
            evidence={'schema_version':1,'product':'dshanpi-a1','release':'test','verdict':'passed',
                      'package_manifest_sha256':GATE.digest(manifest),
                      'checks':{name:'passed' for name in GATE.BASE_CHECKS},
                      'evidence':[{'path':'board.log','sha256':GATE.digest(log)}]}
            evidence['checks']['axcl-16g']={name:'passed' for name in GATE.AXCL_CHECKS}
            path=root/'evidence.json';path.write_text(json.dumps(evidence))
            with patch.object(GATE,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'axcl-8g'):
                    GATE.validate('dshanpi-a1','test',path,root)
                evidence['checks']['axcl-8g']={name:'passed' for name in GATE.AXCL_CHECKS}
                path.write_text(json.dumps(evidence));GATE.validate('dshanpi-a1','test',path,root)
                evidence['checks']['axcl-8g']['npu']='not-run'
                path.write_text(json.dumps(evidence))
                with self.assertRaisesRegex(ValueError,'npu'):
                    GATE.validate('dshanpi-a1','test',path,root)

if __name__ == '__main__':
    unittest.main()
