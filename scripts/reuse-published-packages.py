#!/usr/bin/env python3
"""Reuse signed immutable packages when only reproducible-build metadata differs."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile


def identity(path):
    return tuple(subprocess.check_output(
        ['dpkg-deb', '-f', str(path), field], text=True).strip()
        for field in ('Package', 'Version', 'Architecture'))


def payload_digest(path):
    process = subprocess.Popen(['dpkg-deb', '--fsys-tarfile', str(path)], stdout=subprocess.PIPE)
    digest = hashlib.file_digest(process.stdout, 'sha256').digest()
    process.stdout.close()
    if process.wait():
        raise ValueError(f'Cannot read package payload: {path}')
    return digest


def control_records(path):
    raw = subprocess.check_output(['dpkg-deb', '--ctrl-tarfile', str(path)])
    records = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            data = archive.extractfile(member).read() if member.isfile() else b''
            if member.name.removeprefix('./') == 'control':
                # du reports filesystem-dependent allocation, not payload changes.
                data = re.sub(rb'^Installed-Size: [0-9]+\n', b'', data, flags=re.M)
            elif member.name.removeprefix('./') == 'md5sums':
                # LC_COLLATE affects line ordering without changing checksums.
                data = b'\n'.join(sorted(data.splitlines()))
            if member.name in records:
                raise ValueError('Duplicate control archive entry')
            records[member.name] = (member.mode, member.uid, member.gid,
                                    member.type, member.linkname, data)
    return records


def equivalent(left, right):
    return (identity(left) == identity(right)
            and payload_digest(left) == payload_digest(right)
            and control_records(left) == control_records(right))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').digest()


def release_component(path):
    config = json.loads(path.read_text())
    return config['component'], set(config['common_packages'])


def reuse(packages, repository, key, config):
    if repository.is_dir() and not any(repository.iterdir()):
        return  # The first publication has no historical package identities.
    subprocess.run([sys.executable, str(Path(__file__).with_name('verify-repository.py')),
                    '--snapshot', str(repository), str(key), str(repository)], check=True)
    component, common_packages = release_component(config)
    published = {}
    for published_component in ('common', component):
        component_root = repository / 'pool' / published_component
        if not component_root.is_dir():
            continue
        for path in component_root.rglob('*.deb'):
            package_id = identity(path)
            lookup_key = (published_component, *package_id)
            if lookup_key in published and digest(published[lookup_key]) != digest(path):
                raise ValueError(
                    f'Published package identity has conflicting bytes in {published_component}: '
                    f'{package_id}')
            published[lookup_key] = path
    replacements = []
    for path in packages.glob('*.deb'):
        package_id = identity(path)
        target_component = 'common' if package_id[0] in common_packages else component
        canonical = published.get((target_component, *package_id))
        if canonical is None or digest(path) == digest(canonical):
            continue
        if not equivalent(path, canonical):
            raise ValueError(f'Published package changed; increment its version: {path.name}')
        replacements.append((path, canonical))
    for path, canonical in replacements:
        temporary = path.with_suffix('.deb.canonical')
        shutil.copyfile(canonical, temporary)
        temporary.replace(path)
        print(f'Reused signed published bytes: {path.name}')


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit(
            'usage: reuse-published-packages.py PACKAGE_DIR SIGNED_REPOSITORY PUBLIC_KEY PRODUCT_CONFIG')
    try:
        reuse(*(Path(arg).resolve() for arg in sys.argv[1:]))
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
