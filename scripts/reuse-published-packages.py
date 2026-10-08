#!/usr/bin/env python3
"""Reuse signed immutable packages when only reproducible-build metadata differs."""
import hashlib
import io
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


def reuse(packages, repository, key):
    if repository.is_dir() and not any(repository.iterdir()):
        return  # The first publication has no historical package identities.
    subprocess.run([sys.executable, str(Path(__file__).with_name('verify-repository.py')),
                    '--snapshot', str(repository), str(key), str(repository)], check=True)
    published = {}
    for path in (repository / 'pool').rglob('*.deb'):
        package_id = identity(path)
        if package_id in published and digest(published[package_id]) != digest(path):
            raise ValueError(f'Published package identity has conflicting bytes: {package_id}')
        published[package_id] = path
    replacements = []
    for path in packages.glob('*.deb'):
        canonical = published.get(identity(path))
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
    if len(sys.argv) != 4:
        raise SystemExit('usage: reuse-published-packages.py PACKAGE_DIR SIGNED_REPOSITORY PUBLIC_KEY')
    try:
        reuse(*(Path(arg).resolve() for arg in sys.argv[1:]))
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
