"""Tests for machine-readable validation gate evidence recording."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/record_validation_gate.py"


def test_record_validation_gate_writes_and_replaces_command_evidence(tmp_path: Path) -> None:
    """A recorded gate has timestamps, exit status, and captured log digests."""
    evidence_path = tmp_path / "validation-evidence.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--evidence",
            str(evidence_path),
            "--label",
            "just fmt",
            "--",
            sys.executable,
            "-c",
            "print('format-ok')",
        ],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "sphinx-interrogator-validation-evidence/v1"
    entry = payload["validation_commands"][0]
    assert entry["command"] == "just fmt"
    assert entry["status"] == "pass"
    assert entry["exit_code"] == 0
    assert entry["started_at"].endswith("Z")
    assert entry["ended_at"].endswith("Z")
    assert entry["duration_ms"] >= 0
    assert len(entry["evidence"]["stdout_sha256"]) == 64
    assert entry["evidence"]["stdout_tail"] == ["format-ok"]

    failed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--evidence",
            str(evidence_path),
            "--label",
            "just fmt",
            "--",
            sys.executable,
            "-c",
            "import sys; print('format-failed'); sys.exit(7)",
        ],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert failed.returncode == 7
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    entries = payload["validation_commands"]
    assert len(entries) == 1
    assert entries[0]["command"] == "just fmt"
    assert entries[0]["status"] == "fail"
    assert entries[0]["exit_code"] == 7
    assert entries[0]["evidence"]["stdout_tail"] == ["format-failed"]
