"""Tests for standard benchmark aggregate statistics."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/benchmark_standard.py"


def _load_script() -> ModuleType:
    """Load the benchmark script as a testable module."""
    spec = importlib.util.spec_from_file_location("benchmark_standard_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load benchmark script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _result(mode: str, seed: int, logical: int, physical: int, status: str) -> dict[str, object]:
    """Build one minimal aggregate benchmark result row."""
    return {
        "selector_mode": mode,
        "fault_assignment": "reference",
        "seed": seed,
        "status": status,
        "judge_accepted": status == "unique_exact",
        "remaining_secret_candidates": 1,
        "cost": {
            "logical_relation_families": logical,
            "physical_executions": physical,
            "hard_resets": physical,
            "last_public_physical_remaining": 1000,
        },
        "challenge_id": f"challenge-{seed}",
        "run": f"runs/{mode}-{seed}",
    }


def test_paired_bootstrap_uses_common_seed_deltas() -> None:
    """Full-vs-baseline intervals are computed from paired seed differences."""
    benchmark = _load_script()
    results = [
        _result("full", 1, 10, 20, "unique_exact"),
        _result("random", 1, 15, 30, "unique_exact"),
        _result("full", 2, 20, 40, "unique_exact"),
        _result("random", 2, 30, 60, "candidate_set"),
    ]

    intervals = benchmark._paired_bootstrap_confidence_intervals(
        results,
        samples=50,
        seed=123,
        confidence_level=0.95,
    )
    comparisons = {
        item["metric"]: item for item in intervals["comparisons"] if item["baseline"] == "random"
    }

    assert comparisons["logical_relation_families_delta"]["estimate"] == -7.5
    assert comparisons["physical_executions_delta"]["estimate"] == -15.0
    assert comparisons["exact_success_delta"]["estimate"] == 0.5
    assert comparisons["logical_relation_families_delta"]["paired_seed_count"] == 2


def test_bootstrap_metrics_are_deterministic_for_single_seed() -> None:
    """One-seed smoke matrices record honest degenerate confidence intervals."""
    benchmark = _load_script()
    intervals = benchmark._paired_bootstrap_confidence_intervals(
        [_result("full", 1, 34, 68, "unique_exact")],
        samples=10,
        seed=1,
        confidence_level=0.95,
    )

    logical = next(
        item
        for item in intervals["metrics"]
        if item["selector_mode"] == "full" and item["metric"] == "logical_relation_families"
    )
    assert logical["estimate"] == 34.0
    assert logical["ci_low"] == 34.0
    assert logical["ci_high"] == 34.0
    assert intervals["comparisons"] == []


def test_baseline_surface_records_b0_to_b7_evidence(tmp_path: Path) -> None:
    """Standard reports distinguish measured, not-applicable, and development baselines."""
    benchmark = _load_script()
    upper_bound = tmp_path / "standard-profile-audit.json"
    upper_bound.write_text(
        json.dumps(
            {
                "analysis_scope": "public-symbolic-development-audit",
                "targets_met": {"oracle_collision_logical_eq_16": True},
                "learnability_bound": {"oracle_collision_logical_relations": 16},
            }
        ),
        encoding="utf-8",
    )
    results = [
        _result("random_final_guess", 1, 0, 0, "candidate_set"),
        _result("random", 1, 40, 80, "unique_exact"),
        _result("stateless", 1, 41, 82, "unique_exact"),
        _result("kb_no_synthesis", 1, 45, 90, "unique_exact"),
        _result("synthesis_no_kb", 1, 34, 68, "unique_exact"),
    ]

    surface = benchmark._baseline_surface(
        results,
        variants=[
            "random_final_guess",
            "full",
            "random",
            "stateless",
            "kb_no_synthesis",
            "synthesis_no_kb",
        ],
        upper_bound_artifact=upper_bound,
    )
    by_id = {entry["baseline_id"]: entry for entry in surface["entries"]}

    assert surface["complete"] is True
    assert by_id["B0"]["status"] == "measured"
    assert by_id["B5"]["status"] == "not_applicable"
    assert by_id["B6"]["status"] == "not_applicable"
    assert by_id["B7"]["status"] == "measured"
