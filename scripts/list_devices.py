#!/usr/bin/env python3
"""Emit a GitHub Actions JSON matrix from checked-in device definitions."""

import argparse
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1] / 'devices'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--only', default='all')
args = parser.parse_args()
names = sorted(p.stem for p in root.glob('*.json'))
if not names or any(json.loads((root / f'{name}.json').read_text())['id'] != name for name in names):
    sys.exit('no devices or inconsistent device filenames')
if args.only != 'all':
    if args.only not in names:
        sys.exit(f'unknown device {args.only}; available: {names}')
    names = [args.only]
print(json.dumps(names))
