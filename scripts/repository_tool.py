#!/usr/bin/env python3
import argparse
import datetime as dt
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def fail(message: str) -> None:
    raise SystemExit(f"repository-tool: {message}")


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def deb_fields(path: Path) -> dict[str, str]:
    output = subprocess.check_output(["dpkg-deb", "-f", str(path)], text=True)
    fields: dict[str, str] = {}
    key = None
    for line in output.splitlines():
        if line[:1].isspace() and key:
            fields[key] += "\n" + line
        elif ":" in line:
            key, value = line.split(":", 1)
            fields[key] = value.lstrip()
    for required in ("Package", "Version", "Architecture"):
        if not fields.get(required):
            fail(f"{path} has no {required}")
    return fields


def identity(entry: dict[str, str]) -> tuple[str, str, str]:
    return entry["package"], entry["version"], entry["architecture"]


def read_catalog(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    entries = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            fail(f"invalid catalog line {path}:{number}")
        package, version, architecture, filename, sha256 = parts
        entries.append({
            "package": package,
            "version": version,
            "architecture": architecture,
            "filename": filename,
            "sha256": sha256,
        })
    return entries


def write_catalog(path: Path, entries: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = sorted(entries, key=lambda item: identity(item))
    data = "".join(
        "\t".join((item["package"], item["version"], item["architecture"], item["filename"], item["sha256"])) + "\n"
        for item in entries
    )
    path.write_text(data)


def merge_catalog(path: Path, additions: list[dict[str, str]]) -> None:
    entries = read_catalog(path)
    known = {identity(item): item for item in entries}
    for item in additions:
        key = identity(item)
        if key in known and known[key] != item:
            fail(f"package identity changed content: {'/'.join(key)}")
        if key not in known:
            known[key] = item
    write_catalog(path, list(known.values()))


def pool_path(component: str, fields: dict[str, str], filename: str) -> Path:
    package = fields["Package"]
    initial = "lib" + package[3] if package.startswith("lib") and len(package) > 3 else package[0]
    return Path("pool") / component / initial / package / filename


def load_product(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or data.get("product") != path.parent.name:
        fail(f"invalid product config: {path}")
    return data


def add_release(args: argparse.Namespace) -> None:
    repo = args.repository.resolve()
    package_dir = args.packages.resolve()
    config = load_product(args.config.resolve())
    product = config["product"]
    if not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[1-9][0-9]*", args.version):
        fail(f"invalid release version: {args.version}")
    suite = config["testing_suite"]
    common = set(config["common_packages"])
    required = {(item["name"], item["arch"]) for item in config["required_packages"]}
    required |= {
        (config["release_meta"]["core"], "all"),
        (config["release_meta"]["desktop"], "all"),
    }
    found: dict[tuple[str, str], list[Path]] = {}
    for deb in sorted(package_dir.glob("*.deb")):
        fields = deb_fields(deb)
        for pattern in config["forbidden_package_patterns"]:
            if re.search(pattern, fields["Package"]):
                fail(f"forbidden OTA package: {fields['Package']}")
        found.setdefault((fields["Package"], fields["Architecture"]), []).append(deb)
    for key in required:
        if len(found.get(key, [])) != 1:
            fail(f"expected exactly one required package {key[0]}/{key[1]}")
    unexpected = sorted(set(found) - required)
    if unexpected:
        fail("unexpected package in release directory: " + ", ".join(f"{name}/{arch}" for name, arch in unexpected))
    for meta_name in (config["release_meta"]["core"], config["release_meta"]["desktop"]):
        meta = found[(meta_name, "all")][0]
        if deb_fields(meta)["Version"] != args.version:
            fail(f"release meta-package version does not match release: {meta_name}")

    repo.mkdir(parents=True, exist_ok=True)
    additions: dict[str, list[dict[str, str]]] = {}
    release_entries = []
    for key in sorted(required):
        deb = found[key][0]
        fields = deb_fields(deb)
        component = "common" if fields["Package"] in common else config["component"]
        relative = pool_path(component, fields, deb.name)
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source_hash = digest(deb)
        if target.exists() and digest(target) != source_hash:
            fail(f"immutable pool collision: {relative}")
        if not target.exists():
            shutil.copy2(deb, target)
        entry = {
            "package": fields["Package"],
            "version": fields["Version"],
            "architecture": fields["Architecture"],
            "filename": relative.as_posix(),
            "sha256": source_hash,
        }
        additions.setdefault(component, []).append(entry)
        release_entries.append({**entry, "component": component})

    for component, entries in additions.items():
        merge_catalog(repo / "catalog" / "suites" / suite / f"{component}.tsv", entries)
    manifest = {
        "schema_version": 1,
        "product": product,
        "version": args.version,
        "channel": "testing",
        "suite": suite,
        "packages": sorted(release_entries, key=lambda item: identity(item)),
    }
    manifest_path = repo / "catalog" / "releases" / product / f"{args.version}.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        fail(f"release manifest already exists with different content: {manifest_path}")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def promote_release(args: argparse.Namespace) -> None:
    repo = args.repository.resolve()
    config = load_product(args.config.resolve())
    product = config["product"]
    manifest_path = repo / "catalog" / "releases" / product / f"{args.version}.json"
    if not manifest_path.exists():
        fail(f"testing release manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("product") != product or manifest.get("version") != args.version:
        fail("testing release manifest identity mismatch")
    stable_suite = config["codename"]
    grouped: dict[str, list[dict[str, str]]] = {}
    for package in manifest["packages"]:
        entry = {key: package[key] for key in ("package", "version", "architecture", "filename", "sha256")}
        payload = repo / entry["filename"]
        if not payload.is_file() or digest(payload) != entry["sha256"]:
            fail(f"testing payload changed or is missing: {entry['filename']}")
        grouped.setdefault(package["component"], []).append(entry)
    for component, entries in grouped.items():
        merge_catalog(repo / "catalog" / "suites" / stable_suite / f"{component}.tsv", entries)
    manifest["promoted_to"] = stable_suite
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def withdraw_release(args: argparse.Namespace) -> None:
    repo = args.repository.resolve()
    config = load_product(args.config.resolve())
    product = config["product"]
    suite = config["testing_suite"]
    component = config["component"]
    manifest_path = repo / "catalog" / "releases" / product / f"{args.version}.json"
    if not manifest_path.exists():
        fail(f"testing release manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    remove = {
        identity(package)
        for package in manifest.get("packages", [])
        if package.get("component") == component
    }
    catalog_path = repo / "catalog" / "suites" / suite / f"{component}.tsv"
    remaining = [entry for entry in read_catalog(catalog_path) if identity(entry) not in remove]
    write_catalog(catalog_path, remaining)
    manifest["withdrawn_from"] = suite
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def control_paragraph(path: Path, relative: str) -> str:
    fields = deb_fields(path)
    excluded = {"Filename", "Size", "MD5sum", "SHA1", "SHA256"}
    lines = []
    for key, value in fields.items():
        if key in excluded:
            continue
        value_lines = value.splitlines() or [""]
        lines.append(f"{key}: {value_lines[0]}")
        lines.extend(value_lines[1:])
    lines.extend([
        f"Filename: {relative}",
        f"Size: {path.stat().st_size}",
        f"MD5sum: {digest(path, 'md5')}",
        f"SHA1: {digest(path, 'sha1')}",
        f"SHA256: {digest(path, 'sha256')}",
    ])
    return "\n".join(lines) + "\n\n"


def render(args: argparse.Namespace) -> None:
    repo = args.repository.resolve()
    suites_root = repo / "catalog" / "suites"
    for suite in args.ensure_suite:
        (suites_root / suite).mkdir(parents=True, exist_ok=True)
    for component in args.ensure_component:
        for suite in args.ensure_suite:
            catalog = suites_root / suite / f"{component}.tsv"
            if not catalog.exists():
                write_catalog(catalog, [])

    for suite_dir in sorted(path for path in suites_root.iterdir() if path.is_dir()):
        suite = suite_dir.name
        dist = repo / "dists" / suite
        if dist.exists():
            shutil.rmtree(dist)
        components = []
        architectures = set()
        for catalog in sorted(suite_dir.glob("*.tsv")):
            component = catalog.stem
            components.append(component)
            entries = read_catalog(catalog)
            for arch in ("arm64", "all"):
                architectures.add(arch)
                binary_dir = dist / component / f"binary-{arch}"
                binary_dir.mkdir(parents=True, exist_ok=True)
                paragraphs = []
                for entry in entries:
                    if entry["architecture"] != arch:
                        continue
                    payload = repo / entry["filename"]
                    if not payload.is_file() or digest(payload) != entry["sha256"]:
                        fail(f"catalog payload mismatch: {entry['filename']}")
                    paragraphs.append((identity(entry), control_paragraph(payload, entry["filename"])))
                data = "".join(paragraph for _, paragraph in sorted(paragraphs)).encode()
                packages = binary_dir / "Packages"
                packages.write_bytes(data)
                with (binary_dir / "Packages.gz").open("wb") as compressed:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as output:
                        output.write(data)
                (binary_dir / "Packages.xz").write_bytes(lzma.compress(data, format=lzma.FORMAT_XZ, preset=9))

        epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "1790726400"))
        date = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
        fields = [
            "Origin: DShanPI",
            "Label: DShanPI",
            f"Suite: {suite}",
            f"Codename: {suite}",
            f"Date: {date}",
            f"Architectures: {' '.join(sorted(architectures))}",
            f"Components: {' '.join(sorted(components))}",
            "Description: DShanPI signed platform packages",
            "NotAutomatic: yes",
            "ButAutomaticUpgrades: no",
        ]
        indexed = sorted(
            path for path in dist.rglob("*")
            if path.is_file() and path.name not in {"Release", "InRelease", "Release.gpg"}
        )
        for algorithm, label in (("md5", "MD5Sum"), ("sha1", "SHA1"), ("sha256", "SHA256")):
            fields.append(f"{label}:")
            for path in indexed:
                relative = path.relative_to(dist).as_posix()
                fields.append(f" {digest(path, algorithm)} {path.stat().st_size:16d} {relative}")
        (dist / "Release").write_text("\n".join(fields) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("config", type=Path)
    add.add_argument("version")
    add.add_argument("packages", type=Path)
    add.add_argument("repository", type=Path)
    add.set_defaults(func=add_release)
    promote = commands.add_parser("promote")
    promote.add_argument("config", type=Path)
    promote.add_argument("version")
    promote.add_argument("repository", type=Path)
    promote.set_defaults(func=promote_release)
    withdraw = commands.add_parser("withdraw")
    withdraw.add_argument("config", type=Path)
    withdraw.add_argument("version")
    withdraw.add_argument("repository", type=Path)
    withdraw.set_defaults(func=withdraw_release)
    render_command = commands.add_parser("render")
    render_command.add_argument("repository", type=Path)
    render_command.add_argument("--ensure-suite", action="append", default=[])
    render_command.add_argument("--ensure-component", action="append", default=[])
    render_command.set_defaults(func=render)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
