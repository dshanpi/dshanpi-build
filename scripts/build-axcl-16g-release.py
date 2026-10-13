#!/usr/bin/env python3
"""Assemble an A1 package maintenance release using verified historical bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('version')
    p.add_argument('repository', type=Path)
    p.add_argument('--upstream', type=Path)
    args = p.parse_args()
    run = lambda *cmd: subprocess.run(list(map(str, cmd)), check=True)
    run('python3', ROOT / 'tools/check-delivery-policy.py')
    lock_path = ROOT / 'products/dshanpi-a1/releases' / (args.version + '.lock.json')
    lock = json.loads(lock_path.read_text())
    if lock.get('maintenance_adapter') != 'axcl-16g' or lock.get('product') != 'dshanpi-a1':
        raise SystemExit('not an A1 AXCL 16GB maintenance plan')
    axcl_lock_path = ROOT / 'packages/axcl-16g/upstream.lock.json'
    if hashlib.sha256(axcl_lock_path.read_bytes()).hexdigest() != lock['axcl_16g_lock_sha256']:
        raise SystemExit('AXCL 16GB inputs differ from release plan')
    axcl_lock = json.loads(axcl_lock_path.read_text())
    run(ROOT / 'scripts/validate-config.sh', 'dshanpi-a1', lock_path)
    repo = args.repository.resolve()
    run('python3', ROOT / 'scripts/verify-repository.py', '--snapshot', repo, ROOT / 'keys/dshanpi-archive.asc', repo)
    manifest = repo / 'catalog/releases/dshanpi-a1' / (lock['base_release'] + '.json')
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != lock['base_manifest_sha256']:
        raise SystemExit('base release manifest hash mismatch')
    axcl_manifest = repo / 'catalog/releases/dshanpi-a1' / (lock['axcl_source_release'] + '.json')
    if hashlib.sha256(axcl_manifest.read_bytes()).hexdigest() != lock['axcl_source_manifest_sha256']:
        raise SystemExit('AXCL source release manifest hash mismatch')
    output = ROOT / 'output/dshanpi-a1' / args.version / 'packages'
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit('output directory must be empty')
    config = json.loads((ROOT / 'products/dshanpi-a1/product.json').read_text())
    required = {(x['name'], x['arch']) for x in config['required_packages']}
    # Retain unrelated optional cohorts when they are present in the platform
    # base. The target AXCL runtime and firmware are pulled from their own
    # verified source release below; only driver and meta are rebuilt.
    for name, members in config.get('optional_package_sets', {}).items():
        if name != 'axcl-16g':
            required.update((x['name'], x['arch']) for x in members)
    for package in json.loads(manifest.read_text())['packages']:
        if (package['package'], package['architecture']) not in required:
            continue
        relative = Path(package['filename'])
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit('unsafe package path')
        source = repo / relative
        with source.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != package['sha256']:
                raise SystemExit('historical package hash mismatch')
        shutil.copyfile(source, output / source.name)
    retained = axcl_lock['retained_packages']
    source_driver = axcl_lock['source_driver']
    previous_driver = None
    copied_retained = set()
    for package in json.loads(axcl_manifest.read_text())['packages']:
        expected = retained.get(package['package'])
        is_driver = package['package'] == source_driver['package']
        if expected is None and not is_driver:
            continue
        identity = source_driver if is_driver else expected
        if package['version'] != identity['version'] or package['architecture'] != identity['architecture'] or package['sha256'] != identity['sha256']:
            raise SystemExit(f'AXCL historical identity mismatch: {package["package"]}')
        relative = Path(package['filename'])
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit('unsafe AXCL package path')
        source = repo / relative
        with source.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != package['sha256']:
                raise SystemExit('historical AXCL package hash mismatch')
        if is_driver:
            if previous_driver is not None:
                raise SystemExit('duplicate AXCL source driver in release manifest')
            previous_driver = source
        else:
            if package['package'] in copied_retained:
                raise SystemExit(f'duplicate retained AXCL package: {package["package"]}')
            shutil.copyfile(source, output / source.name)
            copied_retained.add(package['package'])
    if previous_driver is None or copied_retained != set(retained):
        raise SystemExit('AXCL historical source cohort is incomplete')
    cmd = ['python3', ROOT / 'scripts/build-axcl-16g-packages.py', output]
    if args.upstream:
        cmd += ['--upstream', args.upstream]
    else:
        cmd += ['--previous-driver', previous_driver]
    cmd += [
        '--package-version', axcl_lock['version'],
        '--platform-version', lock['revision'],
    ]
    run(*cmd)
    run(ROOT / 'scripts/build-release-meta.sh', 'dshanpi-a1', args.version, output)
    run(ROOT / 'scripts/audit-packages.sh', output)
    with (output / 'SHA256SUMS').open('w') as sums:
        for deb in sorted(output.glob('*.deb')):
            with deb.open('rb') as f:
                sums.write(hashlib.file_digest(f, 'sha256').hexdigest() + '  ' + deb.name + '\n')
    print(output)


if __name__ == '__main__':
    main()
