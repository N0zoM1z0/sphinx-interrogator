"""Tests for public evaluation CSV/plot artifact export."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
EXPORT_SCRIPT = ROOT / "scripts/export_evaluation_artifacts.py"
RELEASE_SCRIPT = ROOT / "scripts/release_manifest.py"


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_evaluation_artifacts_writes_csv_plots_and_manifest(tmp_path: Path) -> None:
    """Exporter turns public reports and event logs into release-bound artifacts."""
    export = _load_script("export_evaluation_artifacts_script", EXPORT_SCRIPT)
    release_manifest = _load_script("release_manifest_for_evaluation_artifacts", RELEASE_SCRIPT)
    standard_report, state_report, reducer_report = _write_fixture_reports(tmp_path)

    result = export.build_artifacts(
        output=tmp_path / "exports",
        standard_report=standard_report,
        state_report=state_report,
        reducer_report=reducer_report,
    )

    manifest_path = Path(result["path"])
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "spec/evaluation-artifacts.schema.json").read_text("utf-8"))
    jsonschema.Draft202012Validator(schema).validate(manifest)
    assert manifest["private_artifacts_included"] is False
    assert manifest["row_counts"] == {
        "campaign_results": 1,
        "query_events": 1,
        "relation_decisions": 1,
        "state_learning": 5,
        "reducer_families": 1,
    }

    relation_csv = manifest_path.parent / "csv/relation-decisions.csv"
    with relation_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["constraint_count"] == "1"
    assert rows[0]["certificate_id"] == "cert-fixture"
    assert rows[0]["constraint_approximations"] == '["bounded"]'

    plot = manifest_path.parent / "plots/state-learning-accuracy.svg"
    assert "Held-Out State-Learning Accuracy" in plot.read_text(encoding="utf-8")

    checks = release_manifest._evaluation_artifacts_checks(Path(result["path"]), manifest)
    assert {check["status"] for check in checks} == {"pass"}


def _write_fixture_reports(tmp_path: Path) -> tuple[Path, Path, Path]:
    standard_root = tmp_path / "standard"
    run = standard_root / "runs/full-reference-seed-1"
    run.mkdir(parents=True)
    (run / "report.json").write_text(
        json.dumps({"campaign_id": "campaign-fixture"}),
        encoding="utf-8",
    )
    (run / "events.jsonl").write_text(
        "\n".join(
            json.dumps(event, sort_keys=True)
            for event in (
                {
                    "kind": "query_created",
                    "payload": {
                        "program_sha256": "a" * 64,
                        "query_id": "q-source",
                    },
                    "sequence": 1,
                },
                {
                    "kind": "relation_recorded",
                    "payload": {
                        "relation": {
                            "certificate": {"certificate_id": "cert-fixture"},
                            "emits_secret_constraints": True,
                            "relation_id": "repeat-amplify/v1",
                            "reset_policy": "hard",
                        },
                        "relation_instance_id": "rel-1",
                    },
                    "sequence": 2,
                },
                {
                    "kind": "execution_recorded",
                    "payload": {
                        "batch_id": "batch-1",
                        "execution_id": "exec-1",
                        "position": 0,
                        "query_id": "q-source",
                        "request_id": "req-1",
                        "response": {
                            "budget": {
                                "logical_queries_used": 1,
                                "physical_executions_used": 1,
                            },
                            "observation": {
                                "bucket_width": 4,
                                "cycle_bucket": 55,
                            },
                            "ok": True,
                            "public_metrics": {
                                "retired_instructions": 7,
                                "static_cycles": 42,
                            },
                            "status": "halted",
                        },
                    },
                    "sequence": 3,
                },
                {
                    "kind": "decision_recorded",
                    "payload": {
                        "decision": {
                            "source_request_ids": ["req-1"],
                        },
                        "kind": "bounded_greater",
                        "relation_instance_id": "rel-1",
                    },
                    "sequence": 4,
                },
                {
                    "kind": "constraint_added",
                    "payload": {
                        "approximation": "bounded",
                        "relation_instance_id": "rel-1",
                    },
                    "sequence": 5,
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    standard_report = standard_root / "standard-benchmark-report.json"
    standard_report.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "challenge_id": "challenge-fixture",
                        "cost": {
                            "hard_resets": 1,
                            "logical_relation_families": 1,
                            "physical_executions": 1,
                        },
                        "fault_assignment": "reference",
                        "judge_accepted": True,
                        "remaining_secret_candidates": 1,
                        "run": "runs/full-reference-seed-1",
                        "seed": 1,
                        "selector_mode": "full",
                        "status": "unique_exact",
                    }
                ],
                "summaries": [
                    {
                        "exact_rate": 1.0,
                        "fault_assignment": "reference",
                        "median_logical_relation_families": 1.0,
                        "selector_mode": "full",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state_report = tmp_path / "state-learning-report.json"
    state_report.write_text(
        json.dumps(
            {
                "state_conditioned_inference": {
                    "constraint_groups": [
                        {
                            "anchor_bank": 1,
                            "effective_nibble_candidates_after": 4,
                            "effective_nibble_candidates_before": 16,
                            "measurement_request_id": "req-state",
                            "output": "MEASURE_HIGH",
                            "state_label": "s0",
                        }
                    ],
                    "model_id": "model-fixture",
                },
                "variants": [
                    {
                        "counterexamples": 0,
                        "exact_matches": 1,
                        "held_out_accuracy": 1.0,
                        "mode": "learned_state",
                        "model_id": "model-fixture",
                        "states": 2,
                        "training_cost": {
                            "challenge_campaigns": 1,
                            "logical_queries": 2,
                            "physical_executions": 2,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    reducer_report = tmp_path / "reduced-witnesses-report.json"
    reducer_report.write_text(
        json.dumps(
            {
                "families": [
                    {
                        "artifact_sha256": "b" * 64,
                        "blocked_reasons": [],
                        "family": "repeat-amplify/v1",
                        "measured_replay": [{}],
                        "original": {"cost": {"combined_static_cycles": 50}},
                        "reduced": {"cost": {"combined_static_cycles": 20}},
                        "status": "minimized",
                        "steps": [{}, {}],
                    }
                ],
                "summary": {"reset_policy_honored": True},
            }
        ),
        encoding="utf-8",
    )
    return standard_report, state_report, reducer_report
