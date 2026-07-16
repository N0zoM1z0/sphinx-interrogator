"""Tests for public standard-profile audit artifacts."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/audit_standard_profile.py"


def _load_script() -> ModuleType:
    """Load the audit script as a testable module."""
    spec = importlib.util.spec_from_file_location("audit_standard_profile_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load audit script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mutation_ladder_shows_fault_free_and_aggregate_separation() -> None:
    """The audit should distinguish off, weaker, signed, and reference aggregate costs."""
    audit = _load_script()

    ladder = audit._mutation_ladder()
    stateful = ladder["stateful_three_cell_control"]

    assert ladder["targets_met"]["aggregate_separation"] is True
    assert stateful["off"]["aggregate_fault_cycles"] == 0
    assert stateful["weak"]["aggregate_fault_cycles"] == 1
    assert stateful["signed"]["aggregate_fault_cycles"] == 1
    assert stateful["reference"]["aggregate_fault_cycles"] == 2
    assert ladder["aggregate_order"] == ["off", "weak", "signed", "reference"]


def test_standard_profile_audit_targets_include_mutation_controls(tmp_path: Path) -> None:
    """The generated audit report should make mutation separation a release-visible target."""
    output = tmp_path / "audit"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((output / "standard-profile-audit.json").read_text(encoding="utf-8"))
    assert report["report_version"] == "1.1"
    assert report["targets_met"]["mutation_controls_separated"] is True
    assert report["mutation_ladder"]["targets_met"]["aggregate_separation"] is True
