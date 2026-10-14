#!/usr/bin/env python3
"""Verify a mounted release image against its exact platform meta-package."""
import argparse
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
parser.add_argument('product')
parser.add_argument('version')
args = parser.parse_args()
root = args.root

def require(ok, message):
    if not ok:
        raise SystemExit('image verification: ' + message)

packages = {}
for paragraph in (root / 'var/lib/dpkg/status').read_text().split('\n\n'):
    fields = {}
    key = None
    for line in paragraph.splitlines():
        if line.startswith((' ', '\t')) and key:
            fields[key] += ' ' + line.strip()
        elif ': ' in line:
            key, value = line.split(': ', 1)
            fields[key] = value
    if fields.get('Status') == 'install ok installed':
        packages[fields['Package']] = fields
metas = [packages[name] for name in (args.product + '-release-core', args.product + '-release-desktop') if name in packages]
require(len(metas) == 1, 'expected exactly one installed core/desktop release meta-package')
meta = metas[0]
require(meta['Version'] == args.version, 'release version mismatch')
for dependency in meta.get('Depends', '').split(','):
    match = re.fullmatch(r'\s*([a-z0-9][a-z0-9+.-]*) \(= ([^\s()]+)\)\s*', dependency)
    require(match is not None, 'release dependency is not pinned: ' + dependency)
    name, version = match.groups()
    require(packages.get(name, {}).get('Version') == version, 'missing or wrong dependency: ' + name + '=' + version)
require('dspi-config' in packages, 'dspi-config is not installed')
profile = root / 'usr/share/dspi-config/boards' / args.product
require((profile / 'system.conf').is_file() and (profile / 'overlays.tsv').is_file(), 'board profile is missing')
source = (root / 'etc/apt/sources.list.d/dshanpi.sources').read_text().splitlines()
for expected in ('URIs: https://apt.100ask.net', 'Components: common ' + args.product,
                 'Signed-By: /usr/share/keyrings/dshanpi-archive-keyring.gpg'):
    require(expected in source, 'source configuration mismatch: ' + expected)
require('Suites: noble' in source or 'Suites: noble-testing' in source, 'wrong APT suite')
require(not any(re.match(r'trusted\s*:', line, re.I) for line in source), 'source disables authentication')
require((root / 'usr/share/keyrings/dshanpi-archive-keyring.gpg').stat().st_size > 0, 'archive key is empty')
board_release = (root / 'etc/armbian-release').read_text()
require(re.search(r'^BOARD=[\"\']?' + re.escape(args.product) + r'[\"\']?$', board_release, re.M), 'board identity mismatch')
config = json.loads((Path(__file__).resolve().parents[1] / 'products' / args.product / 'product.json').read_text())
expected_fdt = config['armbian']['boot_fdt_file']
armbian_env = root / 'boot/armbianEnv.txt'
extlinux = root / 'boot/extlinux/extlinux.conf'
if armbian_env.is_file():
    env = dict(line.split('=', 1) for line in armbian_env.read_text().splitlines()
               if '=' in line and not line.startswith('#'))
    selected_fdt = env.get('fdtfile')
    selected_path = root / 'boot/dtb' / str(selected_fdt)
elif extlinux.is_file():
    selections = re.findall(r'^\s*fdt\s+(\S+)\s*$', extlinux.read_text(), re.M | re.I)
    require(len(selections) == 1, 'expected exactly one extlinux device tree selection')
    selected = selections[0]
    prefix = '/dtb/'
    require(selected.startswith(prefix), 'extlinux device tree is outside /dtb')
    selected_fdt = selected[len(prefix):]
    selected_path = root / 'boot' / selected.lstrip('/')
else:
    require(False, 'boot configuration is missing')
require(selected_fdt == expected_fdt, 'wrong boot device tree for product')
require(selected_path.is_file(), 'boot device tree is missing')
print('Verified', args.product, args.version, meta['Package'], 'and all exact platform dependencies')
