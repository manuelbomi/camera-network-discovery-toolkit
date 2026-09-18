"""Ensure the ``src`` layout package is importable without a prior install.

This lets ``pytest`` work straight out of a fresh checkout (``pip install -r
requirements.txt`` then ``pytest``) without also requiring ``pip install -e .``.
"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
