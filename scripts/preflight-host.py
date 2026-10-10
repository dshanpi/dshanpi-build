#!/usr/bin/env python3
"""Read-only Ubuntu 24.04 x86_64 build-host checks. Never installs or publishes."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['packages', 'images'], default='packages')
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--network', action='store_true', help='also check public download endpoints')
    args = parser.parse_args()
    os_info = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    checks = {'ubuntu_24_04': os_info.get('ID', '').strip('"') == 'ubuntu' and
              os_info.get('VERSION_ID', '').strip('"') == '24.04',
              'x86_64': platform.machine() == 'x86_64'}
    commands = ['git', 'curl', 'python3', 'jq', 'dpkg-deb', 'gpg', 'patchelf', 'xz', 'make', 'gcc']
    if args.mode == 'images':
        commands += ['sudo', 'rsync', 'qemu-aarch64-static', 'dtc', 'pigz']
    for command in commands:
        checks['tool:' + command] = shutil.which(command) is not None
    path = args.workspace.resolve()
    while not path.exists():
        path = path.parent
    free_gib = shutil.disk_usage(path).free / 1024 ** 3
    minimum = 100 if args.mode == 'images' else 5
    checks['free_disk'] = free_gib >= minimum
    if args.mode == 'images' and checks['tool:sudo']:
        checks['sudo_ready'] = subprocess.run(['sudo', '-n', 'true'], capture_output=True).returncode == 0
    if args.network:
        for url in ['https://github.com/dshanpi/dshanpi-build', 'https://apt.100ask.net/archive-key.asc',
                    'https://huggingface.co/AXERA-TECH/AXCL']:
            try:
                with urllib.request.urlopen(url, timeout=20) as response:
                    checks['network:' + url] = response.status == 200
            except (OSError, ValueError):
                checks['network:' + url] = False
    print(json.dumps({'mode': args.mode, 'checks': checks, 'free_gib': round(free_gib, 1),
                      'minimum_free_gib': minimum,
                      'note': 'Image disk threshold is a starting minimum, not a peak-usage guarantee. Run sudo -v before image checks.'}, indent=2))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == '__main__':
    main()
