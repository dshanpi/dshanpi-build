"""The policy gate must reject drift and missing enforcement entry points."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.manifest = json.loads((ROOT / ".delivery-policy.json").read_text())
        paths = {".delivery-policy.json", "DELIVERY_POLICY.md", "tools/check-delivery-policy.py",
                 *self.manifest["references"], *self.manifest["hooks"]}
        for name in paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)

    def run_gate(self, *args):
        return subprocess.run(["python3", str(ROOT / "tools/check-delivery-policy.py"),
                               "--root", str(self.root), *args], capture_output=True, text=True)

    def test_current_policy_is_valid(self):
        self.assertEqual(self.run_gate().returncode, 0)

    def test_rejects_policy_changed_without_manifest(self):
        path = self.root / "DELIVERY_POLICY.md"
        path.write_text(path.read_text() + "\nchanged\n")
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)

    def test_rejects_missing_agent_entry(self):
        (self.root / "AGENTS.md").unlink()
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing policy entry", result.stderr)

    def test_rejects_removed_ci_hook(self):
        path = self.root / ".github/workflows/ci.yml"
        path.write_text(path.read_text().replace("check-delivery-policy.py", "skipped.py"))
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not wired", result.stderr)

    def test_rejects_peer_drift_even_with_updated_peer_hash(self):
        peer = Path(self.temp.name) / "peer"
        shutil.copytree(self.root, peer)
        document = peer / "DELIVERY_POLICY.md"
        document.write_text(document.read_text() + "\nlocal divergence\n")
        manifest = self.manifest.copy()
        manifest["sha256"] = hashlib.sha256(document.read_bytes()).hexdigest()
        (peer / ".delivery-policy.json").write_text(json.dumps(manifest))
        result = self.run_gate("--peer", str(peer))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("policy drift", result.stderr)


if __name__ == "__main__":
    unittest.main()
