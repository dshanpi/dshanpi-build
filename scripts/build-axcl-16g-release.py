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
    if hashlib.sha256((ROOT / 'packages/axcl-16g/upstream.lock.json').read_bytes()).hexdigest() != lock['axcl_16g_lock_sha256']:
        raise SystemExit('AXCL 16GB inputs differ from release plan')
    run(ROOT / 'scripts/validate-config.sh', 'dshanpi-a1', lock_path)
    repo = args.repository.resolve()
    run('python3', ROOT / 'scripts/verify-repository.py', '--snapshot', repo, ROOT / 'keys/dshanpi-archive.asc', repo)
    manifest = repo / 'catalog/releases/dshanpi-a1' / (lock['base_release'] + '.json')
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != lock['base_manifest_sha256']:
        raise SystemExit('base release manifest hash mismatch')
    output = ROOT / 'output/dshanpi-a1' / args.version / 'packages'
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit('output directory must be empty')
    config = json.loads((ROOT / 'products/dshanpi-a1/product.json').read_text())
    required = {(x['name'], x['arch']) for x in config['required_packages']}
    # Retain existing optional cohorts (AXCL) unchanged in this maintenance release.
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
    cmd = ['python3', ROOT / 'scripts/build-axcl-16g-packages.py', output]
    if args.upstream:
        cmd += ['--upstream', args.upstream]
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
