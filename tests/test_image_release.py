import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "image-release.py"
COMMIT = "47b72f4adfce6a43035a831b0b47c6504633f367"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class ImageReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.images = self.work / "images"
        self.packages = self.work / "packages"
        self.output = self.work / "assets"
        self.images.mkdir()
        self.packages.mkdir()
        self.lock = self.work / "release.lock.json"
        self.plan = {
            "schema_version": 1,
            "product": "dshanpi-r1",
            "version": "2026.10.10-1",
            "revision": "25.11.0-trunk.20261010.1",
            "sources": {
                "armbianos": {"commit": COMMIT},
                "dspi_config": {"commit": "69f441a1e7d01feaaf9c936cc5db6ac793805668"},
            },
            "image_release": {
                "repository": "dshanpi/ArmBianOS",
                "tag": "dshanpi-r1-2026.10.10-1",
                "target_commit": COMMIT,
                "title": "DShanPI R1 2026.10.10-1",
                "testing": {"draft": False, "prerelease": True},
                "stable": {"draft": False, "prerelease": False},
                "variants": [
                    {"name": "cli", "image": "cli.img", "asset": "cli.img.xz"},
                    {"name": "desktop", "image": "desktop.img", "asset": "desktop.img.xz"},
                ],
                "assets": [
                    "cli.img.xz",
                    "desktop.img.xz",
                    "SHA256SUMS",
                    "package-SHA256SUMS",
                    "release-lock.json",
                    "release-provenance.json",
                ],
            },
        }
        self.lock.write_text(json.dumps(self.plan))

    def run_script(self, *arguments):
        return subprocess.run(["python3", str(SCRIPT), *map(str, arguments)], capture_output=True, text=True)

    def build_package(self, name: str) -> Path:
        package_root = self.work / ("pkg-" + name)
        (package_root / "DEBIAN").mkdir(parents=True)
        (package_root / "usr" / "share" / name).mkdir(parents=True)
        (package_root / "usr" / "share" / name / "payload").write_text("fixture\n")
        (package_root / "DEBIAN" / "control").write_text(
            f"Package: {name}\nVersion: 1.2.3-1\nArchitecture: arm64\n"
            "Installed-Size: 1\nMaintainer: Test <test@example.invalid>\nDescription: test package\n"
        )
        target = self.packages / f"{name}_1.2.3-1_arm64.deb"
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(package_root), str(target)], check=True,
                       stdout=subprocess.DEVNULL)
        return target

    def test_rejects_target_commit_drift(self):
        self.plan["image_release"]["target_commit"] = "1" * 40
        self.lock.write_text(json.dumps(self.plan))
        result = self.run_script("validate", "dshanpi-r1", self.lock)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target_commit", result.stderr)

    def test_prepares_exact_deterministic_asset_set(self):
        for name, payload in (("cli.img", b"cli image\0" * 100), ("desktop.img", b"desktop image\0" * 100)):
            image = self.images / name
            image.write_bytes(payload)
            (self.images / (name + ".sha")).write_text(f"{sha256(image)} {name}\n")
        self.build_package("linux-headers-vendor-rk35xx")
        self.build_package("base-files")

        result = self.run_script("prepare", "dshanpi-r1", self.lock, self.images, self.packages, self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({path.name for path in self.output.iterdir()}, set(self.plan["image_release"]["assets"]))
        subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=self.output, check=True,
                       stdout=subprocess.DEVNULL)
        provenance = json.loads((self.output / "release-provenance.json").read_text())
        self.assertEqual(provenance["release"]["target_commit"], COMMIT)
        self.assertEqual(provenance["headers"]["package"], "linux-headers-vendor-rk35xx")
        self.assertIn("linux-headers-vendor-rk35xx=1.2.3-1", provenance["headers"]["apt_install"])
        self.assertEqual(provenance["initial_login"], {
            "username": "root",
            "password": "1234",
            "password_change_required": True,
        })
        notes = (self.work / "release-notes.md").read_text()
        self.assertIn("## Initial login", notes)
        self.assertIn("Username: `root`", notes)
        self.assertIn("Password: `1234`", notes)
        self.assertIn("requires setting a new root password", notes)


if __name__ == "__main__":
    unittest.main()
