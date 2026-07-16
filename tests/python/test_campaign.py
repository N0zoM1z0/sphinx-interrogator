"""End-to-end test of the deterministic tutorial interrogation scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sphinx_interrogator.campaign import (
    CampaignController,
    CampaignMode,
    ControllerContext,
    TutorialCampaign,
)
from sphinx_interrogator.model import ExecutionObservation, ExecutionResult
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.solver import bank_of


@dataclass(slots=True)
class ExactFakeClient:
    """Minimal black-box-compatible exact target used only by this unit test."""

    secret: tuple[int, ...]
    counter: int = 0

    def execute(
        self,
        program: str,
        *,
        session_id: str,
        logical_batch_id: str,
        reset: str = "hard",
        registers: tuple[int, ...] = (),
        execution_seed_id: str | None = None,
    ) -> ExecutionResult:
        """Evaluate the public experiment subset without exposing private state."""
        del logical_batch_id, reset, registers, execution_seed_id
        phase = 0
        static_cycles = 0
        fault_cycles = 0
        pending: tuple[int, int, bool] | None = None
        retired = 0
        for raw_line in program.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            retired += 1
            opcode, *rest = line.split(maxsplit=1)
            operands = [] if not rest else [int(value.strip()) for value in rest[0].split(",")]
            if opcode == "PAD":
                amount = operands[0]
                static_cycles += amount
                phase = (phase + amount) & 0b11
            elif opcode == "PROBE":
                lane, token, epoch = operands
                static_cycles += 5
                guard = phase == ((lane ^ token ^ epoch) & 0b11)
                pending = (bank_of(self.secret[lane], token, epoch), epoch, guard)
                phase = (phase + 1 + epoch) & 0b11
            elif opcode == "ANCHOR":
                anchor, epoch = operands
                static_cycles += 4
                if pending is not None:
                    bank, pending_epoch, guard = pending
                    if pending_epoch == epoch and bank == anchor and guard:
                        fault_cycles += 1
                pending = None
            elif opcode == "FENCE":
                static_cycles += 2
                pending = None
            elif opcode == "HALT":
                static_cycles += 1
                break
            else:
                raise AssertionError(f"unexpected test opcode {opcode}")
        self.counter += 1
        cycles = static_cycles + fault_cycles
        return ExecutionResult(
            request_id=f"fake-{self.counter}",
            session_id=session_id,
            status="halted",
            public_digest="0000000000000000",
            observation=ExecutionObservation(cycles, 1),
            retired_instructions=retired,
            static_cycles=static_cycles,
            physical_executions_used=self.counter,
            physical_executions_remaining=10_000 - self.counter,
            logical_queries_used=self.counter // 2,
            logical_queries_remaining=10_000 - self.counter // 2,
            hard_resets_used=self.counter,
            hard_resets_remaining=10_000 - self.counter,
            server_version="0.1.0",
            profile_version="0.1.0",
        )


def test_tutorial_campaign_recovers_two_ordered_nibbles() -> None:
    """The reference loop should synthesize relations until the exact secret is unique."""
    target = ExactFakeClient((3, 13))
    campaign = TutorialCampaign(cast("VmClient", target), cells=2)
    assert campaign.run(maximum_steps=64) == (3, 13)
    assert campaign.domain.candidate_count() == 1
    assert campaign.knowledge_base.relations


def test_campaign_controller_exposes_all_public_modes() -> None:
    """The integrated selector surface covers all required interrogation modes."""
    controller = CampaignController()
    context = ControllerContext(secret_cells=2)
    report = controller.plan_report(context)

    assert controller.available_modes() == (
        CampaignMode.INFER,
        CampaignMode.LEARN_STATE,
        CampaignMode.CALIBRATE,
        CampaignMode.REPLAY,
        CampaignMode.REDUCE,
        CampaignMode.DIVERSIFY,
    )
    assert report["modes"] == [
        "infer",
        "learn-state",
        "calibrate",
        "replay",
        "reduce",
        "diversify",
    ]
    assert report["private_artifacts_included"] is False
    assert report["black_box_boundary"] == "public-jsonl-process-only"
    actions = {action["mode"]: action for action in report["actions"]}
    assert set(actions) == set(report["modes"])
    assert actions["infer"]["payload"]["status"] == "ready"
    assert actions["infer"]["payload"]["relation_family"] == "anchor-switch/v1"
    encoded_report = repr(report).lower()
    assert "private_root" not in encoded_report
    assert "private_path" not in encoded_report
    assert "secret.bin" not in encoded_report


def test_campaign_controller_can_select_replay_from_public_group_ids() -> None:
    """Mode restriction should route to replay without reading private evidence."""
    controller = CampaignController()
    context = ControllerContext(
        high_influence_group_ids=("group:relation:7",),
        uncovered_relation_families=("soft-history-contrast/v1",),
    )

    selected = controller.select(context, allowed=(CampaignMode.REPLAY,))
    assert selected.mode is CampaignMode.REPLAY
    assert selected.payload["status"] == "ready"
    assert selected.payload["group_ids"] == ("group:relation:7",)

    diversified = controller.select(context, allowed=("diversify",))
    assert diversified.mode is CampaignMode.DIVERSIFY
    assert diversified.payload["target_family"] == "soft-history-contrast/v1"
