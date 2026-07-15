"""Smoke checks for formal-artifact integration scripts."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_formal_scaffold_checker_succeeds() -> None:
    """The structural checker should accept the checked-in formal files."""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_formal_scaffold.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
