from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load_module("cohort_fixture", ROOT / "tests/test_fetch_public_release.py")


class PublicProductVerifyTests(unittest.TestCase):
    build_deb = fixtures.PublicReleaseFetchTests.build_deb
    digest = staticmethod(fixtures.PublicReleaseFetchTests.digest)
    tearDown = fixtures.PublicReleaseFetchTests.tearDown

    def setUp(self):
        fixtures.PublicReleaseFetchTests.setUp(self)
        self.verifier = load_module("public_verifier", ROOT / "scripts/verify-product-public.py")
        self.verifier.ROOT = self.root
        config = self.root / "products" / self.product / "product.json"
        config.parent.mkdir(parents=True)
        shutil.copyfile(self.config, config)
        (self.root / "keys").mkdir()
        shutil.copyfile(self.public_key, self.root / "keys/dshanpi-archive.asc")
        self.manifest = self.repository / "catalog/releases" / self.product / f"{self.version}.json"
        self.sign_manifest()

    def sign_manifest(self):
        subprocess.run([
            "gpg", "--batch", "--yes", "--homedir", str(self.gnupg), "--armor", "--detach-sign",
            "--output", str(self.manifest) + ".asc", str(self.manifest),
        ], check=True)

    def run_verify(self, cache=None):
        arguments = ["verify-product-public.py", self.product, self.version, "--base-url", self.url]
        if cache is not None:
            arguments += ["--cache-dir", str(cache)]
        output = io.StringIO()
        with patch.object(sys, "argv", arguments), redirect_stdout(output), redirect_stderr(io.StringIO()):
            self.verifier.main()
        result = json.loads(output.getvalue())
        self.assertEqual(result["public_manifest_signature"], "verified")
        self.assertEqual(len(result["packages"]), len(self.package_names))

    def test_default_verifies_public_cohort(self):
        self.run_verify()

    def test_cache_reuses_verified_bytes_without_package_requests(self):
        cache = self.root / "cache"
        self.run_verify(cache)
        self.assertEqual(len(list(cache.glob("*.deb"))), len(self.package_names))
        with patch.object(self.verifier, "fetch", wraps=self.verifier.fetch) as fetcher:
            self.run_verify(cache)
        self.assertTrue(fetcher.call_args_list)
        self.assertFalse(any(call.args[1].startswith("pool/") for call in fetcher.call_args_list))

    def test_corrupt_cache_is_refetched(self):
        cache = self.root / "cache"
        self.run_verify(cache)
        package = next(cache.glob("*.deb"))
        package.write_bytes(b"corrupt cached bytes")
        with patch.object(self.verifier, "fetch", wraps=self.verifier.fetch) as fetcher:
            self.run_verify(cache)
        self.assertEqual(sum(call.args[1].startswith("pool/") for call in fetcher.call_args_list), 1)
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), package.stem)

    def test_rejects_unsafe_signed_hash(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["packages"][0]["sha256"] = "../outside"
        self.manifest.write_text(json.dumps(manifest))
        self.sign_manifest()
        with self.assertRaisesRegex(SystemExit, "invalid public package hash"):
            self.run_verify(self.root / "cache")


if __name__ == "__main__":
    unittest.main()
