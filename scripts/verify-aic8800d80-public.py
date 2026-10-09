#!/usr/bin/env python3
"""Verify the public signed manifest and AIC8800D80 DEBs after Pages deployment."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://apt.100ask.net/'


def fetch(relative, destination):
    if relative.startswith('/') or '..' in relative.split('/'):
        raise SystemExit('unsafe public package path')
    for attempt in range(6):
        try:
            request = urllib.request.Request(BASE + relative, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=40) as response, destination.open('wb') as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            return
        except OSError:
            if attempt == 5:
                raise
            time.sleep(10)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('version')
    args = p.parse_args()
    if not re.fullmatch(r'[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[1-9][0-9]*', args.version):
        raise SystemExit('invalid version')
    with tempfile.TemporaryDirectory(prefix='aic8800d80-public-') as tmp:
        work = Path(tmp)
        key = work / 'archive.gpg'
        subprocess.run(['gpg', '--batch', '--yes', '--dearmor', '--output', str(key), str(ROOT / 'keys/dshanpi-archive.asc')], check=True)
        relative = 'catalog/releases/dshanpi-a1/' + args.version + '.json'
        manifest, signature = work / 'manifest.json', work / 'manifest.asc'
        fetch(relative, manifest)
        fetch(relative + '.asc', signature)
        subprocess.run(['gpgv', '--keyring', str(key), str(signature), str(manifest)], check=True)
        data = json.loads(manifest.read_text())
        if data['product'] != 'dshanpi-a1' or data['version'] != args.version or data.get('withdrawn_from'):
            raise SystemExit('unexpected public release identity/state')
        wanted = {'dshanpi-a1-aic8800d80', 'dshanpi-aic8800d80-firmware', 'dshanpi-aic8800d80-dkms', 'dshanpi-a1-release-core', 'dshanpi-a1-release-desktop'}
        results = []
        for package in data['packages']:
            if package['package'] not in wanted:
                continue
            target = work / 'package.deb'
            fetch(package['filename'], target)
            with target.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != package['sha256']:
                raise SystemExit('public package hash mismatch')
            fields = subprocess.check_output(['dpkg-deb', '-f', str(target), 'Package', 'Version', 'Architecture'], text=True)
            expected = dict(Package=package['package'], Version=package['version'], Architecture=package['architecture'])
            actual = dict(line.split(': ', 1) for line in fields.splitlines())
            if expected != actual:
                raise SystemExit('public package control identity mismatch')
            results.append({'package': package['package'], 'version': package['version'], 'sha256': digest})
        if {p['package'] for p in results} != wanted:
            raise SystemExit('public AIC8800D80 package set is incomplete')
        print(json.dumps({'public_manifest_signature': 'verified', 'packages': results}, indent=2))


if __name__ == '__main__':
    main()
