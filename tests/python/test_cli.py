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
