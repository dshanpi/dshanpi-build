#!/usr/bin/env python3
"""Fetch one exact DEB cohort after verifying the signed public repository manifest."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9+.-]*")
SAFE_VERSION = re.compile(r"[A-Za-z0-9.+:~-]+")


def fail(message: str) -> None:
    raise ValueError(message)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or str(path) != value or ".." in path.parts:
        fail(f"unsafe repository path: {value}")
    return path


def fetch_stream(request: str | Request, temporary: Path, relative: str, expected_status: int) -> None:
    for attempt in range(5):
        try:
            with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                if response.status != expected_status:
                    fail(f"download failed with HTTP {response.status}: {relative}")
                shutil.copyfileobj(response, output, 1024 * 1024)
            return
        except HTTPError as error:
            temporary.unlink(missing_ok=True)
            if error.code in {400, 401, 403, 404}:
                fail(f"download failed with HTTP {error.code}: {relative}")
            if attempt == 4:
                raise
        except (OSError, http.client.IncompleteRead):
            temporary.unlink(missing_ok=True)
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)


def fetch_range(url: str, part: Path, relative: str, start: int, end: int) -> None:
    expected_size = end - start + 1
    for attempt in range(5):
        current = part.stat().st_size if part.exists() else 0
        if current == expected_size:
            return
        if current > expected_size:
            fail(f"range download exceeds expected size: {relative}")
        request = Request(url, headers={"Range": f"bytes={start + current}-{end}"})
        try:
            with urlopen(request, timeout=120) as response, part.open("ab") as output:
                if response.status != 206:
                    fail(f"range download failed with HTTP {response.status}: {relative}")
                shutil.copyfileobj(response, output, 1024 * 1024)
            if part.stat().st_size == expected_size:
                return
        except HTTPError as error:
            if error.code in {400, 401, 403, 404, 416}:
                fail(f"range download failed with HTTP {error.code}: {relative}")
            if attempt == 4:
                raise
        except (OSError, http.client.IncompleteRead):
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)
    fail(f"range download remained incomplete: {relative}")


def fetch(base_url: str, relative: str, destination: Path) -> None:
    url = base_url.rstrip("/") + "/" + quote(relative, safe="/")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    size = 0
    accepts_ranges = False
    try:
        with urlopen(Request(url, method="HEAD"), timeout=30) as response:
            size = int(response.headers.get("Content-Length", "0"))
            accepts_ranges = response.headers.get("Accept-Ranges", "").lower() == "bytes"
    except (OSError, ValueError):
        pass
    if size >= 8 * 1024 * 1024 and accepts_ranges:
        workers = min(8, max(2, (size + 16 * 1024 * 1024 - 1) // (16 * 1024 * 1024)))
        chunk = (size + workers - 1) // workers
        parts = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for index in range(workers):
                start = index * chunk
                end = min(size, start + chunk) - 1
                part = temporary.with_suffix(temporary.suffix + f".part{index}")
                parts.append(part)
                futures.append((executor.submit(fetch_range, url, part, relative, start, end), part, end - start + 1))
            for future, part, expected_size in futures:
                future.result()
                if part.stat().st_size != expected_size:
                    fail(f"range download size mismatch: {relative}")
        with temporary.open("wb") as output:
            for part in parts:
                with part.open("rb") as stream:
                    shutil.copyfileobj(stream, output, 1024 * 1024)
        if temporary.stat().st_size != size:
            fail(f"download size mismatch: {relative}")
        for part in parts:
            part.unlink()
    else:
        fetch_stream(url, temporary, relative, 200)
    temporary.replace(destination)


def make_keyring(public_key: Path, output: Path) -> None:
    result = subprocess.run(
        ["gpg", "--batch", "--yes", "--dearmor", "--output", str(output), str(public_key)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        output.write_bytes(public_key.read_bytes())


def package_field(path: Path, field: str) -> str:
    return subprocess.check_output(["dpkg-deb", "-f", str(path), field], text=True).strip()


def parse_checksums(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in path.read_text().splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            fail("invalid signed SHA256SUMS entry")
        relative = str(safe_relative(parts[1].lstrip(" *")))
        if relative in records:
            fail(f"duplicate signed path: {relative}")
        records[relative] = parts[0]
    return records


def fetch_release(
    base_url: str,
    product_config: Path,
    release_lock: Path,
    output: Path,
    public_key: Path,
) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        fail("public repository URL must be an HTTP(S) origin or path")
    product_data = json.loads(product_config.read_text())
    lock = json.loads(release_lock.read_text())
    product = lock.get("product")
    version = lock.get("version")
    if (
        product != product_data.get("product")
        or not isinstance(product, str)
        or not SAFE_NAME.fullmatch(product)
        or not isinstance(version, str)
        or not SAFE_VERSION.fullmatch(version)
    ):
        fail("product configuration and release lock do not match")
    if output.exists() and not output.is_dir():
        fail("package output path is not a directory")
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporary_name:
        temporary = Path(temporary_name)
        sums = temporary / "SHA256SUMS"
        signature = temporary / "SHA256SUMS.asc"
        keyring = temporary / "archive.gpg"
        fetch(base_url, "SHA256SUMS", sums)
        fetch(base_url, "SHA256SUMS.asc", signature)
        make_keyring(public_key, keyring)
        subprocess.run(
            ["gpgv", "--keyring", str(keyring), str(signature), str(sums)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        signed = parse_checksums(sums)
        manifest_relative = f"catalog/releases/{product}/{version}.json"
        expected_manifest = signed.get(manifest_relative)
        if expected_manifest is None:
            fail(f"release is absent from the signed public repository: {product} {version}")
        manifest_path = temporary / "release.json"
        fetch(base_url, manifest_relative, manifest_path)
        if digest(manifest_path) != expected_manifest:
            fail("release manifest differs from the signed repository checksum")
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest.get("product") != product
            or manifest.get("version") != version
            or manifest.get("suite") != product_data.get("testing_suite")
            or manifest.get("withdrawn_from") == manifest.get("suite")
        ):
            fail("release manifest identity or testing state is invalid")
        packages = manifest.get("packages")
        if not isinstance(packages, list) or not packages:
            fail("release manifest contains no packages")

        seen_identities: set[tuple[str, str, str]] = set()
        seen_names: set[str] = set()
        for item in packages:
            package = item.get("package")
            package_version = item.get("version")
            architecture = item.get("architecture")
            component = item.get("component")
            relative_text = item.get("filename")
            expected = item.get("sha256")
            if (
                not isinstance(package, str)
                or not SAFE_NAME.fullmatch(package)
                or not isinstance(package_version, str)
                or not SAFE_VERSION.fullmatch(package_version)
                or architecture not in {"arm64", "all"}
                or component not in {"common", product}
                or not isinstance(relative_text, str)
                or not isinstance(expected, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected)
            ):
                fail("release manifest contains an invalid package record")
            relative = safe_relative(relative_text)
            if len(relative.parts) < 3 or relative.parts[0:2] != ("pool", component):
                fail(f"package belongs to the wrong component: {relative}")
            if signed.get(str(relative)) != expected:
                fail(f"package is not bound by the signed repository checksum: {relative}")
            identity = package, package_version, architecture
            if identity in seen_identities or relative.name in seen_names:
                fail(f"duplicate package identity or filename: {package}")
            seen_identities.add(identity)
            seen_names.add(relative.name)
            destination = output / relative.name
            if destination.exists():
                if not destination.is_file() or digest(destination) != expected:
                    fail(f"existing package differs from the signed cohort: {relative.name}")
                print(f"reused verified package: {relative.name}")
            else:
                fetch(base_url, str(relative), destination)
            if digest(destination) != expected:
                fail(f"downloaded package checksum mismatch: {relative}")
            actual = tuple(package_field(destination, field) for field in ("Package", "Version", "Architecture"))
            if actual != identity:
                fail(f"downloaded package identity mismatch: {relative}")
            print(f"fetched signed package: {relative.name}")

        expected_required = {
            (entry["name"], entry["arch"]) for entry in product_data.get("required_packages", [])
        }
        actual_name_arch = {(name, arch) for name, _, arch in seen_identities}
        missing = sorted(expected_required - actual_name_arch)
        for meta in (
            product_data["release_meta"]["core"],
            product_data["release_meta"]["desktop"],
        ):
            if (meta, "all") not in actual_name_arch:
                missing.append((meta, "all"))
        if missing:
            fail(f"signed release is missing required packages: {missing}")
        unexpected = sorted(path.name for path in output.glob("*.deb") if path.name not in seen_names)
        if unexpected:
            fail(f"package directory contains files outside the signed cohort: {unexpected}")
        shutil.copyfile(manifest_path, output.parent / "public-release.json")

    checksum_path = output / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in sorted(output.glob("*.deb")))
    )
    print(f"fetched and verified {len(seen_identities)} signed packages for {product} {version}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("product_config", type=Path)
    parser.add_argument("release_lock", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("public_key", type=Path)
    args = parser.parse_args()
    try:
        fetch_release(
            args.base_url,
            args.product_config.resolve(),
            args.release_lock.resolve(),
            args.output.resolve(),
            args.public_key.resolve(),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"fetch-public-release: {error}")


if __name__ == "__main__":
    main()
