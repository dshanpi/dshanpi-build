#!/usr/bin/env python3
"""Download three pinned repositories to a new workspace; never build or publish."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()


def checkout(destination, manifest, build_commit):
    entries = manifest['repositories']
    if set(entries) != {'ArmBianOS', 'dshanpi-build', 'dspi-config'}:
        raise ValueError('workspace must contain exactly the three delivery repositories')
    plans = []
    for name, entry in entries.items():
        commit = build_commit if name == 'dshanpi-build' and entry['commit'] == 'self' else entry['commit']
        if not re.fullmatch('[0-9a-f]{40}', commit):
            raise ValueError('workspace commit must be a full SHA: ' + name)
        target = destination / name
        if target.exists():
            raise ValueError('refusing to overwrite existing checkout: ' + str(target))
        plans.append((name, entry['url'], commit, target))
    destination.mkdir(parents=True, exist_ok=True)
    resolved = {}
    for name, url, commit, target in plans:
        # Full history retains the protected A1 baseline and old release commits.
        subprocess.run(['git', 'clone', '--quiet', '--no-checkout', '--', url, str(target)], check=True)
        git('-C', target, 'checkout', '--quiet', '--detach', commit)
        if git('-C', target, 'rev-parse', 'HEAD') != commit:
            raise ValueError('checkout does not match pinned commit: ' + name)
        resolved[name] = {'url': url, 'commit': commit}
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--lock', type=Path, default=ROOT / 'handoff/sources.json')
    args = parser.parse_args()
    if git('-C', ROOT, 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('commit or discard tracked bootstrap changes before selecting a snapshot')
    manifest = json.loads(args.lock.read_text())
    resolved = checkout(args.destination.resolve(), manifest, git('-C', ROOT, 'rev-parse', 'HEAD'))
    output = args.destination / 'workspace-lock.json'
    output.write_text(json.dumps({'repositories': resolved}, indent=2) + '\n')
    print('Pinned workspace created; no build or publication performed. Lock: ' + str(output))


if __name__ == '__main__':
    main()
