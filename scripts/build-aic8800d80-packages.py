#!/usr/bin/env python3
"""Package the pinned user-supplied AIC8800D80 USB sources and firmware for A1."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(root, name, text, mode=0o644):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def replace_once(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise ValueError('unexpected vendor source at ' + str(path))
    path.write_text(text.replace(old, new))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run('python3', ROOT / 'tools/check-delivery-policy.py')
    lock = json.loads((ROOT / 'packages/aic8800d80/upstream.lock.json').read_text())
    archive = ROOT / lock['source_archive']
    if sha(archive) != lock['sha256']:
        raise SystemExit('source archive SHA-256 mismatch')
    version, kernel, revision = (lock[k] for k in ('version', 'kernel_release', 'kernel_package_version'))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='aic8800d80-build-') as tmp:
        work = Path(tmp)
        with tarfile.open(archive) as vendor:
            vendor.extractall(work / 'vendor', filter='data')
        original = work / 'vendor/aic8800d80'
        driver, firmware, meta = (work / n for n in ('driver', 'firmware', 'meta'))
        source = driver / ('usr/src/dshanpi-aic8800d80-' + version)
        shutil.copytree(original / 'drivers', source / 'drivers')
        # Use Linux/BlueZ support and a private firmware tree; never overwrite
        # the CM5 SDIO driver's firmware or invoke vendor make install targets.
        replace_once(source / 'drivers/aic8800/aic_load_fw/aicbluetooth.c',
                     'aic_default_fw_path = "/lib/firmware"',
                     'aic_default_fw_path = "/lib/firmware/dshanpi-aic8800d80"')
        replace_once(source / 'drivers/aic_btusb/aic_btusb.c',
                     'aic_default_fw_path = "/lib/firmware"',
                     'aic_default_fw_path = "/lib/firmware/dshanpi-aic8800d80/aic8800D80"')
        write(source, 'build.sh', '''#!/bin/sh
set -eu
kernel=$1
for part in aic8800 aic_btusb; do
    make -j2 -C "/lib/modules/$kernel/build" M="$PWD/drivers/$part" \
        ARCH=arm64 CROSS_COMPILE= CONFIG_PLATFORM_ROCKCHIP=n CONFIG_PLATFORM_UBUNTU=y modules
done
''', 0o755)
        config = f'''PACKAGE_NAME="dshanpi-aic8800d80"
PACKAGE_VERSION="{version}"
AUTOINSTALL="yes"
BUILD_EXCLUSIVE_KERNEL="^{kernel.replace('.', '[.]')}$"
MAKE[0]="sh build.sh $kernelver"
CLEAN="true"
'''
        for i, (name, location) in enumerate((('aic_load_fw', 'drivers/aic8800/aic_load_fw'),
                                             ('aic8800_fdrv', 'drivers/aic8800/aic8800_fdrv'),
                                             ('aic_btusb', 'drivers/aic_btusb'))):
            config += f'BUILT_MODULE_NAME[{i}]="{name}"\nBUILT_MODULE_LOCATION[{i}]="{location}"\nDEST_MODULE_LOCATION[{i}]="/updates/dkms"\n'
        write(source, 'dkms.conf', config)
        write(driver, 'DEBIAN/postinst', f'''#!/bin/sh
set -e
if [ "$1" = configure ]; then
    /usr/lib/dkms/common.postinst dshanpi-aic8800d80 '{version}' '' '' "$2"
fi
''', 0o755)
        write(driver, 'DEBIAN/prerm', f'''#!/bin/sh
set -e
case "$1" in remove|upgrade|deconfigure)
    if [ -d /var/lib/dkms/dshanpi-aic8800d80/{version} ]; then
        dkms remove -m dshanpi-aic8800d80 -v '{version}' --all
    fi
esac
''', 0o755)
        # Prefer the vendor's AIC-specific Bluetooth driver before generic
        # btusb; do not globally blacklist Bluetooth or load modules here.
        write(driver, 'lib/modprobe.d/dshanpi-aic8800d80.conf', 'softdep btusb pre: aic_btusb\n')
        fwdir = firmware / 'lib/firmware/dshanpi-aic8800d80/aic8800D80'
        shutil.copytree(original / 'fw', fwdir)
        write(firmware, 'DEBIAN/conffiles', ''.join('/lib/firmware/dshanpi-aic8800d80/aic8800D80/' + p.name + '\n' for p in sorted(fwdir.glob('*.txt'))))
        write(meta, 'usr/share/doc/dshanpi-a1-aic8800d80/README.md', (ROOT / 'packages/aic8800d80/README.md').read_text())
        packages = [
            (driver, 'dshanpi-aic8800d80-dkms', f'dkms (>= 3), build-essential, kmod, linux-headers-vendor-rk35xx (= {revision}), dshanpi-aic8800d80-firmware (= {version})', 'AIC8800D80 USB Wi-Fi and Bluetooth DKMS sources for A1'),
            (firmware, 'dshanpi-aic8800d80-firmware', '', 'AX8850 adapter AIC8800D80 vendor firmware'),
            (meta, 'dshanpi-a1-aic8800d80', f'dshanpi-aic8800d80-dkms (= {version}), dshanpi-aic8800d80-firmware (= {version}), linux-image-vendor-rk35xx (= {revision}), armbian-bsp-cli-dshanpi-a1-vendor (= {revision}), bluez, iw, rfkill, usbutils', 'Optional AX8850 adapter Wi-Fi and Bluetooth support for DShanPI A1'),
        ]
        evidence = {'upstream': lock, 'packages': []}
        for root, name, depends, description in packages:
            write(root, f'usr/share/doc/{name}/upstream.json', json.dumps(lock, indent=2) + '\n')
            write(root, f'usr/share/doc/{name}/copyright',
                  'Upstream: AICSemi, user-provided AX8850 adapter archive.\n'
                  'Driver files retain original copyright and GPL notices.\n'
                  'Firmware blobs are supplied unchanged; no new license is asserted for them.\n'
                  'Original archive SHA-256: ' + lock['sha256'] + '\n')
            if root == driver:
                shutil.copyfile('/usr/share/common-licenses/GPL-2', root / f'usr/share/doc/{name}/GPL-2')
            installed_size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()) // 1024 + 1
            extra = ('Depends: ' + depends + '\n') if depends else ''
            if root == driver:
                extra += 'Conflicts: aic8800-sdio-dkms, aic8800-usb-dkms, aic8800-pcie-dkms, aic8800-dkms\n'
            write(root, 'DEBIAN/control', f'''Package: {name}
Version: {version}
Architecture: arm64
Maintainer: DShanPI <support@dshanpi.com>
Section: kernel
Priority: optional
Installed-Size: {installed_size}
{extra}Description: {description}
 Hardware functional validation is performed separately by the user.
''')
            sums = [hashlib.md5(p.read_bytes()).hexdigest() + '  ' + p.relative_to(root).as_posix()
                    for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink() and p.relative_to(root).parts[0] != 'DEBIAN']
            write(root, 'DEBIAN/md5sums', '\n'.join(sums) + '\n')
            for p in [root, *root.rglob('*')]:
                if not p.is_symlink():
                    p.chmod(0o755 if p.is_dir() or p.stat().st_mode & 0o111 else 0o644)
                os.utime(p, (lock['source_date_epoch'],) * 2, follow_symlinks=False)
            candidate = work / f'{name}_{version}_arm64.deb'
            run('dpkg-deb', '-Zxz', '--root-owner-group', '--build', root, candidate,
                env={**os.environ, 'SOURCE_DATE_EPOCH': str(lock['source_date_epoch'])})
            deb = output / candidate.name
            if deb.exists() and sha(deb) != sha(candidate):
                raise SystemExit('refusing changed package identity: ' + str(deb))
            shutil.copyfile(candidate, deb)
            evidence['packages'].append({'package': name, 'version': version, 'architecture': 'arm64', 'filename': deb.name, 'sha256': sha(deb)})
        (output / 'aic8800d80-build.json').write_text(json.dumps(evidence, indent=2) + '\n')
    run(ROOT / 'scripts/audit-packages.sh', output)


if __name__ == '__main__':
    main()
