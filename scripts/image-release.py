#!/usr/bin/env python3
"""Validate a fixed image-release plan and prepare immutable release assets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
VERSION_RE = re.compile(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[1-9][0-9]*")
SHA_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
FIXED_ASSETS = {
    "SHA256SUMS",
    "package-SHA256SUMS",
    "release-lock.json",
    "release-provenance.json",
}


def fail(message: str) -> None:
    raise ValueError(message)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read JSON {path}: {error}")
    if not isinstance(value, dict):
        fail(f"JSON object required: {path}")
    return value


def safe_name(value: object, field: str) -> str:
    if not isinstance(value, str) or not SAFE_NAME_RE.fullmatch(value):
        fail(f"unsafe {field}: {value!r}")
    return value


def initial_login(product: str) -> dict:
    config = load_json(ROOT / "products" / product / "product.json")
    login = config.get("initial_login")
    if not isinstance(login, dict):
        fail("product initial_login documentation is required")
    username = safe_name(login.get("username"), "initial login username")
    password = safe_name(login.get("password"), "initial login password")
    if login.get("password_change_required") is not True:
        fail("initial login must require a password change")
    return {
        "username": username,
        "password": password,
        "password_change_required": True,
    }


def validate_plan(product: str, lock: dict) -> dict:
    if not PRODUCT_RE.fullmatch(product) or lock.get("product") != product:
        fail("release product mismatch")
    if lock.get("schema_version") != 1 or not VERSION_RE.fullmatch(str(lock.get("version", ""))):
        fail("invalid release lock identity")
    initial_login(product)
    source_commit = lock.get("sources", {}).get("armbianos", {}).get("commit", "")
    if not COMMIT_RE.fullmatch(str(source_commit)):
        fail("invalid ArmBianOS source commit")

    plan = lock.get("image_release")
    if not isinstance(plan, dict):
        fail("image_release plan is required for complete image delivery")
    if plan.get("repository") != "dshanpi/ArmBianOS":
        fail("image release repository must be dshanpi/ArmBianOS")
    if plan.get("target_commit") != source_commit:
        fail("image release target_commit must equal the pinned ArmBianOS commit")
    expected_tag = f"{product}-{lock['version']}"
    if plan.get("tag") != expected_tag:
        fail(f"image release tag must be {expected_tag}")
    if not isinstance(plan.get("title"), str) or not plan["title"].strip():
        fail("image release title is required")
    for channel, prerelease in (("testing", True), ("stable", False)):
        state = plan.get(channel)
        if state != {"draft": False, "prerelease": prerelease}:
            fail(f"image release {channel} state must fix draft=false and prerelease={str(prerelease).lower()}")

    variants = plan.get("variants")
    if not isinstance(variants, list) or len(variants) != 2:
        fail("image release must contain exactly CLI and desktop variants")
    names = set()
    raw_names = set()
    compressed_names = set()
    for variant in variants:
        if not isinstance(variant, dict):
            fail("invalid image variant")
        name = variant.get("name")
        if name not in {"cli", "desktop"} or name in names:
            fail("image variants must be unique cli and desktop entries")
        names.add(name)
        raw = safe_name(variant.get("image"), "image filename")
        asset = safe_name(variant.get("asset"), "image asset filename")
        if not raw.endswith(".img") or asset != raw + ".xz":
            fail("image assets must be the exact raw .img filename plus .xz")
        raw_names.add(raw)
        compressed_names.add(asset)
    if names != {"cli", "desktop"}:
        fail("image release variants are incomplete")

    assets = plan.get("assets")
    if not isinstance(assets, list) or any(not isinstance(item, str) for item in assets):
        fail("image release assets must be a list")
    if len(assets) != len(set(assets)):
        fail("image release asset names must be unique")
    for asset in assets:
        safe_name(asset, "release asset filename")
    expected_assets = compressed_names | FIXED_ASSETS
    if set(assets) != expected_assets:
        fail("image release assets do not exactly match variants and required provenance files")
    return plan


def deb_fields(path: Path) -> dict[str, str]:
    output = subprocess.check_output(
        ["dpkg-deb", "-f", str(path), "Package", "Version", "Architecture", "Installed-Size"],
        text=True,
    )
    fields = {}
    for line in output.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            fields[key] = value
    return fields


def apt_pool_path(component: str, package: str, filename: str) -> str:
    initial = "lib" + package[3] if package.startswith("lib") and len(package) > 3 else package[0]
    return f"pool/{component}/{initial}/{package}/{filename}"


def verify_sidecar(image: Path) -> str:
    sidecar = image.with_name(image.name + ".sha")
    if not sidecar.is_file():
        fail(f"image checksum sidecar is missing: {sidecar.name}")
    fields = sidecar.read_text().strip().split()
    if len(fields) != 2 or not SHA_RE.fullmatch(fields[0]) or Path(fields[1]).name != image.name:
        fail(f"invalid image checksum sidecar: {sidecar.name}")
    actual = digest(image)
    if actual != fields[0]:
        fail(f"image checksum mismatch: {image.name}")
    return actual


def compress_image(source: Path, target: Path) -> None:
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        with temporary.open("wb") as output_stream:
            subprocess.run(["xz", "-T0", "-3", "--stdout", str(source)], stdout=output_stream, check=True)
        subprocess.run(["xz", "-T0", "--test", str(temporary)], check=True)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare(product: str, lock_path: Path, images: Path, packages: Path, output: Path) -> None:
    lock = load_json(lock_path)
    plan = validate_plan(product, lock)
    login = initial_login(product)
    product_config = load_json(ROOT / "products" / product / "product.json")
    if not images.is_dir() or not packages.is_dir():
        fail("image and package directories must exist")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        fail(f"release asset directory must be empty: {output}")

    expected_images = {variant["image"] for variant in plan["variants"]}
    actual_images = {path.name for path in images.glob("*.img") if path.is_file()}
    if actual_images != expected_images:
        fail(f"raw image set mismatch: expected {sorted(expected_images)}, found {sorted(actual_images)}")

    image_records = []
    for variant in sorted(plan["variants"], key=lambda item: item["name"]):
        image = images / variant["image"]
        raw_sha = verify_sidecar(image)
        asset = output / variant["asset"]
        compress_image(image, asset)
        image_records.append(
            {
                "variant": variant["name"],
                "raw_image": image.name,
                "raw_bytes": image.stat().st_size,
                "raw_sha256": raw_sha,
                "asset": asset.name,
                "asset_bytes": asset.stat().st_size,
                "asset_sha256": digest(asset),
            }
        )

    package_records = []
    for package_path in sorted(packages.glob("*.deb"), key=lambda path: path.name):
        fields = deb_fields(package_path)
        package_records.append(
            {
                "filename": package_path.name,
                "package": fields["Package"],
                "version": fields["Version"],
                "architecture": fields["Architecture"],
                "bytes": package_path.stat().st_size,
                "sha256": digest(package_path),
            }
        )
    if not package_records:
        fail("release package directory contains no DEBs")
    package_sums = output / "package-SHA256SUMS"
    package_sums.write_text("".join(f"{item['sha256']}  {item['filename']}\n" for item in package_records))

    header_names = {
        item["name"] for item in product_config["required_packages"]
        if item["name"].startswith("linux-headers-")
    }
    headers = [item for item in package_records if item["package"] in header_names]
    if len(headers) != 1:
        fail(f"expected exactly one matching headers DEB, found {len(headers)}")
    header = headers[0]
    header_path = packages / header["filename"]
    header_fields = deb_fields(header_path)
    component = "common" if header["package"] in product_config["common_packages"] else product_config["component"]
    header.update(
        {
            "installed_size_kib": int(header_fields["Installed-Size"]),
            "apt_install": f"sudo apt-get install {header['package']}={header['version']}",
            "url": "https://apt.100ask.net/" + apt_pool_path(component, header["package"], header["filename"]),
        }
    )

    published_lock = output / "release-lock.json"
    shutil.copyfile(lock_path, published_lock)
    build_commit = os.environ.get("GITHUB_SHA")
    if not build_commit:
        build_commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if not COMMIT_RE.fullmatch(build_commit):
        fail("builder commit is not a full Git SHA")
    provenance = {
        "schema_version": 1,
        "product": product,
        "version": lock["version"],
        "revision": lock["revision"],
        "sources": lock["sources"],
        "builder": {"repository": "dshanpi/dshanpi-build", "commit": build_commit},
        "release": {
            "repository": plan["repository"],
            "tag": plan["tag"],
            "target_commit": plan["target_commit"],
        },
        "initial_login": login,
        "images": image_records,
        "headers": header,
        "packages": {
            "count": len(package_records),
            "sha256sums": package_sums.name,
            "sha256sums_sha256": digest(package_sums),
        },
        "release_lock_sha256": digest(published_lock),
    }
    provenance_path = output / "release-provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")

    checksummed = sorted(path for path in output.iterdir() if path.name != "SHA256SUMS")
    sums = output / "SHA256SUMS"
    sums.write_text("".join(f"{digest(path)}  {path.name}\n" for path in checksummed))
    if {path.name for path in output.iterdir()} != set(plan["assets"]):
        fail("prepared release assets differ from the fixed plan")

    notes = output.parent / "release-notes.md"
    variant_lines = "\n".join(
        f"- `{item['variant']}`: `{item['asset']}` — `{item['asset_sha256']}`"
        for item in image_records
    )
    notes.write_text(
        f"# {plan['title']}\n\n"
        "This is an automatically assembled testing image release. It remains a prerelease until the exact package cohort passes applicable physical-board validation.\n\n"
        "## Initial login\n\n"
        f"- Username: `{login['username']}`\n"
        f"- Password: `{login['password']}`\n"
        "- The first interactive login requires setting a new root password.\n\n"
        f"## Images\n\n{variant_lines}\n\n"
        "## Matching kernel headers\n\n"
        f"- Package: `{header['package']}={header['version']}` (`{header['architecture']}`)\n"
        f"- DEB: [{header['filename']}]({header['url']})\n"
        f"- SHA-256: `{header['sha256']}`\n"
        f"- Download size: `{header['bytes']}` bytes; Installed-Size: `{header['installed_size_kib']}` KiB\n"
        f"- Install after enabling the signed DShanPI source: `{header['apt_install']}`\n\n"
        "`release-provenance.json`, `release-lock.json`, `package-SHA256SUMS`, and `SHA256SUMS` bind the images to their source and package cohort.\n"
    )
    print(json.dumps(provenance, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("product")
    validate.add_argument("lock", type=Path)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("product")
    prepare_parser.add_argument("lock", type=Path)
    prepare_parser.add_argument("images", type=Path)
    prepare_parser.add_argument("packages", type=Path)
    prepare_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        validate_plan(args.product, load_json(args.lock.resolve()))
        print(f"validated image release plan: {args.product}")
    else:
        prepare(
            args.product,
            args.lock.resolve(),
            args.images.resolve(),
            args.packages.resolve(),
            args.output.resolve(),
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"image-release: {error}", file=sys.stderr)
        raise SystemExit(1)
