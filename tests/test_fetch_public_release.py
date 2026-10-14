import hashlib
import http.server
import json
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch-public-release.py"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format, *args):
        pass


class PublicReleaseFetchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gnupg = self.root / "gnupg"
        self.gnupg.mkdir(mode=0o700)
        subprocess.run(
            [
                "gpg", "--batch", "--homedir", str(self.gnupg), "--passphrase", "",
                "--quick-gen-key", "Fetch Test <fetch@example.invalid>", "rsa2048", "sign", "0",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.public_key = self.root / "public.asc"
        with self.public_key.open("wb") as output:
            subprocess.run(
                ["gpg", "--batch", "--homedir", str(self.gnupg), "--armor", "--export"],
                check=True,
                stdout=output,
            )
        self.repository = self.root / "repository"
        self.product = "fixture-board"
        self.version = "2026.10.14-1"
        self.package_names = [
            "base-files", "fixture-required", "dspi-config", "dshanpi-archive-keyring",
            f"{self.product}-repository", f"{self.product}-release-core",
            f"{self.product}-release-desktop",
        ]
        records = []
        for package in self.package_names:
            component = "common" if package in {"dspi-config", "dshanpi-archive-keyring"} else self.product
            architecture = "arm64" if package in {"base-files", "fixture-required"} else "all"
            relative = Path("pool") / component / package[0] / package / f"{package}_1.0-1_{architecture}.deb"
            target = self.repository / relative
            self.build_deb(target, package, architecture)
            records.append(
                {
                    "package": package,
                    "version": "1.0-1",
                    "architecture": architecture,
                    "component": component,
                    "filename": relative.as_posix(),
                    "sha256": self.digest(target),
                }
            )
        manifest_relative = Path("catalog/releases") / self.product / f"{self.version}.json"
        manifest = self.repository / manifest_relative
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps(
                {
                    "product": self.product,
                    "version": self.version,
                    "suite": "noble-testing",
                    "packages": records,
                }
            )
            + "\n"
        )
        files = sorted(path for path in self.repository.rglob("*") if path.is_file())
        sums = self.repository / "SHA256SUMS"
        sums.write_text(
            "".join(f"{self.digest(path)}  {path.relative_to(self.repository).as_posix()}\n" for path in files)
        )
        subprocess.run(
            [
                "gpg", "--batch", "--homedir", str(self.gnupg), "--armor", "--detach-sign",
                "--output", str(self.repository / "SHA256SUMS.asc"), str(sums),
            ],
            check=True,
        )
        self.config = self.root / "product.json"
        self.config.write_text(
            json.dumps(
                {
                    "product": self.product,
                    "testing_suite": "noble-testing",
                    "required_packages": [
                        {"name": "base-files", "arch": "arm64"},
                        {"name": "fixture-required", "arch": "arm64"},
                        {"name": "dspi-config", "arch": "all"},
                        {"name": "dshanpi-archive-keyring", "arch": "all"},
                        {"name": f"{self.product}-repository", "arch": "all"},
                    ],
                    "release_meta": {
                        "core": f"{self.product}-release-core",
                        "desktop": f"{self.product}-release-desktop",
                    },
                }
            )
        )
        self.lock = self.root / "release.lock.json"
        self.lock.write_text(json.dumps({"product": self.product, "version": self.version}))
        handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(self.repository), **kwargs)
        self.server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def build_deb(self, target: Path, package: str, architecture: str):
        package_root = self.root / "build" / package
        (package_root / "DEBIAN").mkdir(parents=True)
        (package_root / "usr/share" / package).mkdir(parents=True)
        (package_root / "DEBIAN/control").write_text(
            f"Package: {package}\nVersion: 1.0-1\nArchitecture: {architecture}\n"
            "Maintainer: Test <test@example.invalid>\nDescription: fixture\n"
        )
        (package_root / "usr/share" / package / "payload").write_text(package)
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "--build", str(package_root), str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def run_fetch(self, output: Path):
        return subprocess.run(
            [
                "python3", str(SCRIPT), self.url, str(self.config), str(self.lock),
                str(output), str(self.public_key),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_fetches_only_signed_exact_cohort(self):
        output = self.root / "output/packages"
        result = self.run_fetch(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(output.glob("*.deb"))), len(self.package_names))
        self.assertTrue((output / "SHA256SUMS").is_file())
        self.assertTrue((output.parent / "public-release.json").is_file())
        second = self.run_fetch(output)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("reused verified package", second.stdout)

    def test_rejects_existing_unsigned_extra_package(self):
        output = self.root / "extra/packages"
        first = self.run_fetch(output)
        self.assertEqual(first.returncode, 0, first.stderr)
        extra = output / "unlisted_1.0-1_all.deb"
        self.build_deb(extra, "unlisted", "all")
        second = self.run_fetch(output)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("outside the signed cohort", second.stderr)

    def test_rejects_package_changed_after_signed_manifest(self):
        package = next(self.repository.glob("pool/**/*.deb"))
        package.write_bytes(package.read_bytes() + b"tampered")
        result = self.run_fetch(self.root / "tampered/packages")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
