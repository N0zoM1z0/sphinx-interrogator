"""End-to-end test of the deterministic tutorial interrogation scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sphinx_interrogator.campaign import TutorialCampaign
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
