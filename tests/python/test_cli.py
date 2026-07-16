"""Public CLI tests for campaign inspection and deterministic replay."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from sphinx_interrogator.cli import main
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository


def test_inspect_and_replay_commands_report_public_materialized_state(tmp_path: Path) -> None:
    """A persisted run can be inspected and rebuilt without target-private access."""
    run = tmp_path / "run"
    repository = CampaignRepository.create(
        run,
        CampaignManifest(
            campaign_id="cli-campaign",
            challenge_id="public-challenge",
            challenge_commitment="0" * 64,
            profile_name="tutorial",
            semantic_version="0.1.0",
            public_profile_sha256="5" * 64,
            seed=47,
            minimum_certificate_strength="exhaustive-enumeration",
            logical_query_budget=80,
            physical_execution_budget=240,
            hard_reset_budget=240,
        ),
    )
    repository.close()

    runner = CliRunner()
    inspected = runner.invoke(main, ["inspect", "--run", str(run)])
    assert inspected.exit_code == 0, inspected.output
    report = json.loads(inspected.output)
    assert report["campaign_id"] == "cli-campaign"
    assert report["event_count"] == 0

    replayed = runner.invoke(main, ["replay", "--run", str(run)])
    assert replayed.exit_code == 0, replayed.output
    replay = json.loads(replayed.output)
    assert replay["matched"] is True
    assert replay["before_digest"] == replay["after_digest"]


def test_doctor_and_reduce_commands_are_noninteractive(tmp_path: Path) -> None:
    """Release CLI exposes doctor and reducer reports without target-private access."""
    runner = CliRunner()

    doctor = runner.invoke(main, ["doctor"])
    assert doctor.exit_code == 0, doctor.output
    doctor_report = json.loads(doctor.output)
    assert doctor_report["black_box_boundary"] == "public-jsonl-process-only"
    assert "reduce" in doctor_report["commands"]

    output = tmp_path / "reduced.json"
    reduced = runner.invoke(
        main,
        [
            "reduce",
            "--family",
            "repeat-amplify/v1",
            "--output",
            str(output),
        ],
    )
    assert reduced.exit_code == 0, reduced.output
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "minimized"
    assert report["preservation"]["uses_true_secret"] is False


def test_benchmark_command_reads_nested_acceptance_contract(tmp_path: Path) -> None:
    """CLI must not report false failure for a schema-valid accepted benchmark."""
    report_path = tmp_path / "benchmark.json"
    report_path.write_text(
        json.dumps(
            {
                "variants": ["full", "random"],
                "acceptance": {
                    "targets_met": True,
                    "full_published_matrix": True,
                },
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(main, ["benchmark", "--report", str(report_path)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["targets_met"] is True
    assert report["full_published_matrix"] is True
