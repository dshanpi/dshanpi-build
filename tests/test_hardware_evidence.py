import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/validate-hardware-evidence.py'
SPEC = importlib.util.spec_from_file_location('hardware_evidence', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HardwareEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / 'repository'
        manifest = self.repository / 'catalog/releases/dshanpi-a1/2026.10.13-1.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"product":"dshanpi-a1","version":"2026.10.13-1"}\n')
        manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.evidence = {
            'schema_version': 1,
            'product': 'dshanpi-a1',
            'release': '2026.10.13-1',
            'verdict': 'passed',
            'package_manifest_sha256': manifest_hash,
            'checks': {
                'apt_install': 'passed',
                'release_meta': 'passed',
                'boot': 'passed',
                'reboot': 'passed',
                'rollback': 'passed',
                'axcl-16g': {name: 'passed' for name in MODULE.AXCL_CHECKS},
            },
            'evidence': [{'path': 'board.log', 'sha256': 'a' * 64}],
        }
        self.log = self.root / 'board.log'
        self.log.write_text('hardware acceptance passed\n')
        self.evidence['evidence'][0]['sha256'] = hashlib.sha256(self.log.read_bytes()).hexdigest()
        self.path = self.root / 'evidence.json'
        self.path.write_text(json.dumps(self.evidence))

    def tearDown(self):
        self.temporary.cleanup()

    def test_accepts_complete_exact_release_evidence(self):
        MODULE.validate('dshanpi-a1', '2026.10.13-1', self.path, self.repository)

    def test_rejects_missing_axcl_runtime_test(self):
        self.evidence['checks']['axcl-16g']['npu'] = 'not-run'
        self.path.write_text(json.dumps(self.evidence))
        with self.assertRaisesRegex(ValueError, 'npu'):
            MODULE.validate('dshanpi-a1', '2026.10.13-1', self.path, self.repository)

    def test_rejects_different_package_manifest(self):
        self.evidence['package_manifest_sha256'] = '0' * 64
        self.path.write_text(json.dumps(self.evidence))
        with self.assertRaisesRegex(ValueError, 'exact package manifest'):
            MODULE.validate('dshanpi-a1', '2026.10.13-1', self.path, self.repository)

    def test_rejects_missing_evidence_artifact(self):
        self.log.unlink()
        with self.assertRaisesRegex(ValueError, 'artifact is missing'):
            MODULE.validate('dshanpi-a1', '2026.10.13-1', self.path, self.repository)


if __name__ == '__main__':
    unittest.main()
