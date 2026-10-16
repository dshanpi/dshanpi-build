#!/usr/bin/env python3
"""CI streams this file over SSH; no server-side program installation is needed."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def initialize(root):
    if not root.is_absolute() or root == Path('/') or root.is_symlink():
        raise ValueError('unsafe server root')
    root.mkdir(parents=True, exist_ok=True)
    if root.resolve() != root:
        raise ValueError('server root must not traverse symbolic links')
    for name in ('incoming', 'releases'):
        path = root / name
        if path.is_symlink():
            raise ValueError('server storage must not be a symbolic link')
        path.mkdir(mode=0o755, exist_ok=True)


@contextmanager
def publication_lock(root):
    with (root / '.publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def current_release(root):
    pointer = root / 'current'
    if not pointer.is_symlink():
        if pointer.exists():
            raise ValueError('current must be a release symlink')
        if any((root / name).exists() for name in ('pool', 'dists', 'SHA256SUMS')):
            raise ValueError('flat repository exists; refusing to hide existing data')
        return None
    current = pointer.resolve(strict=True)
    if current.parent != root / 'releases' or not current.is_dir():
        raise ValueError('current points outside release storage')
    if not (current / 'SHA256SUMS').is_file():
        raise ValueError('current release is incomplete')
    return current


def job_directory(root, job):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}-[0-9]+', job):
        raise ValueError('invalid upload job identifier')
    path = root / 'incoming' / job
    if path.is_symlink():
        raise ValueError('upload job must not be a symbolic link')
    return path


def prepare(root, job, mode):
    with publication_lock(root):
        current = current_release(root)
        if current is None and mode != '--bootstrap':
            raise ValueError('server is empty; run the migration workflow first')
        path = job_directory(root, job)
        path.mkdir(mode=0o755)
        (path / 'repository').mkdir(mode=0o755)
        (path / 'control').mkdir(mode=0o700)
        return str(current) if current else 'none'


def check_history(previous, candidate):
    publication = json.loads((candidate / 'PUBLICATION.json').read_text())
    allowed = publication.get('removed_pool_files', [])
    if not isinstance(allowed, list) or any(not isinstance(p, str) for p in allowed):
        raise ValueError('invalid pool removal list')
    allowed = set(allowed)
    if allowed and publication.get('operation') != 'purge':
        raise ValueError('only an explicit signed purge may remove pool files')
    removed = set()
    for path in (previous / 'pool').rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(previous)
        target = candidate / relative
        if not target.is_file():
            removed.add(relative.as_posix())
        elif digest(path) != digest(target):
            raise ValueError('historical pool bytes changed: ' + relative.as_posix())
    if removed != allowed:
        raise ValueError('pool removal differs from the signed purge plan')


def publish(root, job, expected_hash, key_name, bootstrap=False):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
        raise ValueError('invalid publication checksum')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+', key_name):
        raise ValueError('invalid public key filename')
    upload = job_directory(root, job)
    candidate = upload / 'repository'
    control = upload / 'control'
    if any(p.is_symlink() for p in upload.rglob('*')):
        raise ValueError('upload contains a symbolic link')
    verifier = control / 'verify-repository.py'
    key = control / key_name
    with publication_lock(root):
        previous = current_release(root)
        if not candidate.is_dir() or digest(candidate / 'SHA256SUMS') != expected_hash:
            raise ValueError('upload checksum differs from CI candidate')
        same_state = previous is not None and digest(previous / 'SHA256SUMS') == expected_hash
        if bootstrap and previous is not None and not same_state:
            raise ValueError('migration cannot overwrite an initialized server')
        if not bootstrap and previous is None:
            raise ValueError('server is empty; migrate the existing repository first')
        command = [sys.executable, str(verifier)]
        if bootstrap or same_state:
            command.append('--snapshot')
        command += [str(candidate), str(key), str(previous or candidate)]
        subprocess.run(command, check=True, stdout=sys.stderr)
        if previous is not None:
            # The lock covers predecessor checking, verification and the switch.
            subprocess.run([sys.executable, str(verifier), '--snapshot',
                            str(previous), str(key), str(previous)],
                           check=True, stdout=sys.stderr)
            if not same_state:
                check_history(previous, candidate)
        for name in ('index.html', 'repository.json', 'archive-key.asc', 'dshanpi-archive-keyring.gpg'):
            if not (candidate / name).is_file():
                raise ValueError('missing public site asset: ' + name)
        if (candidate / 'archive-key.asc').read_bytes() != key.read_bytes():
            raise ValueError('public download key differs from verification key')
        if same_state:
            print('The identical signed repository is already current; no switch needed.')
            shutil.rmtree(upload)
            return
        destination = root / 'releases' / job
        if destination.exists() or destination.is_symlink():
            raise ValueError('release destination already exists')
        candidate.rename(destination)
        temporary = root / ('.current-' + job)
        try:
            temporary.symlink_to(Path('releases') / job, target_is_directory=True)
            os.replace(temporary, root / 'current')
        finally:
            if temporary.is_symlink():
                temporary.unlink()
        # Keep previous snapshots for recovery. Identical files are hard-linked
        # by rsync --link-dest; no automatic deletion of published history.
        print('Current signed repository: ' + str(destination))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['current', 'prepare', 'publish', '--bootstrap'])
    parser.add_argument('root', type=Path)
    parser.add_argument('arguments', nargs='*')
    # --bootstrap is a positional operation passed after -- by the caller.
    args = parser.parse_args()
    initialize(args.root)
    if args.operation == 'current':
        with publication_lock(args.root):
            current = current_release(args.root)
            print(current if current else 'none')
    elif args.operation == 'prepare':
        print(prepare(args.root, *args.arguments))
    else:
        publish(args.root, *args.arguments, bootstrap=args.operation == '--bootstrap')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('APT SSH publication failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
