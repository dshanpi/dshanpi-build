#!/usr/bin/env python3
"""Validate committed board acceptance before an immutable stable promotion."""

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BASE_CHECKS = ('apt_install', 'release_meta', 'boot', 'reboot', 'rollback')
AXCL_CHECKS = ('dkms', 'module_load', 'axcl_smi', 'npu', 'reboot_recovery')


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(product: str, version: str, evidence_path: Path, repository: Path) -> dict:
    evidence = json.loads(evidence_path.read_text())
    require(evidence.get('schema_version') == 1, 'hardware evidence schema must be 1')
    require(evidence.get('product') == product and evidence.get('release') == version,
            'hardware evidence release identity mismatch')
    require(evidence.get('verdict') == 'passed', 'hardware evidence verdict is not passed')
    manifest = repository / 'catalog/releases' / product / f'{version}.json'
    require(manifest.is_file(), 'release manifest is missing from repository candidate')
    require(evidence.get('package_manifest_sha256') == digest(manifest),
            'hardware evidence does not bind the exact package manifest')
    checks = evidence.get('checks')
    require(isinstance(checks, dict), 'hardware evidence checks are missing')
    for name in BASE_CHECKS:
        require(checks.get(name) == 'passed', f'hardware check did not pass: {name}')
    config = json.loads((ROOT / 'products' / product / 'product.json').read_text())
    selected = config.get('release_package_sets', [])
    plan_path = ROOT / 'products' / product / 'releases' / f'{version}.lock.json'
    if plan_path.is_file():
        plan = json.loads(plan_path.read_text())
        # An 8GB-only maintenance release retains the exact previously tested
        # 16GB bytes. Require evidence for the changed capacity, never substitute
        # the old 16GB hardware result for testing the new 8GB PAC/runtime.
        if plan.get('maintenance_adapter') == 'axcl-8g':
            selected = ['axcl-8g']
    for capacity in ('axcl-8g', 'axcl-16g'):
        if capacity not in selected:
            continue
        axcl = checks.get(capacity)
        require(isinstance(axcl, dict), f'{capacity} hardware checks are missing')
        for name in AXCL_CHECKS:
            require(axcl.get(name) == 'passed', f'{capacity} hardware check did not pass: {name}')
    artifacts = evidence.get('evidence')
    require(isinstance(artifacts, list) and artifacts, 'hardware evidence artifact list is empty')
    for item in artifacts:
        require(isinstance(item, dict) and isinstance(item.get('path'), str),
                'invalid hardware evidence artifact')
        require(re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', '')) is not None,
                'invalid hardware evidence artifact SHA-256')
        relative = Path(item['path'])
        require(not relative.is_absolute() and '..' not in relative.parts,
                'hardware evidence artifact path must be relative and contained')
        artifact = evidence_path.parent / relative
        require(artifact.is_file(), f'hardware evidence artifact is missing: {relative}')
        require(digest(artifact) == item['sha256'],
                f'hardware evidence artifact hash mismatch: {relative}')
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product')
    parser.add_argument('version')
    parser.add_argument('evidence', type=Path)
    parser.add_argument('repository', type=Path)
    args = parser.parse_args()
    try:
        validate(args.product, args.version, args.evidence.resolve(), args.repository.resolve())
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f'hardware evidence validation failed: {error}')
    print(f'validated hardware acceptance for {args.product} {args.version}')


if __name__ == '__main__':
    main()
