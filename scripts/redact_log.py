#!/usr/bin/env python3
"""Produce a diagnostic log without DD build parameter values."""

import os
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit('usage: redact_log.py INPUT OUTPUT')
text = Path(sys.argv[1]).read_text(errors='replace')
raw = os.environ.get('FF_REGISTERKEY_PREFIX', '')
values = {raw, raw.replace('_', ':'), os.environ.get('FF_MESH_KEY', '')}
for value in sorted((s for s in values if s), key=len, reverse=True):
    text = text.replace(value, '[REDACTED]')
Path(sys.argv[2]).write_text(text)
