#!/usr/bin/env python3
"""Build pinned A1 AXCL driver/meta compatibility packages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(root, relative, content, mode=0o644):
    p = root / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    p.chmod(mode)


def deb_field(path, field):
    return subprocess.check_output(['dpkg-deb', '-f', str(path), field], text=True).strip()


def verify_previous_driver(path, lock):
    expected = lock['source_driver']
    if sha(path) != expected['sha256']:
        raise SystemExit('previous AXCL driver SHA-256 mismatch')
    for field, key in (('Package', 'package'), ('Version', 'version'), ('Architecture', 'architecture')):
        if deb_field(path, field) != expected[key]:
            raise SystemExit(f'previous AXCL driver {field} mismatch')


def package_dependencies(lock, version=None, revision=None):
    version = version or lock['version']
    revision = revision or lock['kernel_package_version']
    retained = lock['retained_packages']
    runtime_version = retained['dshanpi-axcl-runtime-16g']['version']
    firmware_version = retained['dshanpi-axcl-firmware-16g']['version']
    return {
        'dshanpi-axcl-dkms-16g': (
            f'dkms (>= 3), build-essential, kmod, pahole, binutils, '
            f'linux-headers-vendor-rk35xx (= {revision})'
        ),
        'dshanpi-a1-axcl-16g': (
            f'dshanpi-axcl-firmware-16g (= {firmware_version}), '
            f'dshanpi-axcl-runtime-16g (= {runtime_version}), '
            f'dshanpi-axcl-dkms-16g (= {version}), '
            f'linux-image-vendor-rk35xx (= {revision}), '
            f'armbian-bsp-cli-dshanpi-a1-vendor (= {revision}), pciutils, coreutils'
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--upstream', type=Path)
    source.add_argument('--previous-driver', type=Path)
    parser.add_argument('--package-version')
    parser.add_argument('--platform-version')
    args = parser.parse_args()
    run('python3', ROOT / 'tools/check-delivery-policy.py')
    lock = json.loads((ROOT / 'packages/axcl-16g/upstream.lock.json').read_text())
    version = args.package_version or lock['version']
    revision = args.platform_version or lock['kernel_package_version']
    if subprocess.run(['dpkg', '--validate-version', version], capture_output=True).returncode:
        raise SystemExit('invalid AXCL package version')
    if not revision or any(character.isspace() for character in revision):
        raise SystemExit('invalid platform package version')
    kernel = lock['kernel_release']
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='axcl-build-') as tmp:
        work = Path(tmp)
        extracted = work / 'source'
        if args.previous_driver:
            previous_driver = args.previous_driver.resolve()
            verify_previous_driver(previous_driver, lock)
            run('dpkg-deb', '--raw-extract', previous_driver, extracted)
            prior = lock['source_driver']['version']
            source_tree = extracted / ('usr/src/axcl-' + prior)
            embedded = json.loads((extracted / 'usr/share/doc/dshanpi-axcl-dkms-16g/upstream.json').read_text())
            for field in ('url', 'sha256', 'upstream_commit', 'upstream_version'):
                if embedded.get(field) != lock[field]:
                    raise SystemExit(f'previous AXCL driver provenance mismatch: {field}')
        else:
            upstream = args.upstream.resolve() if args.upstream else work / 'upstream.deb'
            if not args.upstream:
                urllib.request.urlretrieve(lock['url'], upstream)
            if sha(upstream) != lock['sha256']:
                raise SystemExit('upstream SHA-256 mismatch')
            run('dpkg-deb', '--raw-extract', upstream, extracted)
            source_tree = extracted / 'usr/src/axcl'
        driver, meta = work / 'driver', work / 'meta'
        source = driver / ('usr/src/axcl-' + version)
        shutil.copytree(source_tree, source, symlinks=True)
        # Only the five documented host modules are installed. Network/vtty
        # drivers are not needed for the documented inference workflow.
        makefile = source / 'drv/pcie/driver/Makefile'
        makefile.write_text(makefile.read_text().replace(
            'SUBDIRS = host_dev msg mmb axcl_host net p2p_rc vtty',
            'SUBDIRS = host_dev msg mmb axcl_host p2p_rc'))
        config = f'''PACKAGE_NAME="axcl"
PACKAGE_VERSION="{version}"
AUTOINSTALL="yes"
BUILD_EXCLUSIVE_KERNEL="^{kernel.replace('.', '[.]')}$"
MAKE[0]="make -j1 -C drv/pcie/driver host=arm64 CROSS= KERNEL_VER=$kernelver KERNEL_DIR=/lib/modules/$kernelver KERNEL_BUILD=/lib/modules/$kernelver/build install"
CLEAN="make -C drv/pcie/driver host=arm64 CROSS= clean"
'''
        for i, name in enumerate(('ax_pcie_host_dev', 'ax_pcie_msg', 'ax_pcie_mmb', 'axcl_host', 'ax_pcie_p2p_rc')):
            config += f'BUILT_MODULE_NAME[{i}]="{name}"\nBUILT_MODULE_LOCATION[{i}]="out/axcl_linux_arm64/ko"\nDEST_MODULE_LOCATION[{i}]="/updates/dkms"\n'
        write(source, 'dkms.conf', config)
        write(driver, 'DEBIAN/postinst', f'''#!/bin/sh
set -e
if [ "$1" = configure ]; then
    /usr/lib/dkms/common.postinst axcl '{version}' '' '' "$2"
fi
''', 0o755)
        write(driver, 'DEBIAN/prerm', f'''#!/bin/sh
set -e
case "$1" in remove|upgrade|deconfigure)
    if [ -d /var/lib/dkms/axcl/{version} ]; then dkms remove -m axcl -v '{version}' --all; fi
esac
''', 0o755)
        # Do not auto-load before the exact card PAC has been reviewed.
        write(meta, 'usr/sbin/dshanpi-axcl', (ROOT / 'packages/axcl-16g/dshanpi-axcl').read_text(), 0o755)
        write(meta, 'lib/systemd/system/dshanpi-axcl.service', '''[Unit]
Description=DShanPI AXCL card initialization
After=systemd-udev-settle.service
ConditionPathExists=/usr/share/dshanpi-axcl/firmware.sha256

[Service]
Type=oneshot
ExecStart=/usr/sbin/dshanpi-axcl start
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
''')
        # Firmware installation will explicitly enable the service only when
        # a reviewed card-specific package is available.
        retained = lock['retained_packages']
        dependencies = package_dependencies(lock, version, revision)
        packages = [
            (driver, 'dshanpi-axcl-dkms-16g', dependencies['dshanpi-axcl-dkms-16g'], 'AXCL host driver sources managed by DKMS'),
            (meta, 'dshanpi-a1-axcl-16g', dependencies['dshanpi-a1-axcl-16g'], 'Optional AX650N/AX8850 support for DShanPI A1'),
        ]
        evidence = {
            'upstream': lock,
            'package_version': version,
            'platform_version': revision,
            'retained_packages': retained,
            'packages': [],
        }
        for root, name, depends, description in packages:
            installed_size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()) // 1024 + 1
            write(root, 'DEBIAN/control', f'''Package: {name}
Version: {version}
Architecture: arm64
Maintainer: DShanPI <support@dshanpi.com>
Section: misc
Priority: optional
Installed-Size: {installed_size}
Depends: {depends}
Conflicts: axclhost, dshanpi-axcl-runtime, dshanpi-axcl-dkms, dshanpi-a1-axcl
Description: {description}
 Explicit 16GB card variant. Runtime and PAC must be installed together.
''')
            write(root, f'usr/share/doc/{name}/upstream.json', json.dumps(lock, indent=2) + '\n')
            write(root, f'usr/share/doc/{name}/copyright',
                  'Upstream: AXERA-TECH AXCL\nSource: ' + lock['url'] + '\n'
                  'The upstream distribution metadata declares BSD-3-Clause.\n'
                  'Driver source retains its original copyright notices and MODULE_LICENSE declarations.\n')
            checksums = []
            for p in sorted(root.rglob('*')):
                if p.is_file() and not p.is_symlink() and p.relative_to(root).parts[0] != 'DEBIAN':
                    checksums.append(hashlib.md5(p.read_bytes()).hexdigest() + '  ' + p.relative_to(root).as_posix())
            write(root, 'DEBIAN/md5sums', '\n'.join(checksums) + '\n')
            # Include the archive root: mkdir inherits the builder's umask.
            for p in [root, *root.rglob('*')]:
                if not p.is_symlink():
                    p.chmod(0o755 if p.is_dir() or p.stat().st_mode & 0o111 else 0o644)
            for p in [root, *root.rglob('*')]:
                os.utime(p, (lock['source_date_epoch'],) * 2, follow_symlinks=False)
            deb = output / f'{name}_{version}_arm64.deb'
            candidate = work / deb.name
            run('dpkg-deb', '-Zxz', '--root-owner-group', '--build', root, candidate,
                env={**os.environ, 'SOURCE_DATE_EPOCH': str(lock['source_date_epoch'])})
            if deb.exists() and sha(deb) != sha(candidate):
                raise SystemExit(f'refusing changed package identity: {deb}')
            shutil.copyfile(candidate, deb)
            evidence['packages'].append({'package': name, 'version': version, 'architecture': 'arm64', 'filename': deb.name, 'sha256': sha(deb)})
        (output / 'axcl-16g-build.json').write_text(json.dumps(evidence, indent=2) + '\n')
    run(ROOT / 'scripts/audit-packages.sh', output)


if __name__ == '__main__':
    main()
