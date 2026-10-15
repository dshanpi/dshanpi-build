#!/usr/bin/env python3
"""Dispatch a committed package-only release without rebuilding product images."""

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = {
    ('dshanpi-a1', 'axcl'): 'build-axcl-release.py',
    ('dshanpi-a1', 'axcl-8g'): 'build-axcl-8g-release.py',
    ('dshanpi-a1', 'axcl-16g'): 'build-axcl-16g-release.py',
    ('dshanpi-a1', 'aic8800d80'): 'build-aic8800d80-release.py',
}


def command(product: str, version: str, repository: Path) -> list[str]:
    lock_path = ROOT / 'products' / product / 'releases' / f'{version}.lock.json'
    lock = json.loads(lock_path.read_text())
    if lock.get('product') != product or lock.get('version') != version:
        raise ValueError('maintenance release identity mismatch')
    adapter = lock.get('maintenance_adapter')
    script = ADAPTERS.get((product, adapter))
    if script is None:
        raise ValueError(f'unsupported maintenance adapter for {product}: {adapter}')
    return ['python3', str(ROOT / 'scripts' / script), version, str(repository.resolve())]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product')
    parser.add_argument('version')
    parser.add_argument('repository', type=Path)
    parser.add_argument('--print-command', action='store_true')
    args = parser.parse_args()
    try:
        selected = command(args.product, args.version, args.repository)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f'maintenance release dispatch failed: {error}')
    if args.print_command:
        print(' '.join(selected))
        return
    subprocess.run(selected, check=True)


if __name__ == '__main__':
    main()
