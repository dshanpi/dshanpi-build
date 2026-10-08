#!/usr/bin/env python3
"""Store immutable Pages payloads in Git using content-addressed 64 MiB chunks."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

LIMIT = 950_000_000  # Leave space below the Pages 1 GB limit for site metadata.
CHUNK = 64 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(source, target):
    if target.exists():
        raise ValueError("snapshot destination already exists")
    files = sorted(source.rglob("*"))
    if any(p.is_symlink() or (not p.is_file() and not p.is_dir()) for p in files):
        raise ValueError("repository contains a symlink or special file")
    if sum(p.stat().st_size for p in files if p.is_file()) > LIMIT:
        raise ValueError("repository exceeds the GitHub Pages size budget")
    (target / "objects").mkdir(parents=True)
    entries = []
    for path in files:
        if not path.is_file():
            continue
        hashes, checksum, size = [], hashlib.sha256(), 0
        with path.open("rb") as stream:
            while data := stream.read(CHUNK):
                key = digest(data)
                (target / "objects" / key).write_bytes(data)
                hashes.append(key)
                checksum.update(data)
                size += len(data)
        entries.append(dict(path=path.relative_to(source).as_posix(), size=size,
                            sha256=checksum.hexdigest(), parts=hashes))
    (target / "manifest.json").write_text(json.dumps(dict(schema=1, files=entries), indent=2) + "\n")


def decode(source, target):
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("schema") != 1 or target.exists():
        raise ValueError("invalid snapshot or destination already exists")
    total, seen = 0, set()
    target.mkdir(parents=True)
    for entry in manifest["files"]:
        path = PurePosixPath(entry["path"])
        if path.is_absolute() or str(path) != entry["path"] or ".." in path.parts or not path.parts:
            raise ValueError("unsafe snapshot path")
        if str(path) in seen or not isinstance(entry["size"], int) or entry["size"] < 0:
            raise ValueError("duplicate path or invalid size")
        seen.add(str(path))
        total += entry["size"]
        if total > LIMIT:
            raise ValueError("snapshot exceeds Pages size budget")
        output = target / path
        output.parent.mkdir(parents=True, exist_ok=True)
        checksum, size = hashlib.sha256(), 0
        with output.open("xb") as stream:
            for key in entry["parts"]:
                if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                    raise ValueError("invalid object key")
                obj = source / "objects" / key
                if obj.is_symlink() or obj.stat().st_size > CHUNK:
                    raise ValueError("invalid snapshot object")
                data = obj.read_bytes()
                size += len(data)
                if digest(data) != key or size > entry["size"]:
                    raise ValueError("snapshot object checksum or size mismatch")
                checksum.update(data)
                stream.write(data)
        if size != entry["size"] or checksum.hexdigest() != entry["sha256"]:
            raise ValueError("snapshot file checksum or size mismatch")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["encode", "decode"])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    {"encode": encode, "decode": decode}[args.command](args.source, args.target)
