"""Regression tests for release-manifest semantic gating."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release_manifest.py"


def _load_script() -> ModuleType:
    """Load the release manifest script as a testable module."""
    spec = importlib.util.spec_from_file_location("release_manifest_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load release manifest script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_standard_smoke_report_is_not_release_complete() -> None:
    """A one-seed benchmark with B0-B7 evidence still cannot satisfy release targets."""
    release_manifest = _load_script()
    report = {
        "acceptance": {
            "full_published_matrix": False,
            "targets_met": False,
            "selected_seed_count": 1,
            "off_false_exact_declarations": 0,
        },
        "paired_bootstrap_confidence_intervals": {"method": "paired-seed-percentile/v1"},
        "baseline_surface": {"complete": True},
        "variants": [
            "random_final_guess",
            "full",
            "random",
            "stateless",
            "kb_no_synthesis",
            "synthesis_no_kb",
        ],
    }

    checks = release_manifest._standard_benchmark_checks(
        Path("runs/standard-benchmark-v2/standard-benchmark-report.json"),
        report,
    )
    statuses = {check["name"]: check["status"] for check in checks}

    assert statuses["standard.full_published_matrix"] == "fail"
    assert statuses["standard.targets_met"] == "fail"
    assert statuses["standard.paired_bootstrap_ci"] == "pass"
    assert statuses["standard.required_ablation_surface"] == "pass"
    assert statuses["standard.off_control_false_exact"] == "pass"


def test_state_learning_requires_independent_research_challenges() -> None:
    """M8 release evidence must prove independent challenge coverage, not only accuracy."""
    release_manifest = _load_script()
    report = {
        "targets_met": {
            "exact_history_accuracy_eq_1": True,
            "learned_state_accuracy_ge_0_95": True,
            "learned_state_beats_no_learner": True,
            "research_challenge_campaigns_ge_30": True,
            "state_model_counterexample_retracted": True,
        },
        "state_conditioned_inference": {
            "status": "complete",
            "nontrivial_constraints": 1,
        },
        "shared_private_root": False,
        "cost": {"challenge_campaigns": 30},
    }

    checks = release_manifest._state_learning_checks(
        Path("runs/state-learning-m8/state-learning-report.json"),
        report,
    )
    statuses = {check["name"]: check["status"] for check in checks}
    assert statuses["m8.measurement_targets"] == "pass"
    assert statuses["m8.state_conditioned_secret_inference"] == "pass"
    assert statuses["m8.independent_research_challenges"] == "pass"

    report["cost"] = {"challenge_campaigns": 29}
    checks = release_manifest._state_learning_checks(
        Path("runs/state-learning-m8/state-learning-report.json"),
        report,
    )
    statuses = {check["name"]: check["status"] for check in checks}
    assert statuses["m8.independent_research_challenges"] == "fail"

    report["cost"] = {"challenge_campaigns": 30}
    report["shared_private_root"] = True
    checks = release_manifest._state_learning_checks(
        Path("runs/state-learning-m8/state-learning-report.json"),
        report,
    )
    statuses = {check["name"]: check["status"] for check in checks}
    assert statuses["m8.independent_research_challenges"] == "fail"


def test_validation_commands_require_explicit_gate_evidence(tmp_path: Path) -> None:
    """Root validation gates are missing evidence unless a command log proves success."""
    release_manifest = _load_script()
    missing = release_manifest._validation_commands(None)
    assert {item["status"] for item in missing} == {"missing_evidence"}

    evidence_path = tmp_path / "validation-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "validation_commands": [
                    {
                        "command": command,
                        "status": "pass",
                        "exit_code": 0,
                        "started_at": "2026-07-16T00:00:00Z",
                        "ended_at": "2026-07-16T00:00:01Z",
                        "duration_ms": 1000,
                    }
                    for command in release_manifest.EXPECTED_ROOT_GATES
                ]
            }
        ),
        encoding="utf-8",
    )

    supplied = release_manifest._validation_commands(evidence_path)
    assert {item["status"] for item in supplied} == {"pass"}
    assert all(item["exit_code"] == 0 for item in supplied)


def test_absolute_output_path_writes_blocked_manifest(tmp_path: Path) -> None:
    """An absolute output path is printable and never crashes after writing."""
    output = tmp_path / "release-manifest.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(output)
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["status"] == "blocked"
    assert manifest["summary"]["validation_gates_pass"] is False


def test_empty_git_status_means_clean_repository(monkeypatch: Any) -> None:
    """A clean `git status --short` emits an empty string, not an unavailable state."""
    release_manifest = _load_script()

    def fake_run(
        command: tuple[str, ...],
        *,
        stderr: bool = False,
        first_line: bool = False,
        allow_empty: bool = False,
    ) -> str:
        _ = (stderr, first_line, allow_empty)
        if command == ("git", "status", "--short"):
            return ""
        if command == ("git", "rev-parse", "HEAD"):
            return "a" * 40
        if command == ("git", "branch", "--show-current"):
            return "main"
        raise AssertionError(command)

    monkeypatch.setattr(release_manifest, "_run", fake_run)

    state = release_manifest._git_state()
    assert state["dirty"] is False
    assert state["status_short"] == []
