"""Reject unbound or incomplete maintenance sources before extracting packages."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MaintenanceInputTests(unittest.TestCase):
    def invoke(self, plan):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'plan.json'
            path.write_text(json.dumps(plan))
            result = subprocess.run(['python3', str(ROOT / 'scripts/build-axcl-16g-packages.py'),
                                     str(root / 'out'), '--previous-release-lock', str(path)],
                                    text=True, capture_output=True)
            self.assertFalse((root / 'out').exists())
            return result

    def plan(self):
        return json.loads((ROOT / 'products/dshanpi-a1/releases/2026.10.15-2.lock.json').read_text())

    def test_wrong_product_is_rejected(self):
        plan = self.plan(); plan['product'] = 'dshanpi-a1-cm5'
        result = self.invoke(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid previous AXCL release plan', result.stderr)

    def test_changed_component_lock_is_rejected(self):
        plan = self.plan(); plan['axcl_16g_lock_sha256'] = '0' * 64
        result = self.invoke(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid previous AXCL release plan', result.stderr)

    def test_partial_input_set_is_rejected(self):
        result = self.invoke(self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires all three input packages', result.stderr)
