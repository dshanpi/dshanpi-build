#!/usr/bin/env python3
"""Generate a browsing index from an already verified repository snapshot."""
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
products = []
for directory in sorted((root / 'catalog/releases').glob('*')):
    if not directory.is_dir():
        continue
    releases = []
    for path in sorted(directory.glob('*.json'), reverse=True):
        release = json.loads(path.read_text())
        releases.append(dict(version=release['version'],
                             testing=release.get('withdrawn_from') != release['suite'],
                             stable=bool(release.get('promoted_to')),
                             manifest=path.relative_to(root).as_posix(),
                             packages=release['packages']))
    products.append(dict(product=directory.name, releases=releases))
(root / 'repository.json').write_text(json.dumps(dict(products=products), ensure_ascii=False) + '\n')
