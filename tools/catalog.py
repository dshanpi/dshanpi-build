#!/usr/bin/env python3
"""Generate a browsing index from an already verified repository snapshot."""
import json
from pathlib import Path
import sys
import re
import subprocess

root = Path(sys.argv[1])
products = []
for directory in sorted((root / 'catalog/releases').glob('*')):
    if not directory.is_dir():
        continue
    releases = []
    for path in sorted(directory.glob('*.json'), reverse=True):
        release = json.loads(path.read_text())
        install = {}
        for variant in ('core', 'desktop'):
            meta = next(p for p in release['packages'] if p['package'] == directory.name + '-release-' + variant)
            dependencies = subprocess.check_output(['dpkg-deb', '-f', str(root / meta['filename']), 'Depends'], text=True)
            arguments = [meta['package'] + '=' + meta['version']]
            for dependency in dependencies.split(','):
                match = re.fullmatch(r'\s*([a-z0-9][a-z0-9+.-]*) \(= ([a-zA-Z0-9.+:~\-]+)\)\s*', dependency)
                if not match:
                    raise SystemExit('unrecognized release dependency: ' + dependency)
                arguments.append('='.join(match.groups()))
            install[variant] = arguments
        releases.append(dict(version=release['version'], install=install,
                             testing=release.get('withdrawn_from') != release['suite'],
                             stable=bool(release.get('promoted_to')),
                             manifest=path.relative_to(root).as_posix(),
                             packages=release['packages']))
    products.append(dict(product=directory.name, releases=releases))
(Path(sys.argv[2]) if len(sys.argv) > 2 else root / 'repository.json').write_text(json.dumps(dict(products=products), ensure_ascii=False) + '\n')
