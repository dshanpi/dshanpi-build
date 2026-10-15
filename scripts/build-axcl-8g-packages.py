#!/usr/bin/env python3
"""Build the explicit 8GB cohort with the shared AXCL packaging implementation."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('axcl_builder', Path(__file__).with_name('build-axcl-16g-packages.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

if __name__ == '__main__':
    builder.main(capacity=8)
