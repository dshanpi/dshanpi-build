import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("snapshot", Path(__file__).parents[1] / "scripts/pages/snapshot.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.original_chunk = snapshot.CHUNK
        snapshot.CHUNK = 16
        self.addCleanup(setattr, snapshot, "CHUNK", self.original_chunk)

    def encode(self):
        snapshot.encode(self.source, self.root / "snapshot")

    def test_multichunk_roundtrip_and_empty_file(self):
        data = bytes(range(99))
        (self.source / "payload.deb").write_bytes(data)
        (self.source / "empty").touch()
        self.encode()
        snapshot.decode(self.root / "snapshot", self.root / "restored")
        self.assertEqual((self.root / "restored/payload.deb").read_bytes(), data)
        self.assertEqual((self.root / "restored/empty").read_bytes(), b"")

    def test_tampering_rejected(self):
        (self.source / "data").write_bytes(b"package")
        self.encode()
        next((self.root / "snapshot/objects").iterdir()).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            snapshot.decode(self.root / "snapshot", self.root / "restored")

    def test_path_traversal_rejected(self):
        (self.source / "data").write_bytes(b"package")
        self.encode()
        manifest = self.root / "snapshot/manifest.json"
        data = json.loads(manifest.read_text())
        data["files"][0]["path"] = "../escape"
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            snapshot.decode(self.root / "snapshot", self.root / "restored")
        self.assertFalse((self.root / "escape").exists())

    def test_symlink_rejected(self):
        (self.source / "link").symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            self.encode()

    def test_capacity_rejected(self):
        previous_limit = snapshot.LIMIT
        self.addCleanup(setattr, snapshot, "LIMIT", previous_limit)
        snapshot.LIMIT = 4
        (self.source / "data").write_bytes(b"too large")
        with self.assertRaises(ValueError):
            self.encode()


if __name__ == "__main__":
    unittest.main()
