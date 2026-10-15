#!/usr/bin/env python3
"""Assemble the explicit 8GB maintenance release using the shared AXCL adapter."""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('axcl_release', Path(__file__).with_name('build-axcl-16g-release.py'))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
if __name__ == '__main__':
    adapter.main(capacity=8)
