#!/usr/bin/env python3
"""Verify a signed public product manifest and every exact release DEB."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://apt.100ask.net/"


def fetch(base: str, relative: str, destination: Path) -> None:
    if relative.startswith("/") or ".." in relative.split("/"):
        raise SystemExit("unsafe public repository path")
    for attempt in range(6):
        try:
            request = urllib.request.Request(base + relative, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            return
        except OSError:
            if attempt == 5:
                raise
            time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product")
    parser.add_argument("version")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.product):
        raise SystemExit("invalid product")
    if not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[1-9][0-9]*", args.version):
        raise SystemExit("invalid version")
    base = args.base_url.rstrip("/") + "/"
    config_path = ROOT / "products" / args.product / "product.json"
    if not config_path.is_file():
        raise SystemExit("unknown product")
    config = json.loads(config_path.read_text())

    with tempfile.TemporaryDirectory(prefix="dshanpi-product-public-") as temporary:
        work = Path(temporary)
        key = work / "archive.gpg"
        subprocess.run(
            ["gpg", "--batch", "--yes", "--dearmor", "--output", str(key), str(ROOT / "keys/dshanpi-archive.asc")],
            check=True,
        )
        relative = f"catalog/releases/{args.product}/{args.version}.json"
        manifest = work / "manifest.json"
        signature = work / "manifest.asc"
        fetch(base, relative, manifest)
        fetch(base, relative + ".asc", signature)
        subprocess.run(["gpgv", "--keyring", str(key), str(signature), str(manifest)], check=True)
        data = json.loads(manifest.read_text())
        if data.get("product") != args.product or data.get("version") != args.version or data.get("withdrawn_from"):
            raise SystemExit("unexpected public release identity or state")

        required = {(item["name"], item["arch"]) for item in config["required_packages"]}
        required |= {
            (config["release_meta"]["core"], "all"),
            (config["release_meta"]["desktop"], "all"),
        }
        actual = {(item["package"], item["architecture"]) for item in data["packages"]}
        allowed = set(required)
        for name, items in config.get("optional_package_sets", {}).items():
            members = {(item["name"], item["arch"]) for item in items}
            if actual & members:
                if not members <= actual:
                    raise SystemExit(f"public optional package set is incomplete: {name}")
                allowed |= members
        if not required <= actual or not actual <= allowed:
            missing = sorted(required - actual)
            extra = sorted(actual - allowed)
            raise SystemExit(f"public package cohort mismatch; missing={missing}, extra={extra}")

        results = []
        for index, package in enumerate(data["packages"]):
            target = work / f"package-{index}.deb"
            fetch(base, package["filename"], target)
            with target.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            if checksum != package["sha256"]:
                raise SystemExit(f"public package hash mismatch: {package['package']}")
            output = subprocess.check_output(
                ["dpkg-deb", "-f", str(target), "Package", "Version", "Architecture"], text=True
            )
            fields = dict(line.split(": ", 1) for line in output.splitlines())
            expected = {
                "Package": package["package"],
                "Version": package["version"],
                "Architecture": package["architecture"],
            }
            if fields != expected:
                raise SystemExit(f"public package identity mismatch: {package['package']}")
            results.append({"package": package["package"], "version": package["version"], "sha256": checksum})
        print(json.dumps({"public_manifest_signature": "verified", "packages": results}, indent=2))


if __name__ == "__main__":
    main()
