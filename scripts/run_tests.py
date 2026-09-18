"""Isolated regression-test runner used by START-ARIADNE.cmd.

Python's -I flag intentionally removes the current working directory from sys.path.
The launcher still needs to test the checked-out repository itself, so this runner
adds only the repository root explicitly and then discovers tests from tests/.
It does not consult PYTHONPATH or user site-packages.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

def main() -> int:
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(TESTS),
        pattern="test*.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
