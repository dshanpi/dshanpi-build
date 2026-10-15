#!/usr/bin/env python3
"""Assemble an A1 package maintenance release using verified historical bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main(capacity=16):
    if capacity not in (8, 16):
        raise SystemExit("unsupported AXCL capacity")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('version')
    p.add_argument('repository', type=Path)
    p.add_argument('--upstream', type=Path)
    args = p.parse_args()
    run = lambda *cmd: subprocess.run(list(map(str, cmd)), check=True)
    run('python3', ROOT / 'tools/check-delivery-policy.py')
    lock_path = ROOT / 'products/dshanpi-a1/releases' / (args.version + '.lock.json')
    lock = json.loads(lock_path.read_text())
    if lock.get('maintenance_adapter') != f'axcl-{capacity}g' or lock.get('product') != 'dshanpi-a1':
        raise SystemExit(f'not an A1 AXCL {capacity}GB maintenance plan')
    axcl_lock_path = ROOT / f'packages/axcl-{capacity}g/upstream.lock.json'
    if hashlib.sha256(axcl_lock_path.read_bytes()).hexdigest() != lock[f'axcl_{capacity}g_lock_sha256']:
        raise SystemExit(f'AXCL {capacity}GB inputs differ from release plan')
    axcl_lock = json.loads(axcl_lock_path.read_text())
    run(ROOT / 'scripts/validate-config.sh', 'dshanpi-a1', lock_path)
    repo = args.repository.resolve()
    run('python3', ROOT / 'scripts/verify-repository.py', '--snapshot', repo, ROOT / 'keys/dshanpi-archive.asc', repo)
    manifest = repo / 'catalog/releases/dshanpi-a1' / (lock['base_release'] + '.json')
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != lock['base_manifest_sha256']:
        raise SystemExit('base release manifest hash mismatch')
    if capacity == 16:
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
        if name != f'axcl-{capacity}g':
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
    complete_cohort = lock.get('axcl_complete_cohort', False)
    if capacity == 16:
        source_inputs = lock['axcl_source_packages'] if complete_cohort else axcl_lock
        retained = source_inputs['retained_packages']
        source_driver = source_inputs['source_driver']
        previous_payloads = {}
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
                previous_payloads[package['package']] = source
                if not complete_cohort:
                    shutil.copyfile(source, output / source.name)
                copied_retained.add(package['package'])
        if previous_driver is None or copied_retained != set(retained):
            raise SystemExit('AXCL historical source cohort is incomplete')
        cmd = ['python3', ROOT / 'scripts/build-axcl-16g-packages.py', output]
        if args.upstream:
            cmd += ['--upstream', args.upstream]
        else:
            cmd += ['--previous-driver', previous_driver]
            if complete_cohort:
                cmd += [
                    '--previous-runtime', previous_payloads['dshanpi-axcl-runtime-16g'],
                    '--previous-firmware', previous_payloads['dshanpi-axcl-firmware-16g'],
                    '--previous-release-lock', lock_path,
                ]
    else:
        if not complete_cohort:
            raise SystemExit('8GB requires a complete four-package cohort')
        cmd = ['python3', ROOT / 'scripts/build-axcl-8g-packages.py', output]
        if args.upstream:
            cmd += ['--upstream', args.upstream]
    cmd += [
        '--package-version', axcl_lock['version'],
        '--platform-version', lock['revision'],
    ]
    run(*cmd)
    if complete_cohort:
        expected = lock['axcl_expected_packages']
        actual = {}
        for deb in output.glob(f'*axcl*{capacity}g*.deb'):
            name = subprocess.check_output(['dpkg-deb', '-f', str(deb), 'Package'], text=True).strip()
            actual[name] = hashlib.sha256(deb.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit('AXCL release bytes differ from the hardware-tested cohort')
    run(ROOT / 'scripts/build-release-meta.sh', 'dshanpi-a1', args.version, output)
    run(ROOT / 'scripts/audit-packages.sh', output)
    with (output / 'SHA256SUMS').open('w') as sums:
        for deb in sorted(output.glob('*.deb')):
            with deb.open('rb') as f:
                sums.write(hashlib.file_digest(f, 'sha256').hexdigest() + '  ' + deb.name + '\n')
    print(output)


if __name__ == '__main__':
    main()
