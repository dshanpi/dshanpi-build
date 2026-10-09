#!/usr/bin/env python3
"""Build pinned, optional A1 AXCL packages. No board access or publication."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--upstream', type=Path)
    args = parser.parse_args()
    run('python3', ROOT / 'tools/check-delivery-policy.py')
    lock = json.loads((ROOT / 'packages/axcl-16g/upstream.lock.json').read_text())
    version, kernel = lock['version'], lock['kernel_release']
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='axcl-build-') as tmp:
        work = Path(tmp)
        upstream = args.upstream or work / 'upstream.deb'
        if not args.upstream:
            urllib.request.urlretrieve(lock['url'], upstream)
        if sha(upstream) != lock['sha256']:
            raise SystemExit('upstream SHA-256 mismatch')
        vendor = work / 'vendor'
        run('dpkg-deb', '--raw-extract', upstream, vendor)
        runtime, driver, meta, firmware = (work / name for name in ('runtime', 'driver', 'meta', 'firmware'))
        pac = vendor / 'lib/firmware/axcl/ax650_card.pac'
        if lock['capacity_gb'] != 16 or sha(pac) != lock['firmware_sha256']:
            raise SystemExit('16GB firmware SHA-256 mismatch')
        (firmware / 'lib/firmware/axcl').mkdir(parents=True)
        shutil.copyfile(pac, firmware / 'lib/firmware/axcl/ax650_card.pac')
        write(firmware, 'usr/share/dshanpi-axcl/firmware.sha256', lock['firmware_sha256'] + '  /lib/firmware/axcl/ax650_card.pac\n')
        for relative in ('usr/bin/axcl', 'usr/lib/axcl', 'usr/include/axcl'):
            shutil.copytree(vendor / relative, runtime / relative, symlinks=True)
        write(runtime, 'etc/ld.so.conf.d/dshanpi-axcl.conf', '/usr/lib/axcl\n/usr/lib/axcl/ffmpeg\n')
        # Stable PATH entry points also work under sudo and non-login shells.
        for binary in ('axcl-smi', 'axcl_run_model'):
            (runtime / 'usr/bin' / binary).symlink_to('axcl/' + binary)
        write(runtime, 'usr/bin/axcl_ut_npu', '#!/bin/sh\ncd /usr/bin/axcl\nexec ./ut/axcl_ut_npu "$@"\n', 0o755)
        write(runtime, 'DEBIAN/triggers', 'activate-noawait ldconfig\n')

        source = driver / ('usr/src/axcl-' + version)
        shutil.copytree(vendor / 'usr/src/axcl', source, symlinks=True)
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
        revision = lock['kernel_package_version']
        packages = [
            (firmware, 'dshanpi-axcl-firmware-16g', f'dshanpi-axcl-runtime-16g (= {version})', 'AX8850 16GB PAC paired with the exact 16GB runtime'),
            (runtime, 'dshanpi-axcl-runtime-16g', 'libc6 (>= 2.35), libstdc++6, libgcc-s1', 'AXCL ARM64 runtime, SDK headers and inference tools'),
            (driver, 'dshanpi-axcl-dkms-16g', f'dkms (>= 3), build-essential, kmod, pahole, binutils, linux-headers-vendor-rk35xx (= {revision})', 'AXCL host driver sources managed by DKMS'),
            (meta, 'dshanpi-a1-axcl-16g', f'dshanpi-axcl-firmware-16g (= {version}), dshanpi-axcl-runtime-16g (= {version}), dshanpi-axcl-dkms-16g (= {version}), linux-image-vendor-rk35xx (= {revision}), armbian-bsp-cli-dshanpi-a1-vendor (= {revision}), pciutils, coreutils', 'Optional AX650N/AX8850 support for DShanPI A1'),
        ]
        evidence = {'upstream': lock, 'packages': []}
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
