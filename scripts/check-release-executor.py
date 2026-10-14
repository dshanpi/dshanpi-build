#!/usr/bin/env python3
"""Prevent complete image builds from consuming GitHub-hosted Actions minutes."""

import json
from pathlib import Path
import sys


def validate(lock_path: Path, operation: str, executor: str) -> None:
    if operation not in {"testing", "testing-packages", "stable", "withdraw", "purge"}:
        raise ValueError(f"unsupported release operation: {operation}")
    if executor not in {"github-hosted", "local"}:
        raise ValueError(f"unsupported release executor: {executor}")
    lock = json.loads(lock_path.read_text())
    if operation == "testing" and "image_release" in lock and executor != "local":
        raise ValueError(
            "complete image releases must be built on the controlled local builder and "
            "uploaded directly to ArmBianOS Releases; GitHub-hosted Actions are reserved "
            "for DEB, signed APT index, and promotion operations"
        )
    if operation == "testing-packages" and "image_release" not in lock:
        raise ValueError("testing-packages requires a complete image release lock")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: check-release-executor.py RELEASE_LOCK OPERATION github-hosted|local"
        )
    try:
        validate(Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3])
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"release executor gate: {error}")
    print(f"release executor gate passed: {sys.argv[2]} on {sys.argv[3]}")
