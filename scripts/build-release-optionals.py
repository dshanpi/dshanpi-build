#!/usr/bin/env python3
"""Build release-bound optional package sets from one product release lock."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def deb_field(path: Path, field: str) -> str:
    return subprocess.check_output(['dpkg-deb', '-f', str(path), field], text=True).strip()


def release_package_version(upstream_version: str, release_version: str) -> str:
    suffix = release_version.replace('-', '.')
    version = f'{upstream_version}+dshanpi.{suffix}'
    if subprocess.run(['dpkg', '--validate-version', version], capture_output=True).returncode:
        raise ValueError('derived optional package version is invalid')
    return version


def find_package(repository: Path, expected: dict) -> Path:
    matches = []
    pattern = f"pool/*/*/{expected['package']}/*.deb"
    for path in repository.glob(pattern):
        identity = {
            'package': deb_field(path, 'Package'),
            'version': deb_field(path, 'Version'),
            'architecture': deb_field(path, 'Architecture'),
        }
        if identity == {key: expected[key] for key in identity}:
            if sha256(path) != expected['sha256']:
                raise ValueError(f'pinned package identity has changed bytes: {path}')
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(
            f"expected one pinned {expected['package']} package in signed repository, found {len(matches)}"
        )
    return matches[0]


def build_axcl_16g(release_lock: dict, repository: Path, output: Path) -> None:
    component_lock = json.loads((ROOT / 'packages/axcl-16g/upstream.lock.json').read_text())
    package_version = release_package_version(component_lock['upstream_version'], release_lock['version'])
    previous_driver = find_package(repository, component_lock['source_driver'])
    retained = component_lock['retained_packages']
    previous_runtime = find_package(repository, {
        'package': 'dshanpi-axcl-runtime-16g', **retained['dshanpi-axcl-runtime-16g']})
    previous_firmware = find_package(repository, {
        'package': 'dshanpi-axcl-firmware-16g', **retained['dshanpi-axcl-firmware-16g']})
    subprocess.run([
        'python3', str(ROOT / 'scripts/build-axcl-16g-packages.py'), str(output),
        '--previous-driver', str(previous_driver),
        '--previous-runtime', str(previous_runtime),
        '--previous-firmware', str(previous_firmware),
        '--package-version', package_version,
        '--platform-version', release_lock['revision'],
    ], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product')
    parser.add_argument('release_lock', type=Path)
    parser.add_argument('repository', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    config = json.loads((ROOT / 'products' / args.product / 'product.json').read_text())
    release_lock = json.loads(args.release_lock.read_text())
    if release_lock.get('product') != args.product:
        raise SystemExit('release product mismatch')
    selected = config.get('release_package_sets', [])
    if len(selected) != len(set(selected)):
        raise SystemExit('duplicate release package set')
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise SystemExit('optional package output directory must be empty')
    for package_set in selected:
        if package_set == 'axcl-16g':
            build_axcl_16g(release_lock, args.repository.resolve(), args.output.resolve())
        else:
            raise SystemExit(f'unknown release package set: {package_set}')
    if selected:
        subprocess.run([str(ROOT / 'scripts/audit-packages.sh'), str(args.output)], check=True)


if __name__ == '__main__':
    main()
