"""Tests for research-profile state-learning macros and reports."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

import pytest

from sphinx_interrogator.learner import OneStateLearner
from sphinx_interrogator.model import ExecutionObservation, ExecutionResult
from sphinx_interrogator.research_state import (
    MEASURE_HIGH,
    MEASURE_LOW,
    MEASURE_SYMBOL,
    STEP_OK,
    STEP_SYMBOL,
    ResearchMacroConfig,
    calibrate_measurement,
    execute_membership_sequence,
    measure_program,
    research_alphabet,
    step_program,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate_state_learning.py"


def _load_state_script() -> ModuleType:
    """Load the M8 evaluation script so pure report helpers can be tested."""
    spec = importlib.util.spec_from_file_location("evaluate_state_learning_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load evaluate_state_learning.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeExecutor:
    """Small public executor with a calibrated high anchor."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def execute(
        self,
        program: str,
        *,
        session_id: str,
        logical_batch_id: str,
        reset: str = "hard",
        registers: Sequence[int] = (),
        memory: Mapping[int, int] | None = None,
        execution_seed_id: str | None = None,
        request_id: str | None = None,
    ) -> ExecutionResult:
        """Return deterministic public buckets based on request IDs."""
        del program, session_id, logical_batch_id, registers, memory, execution_seed_id
        if request_id is None:
            raise ValueError("fake executor requires request_id")
        self.calls.append((request_id, reset))
        bucket = 112 if request_id.endswith("-2") or request_id.endswith("-01") else 105
        static_cycles = 841 if "-cal-" in request_id or request_id.endswith("-01") else 2
        return ExecutionResult(
            request_id=request_id,
            session_id="fake-session",
            status="halted",
            public_digest="0",
            observation=ExecutionObservation(cycle_bucket=bucket, bucket_width=8),
            retired_instructions=1,
            static_cycles=static_cycles,
            physical_executions_used=1,
            physical_executions_remaining=999,
            logical_queries_used=1,
            logical_queries_remaining=999,
            hard_resets_used=1,
            hard_resets_remaining=99,
            server_version="0.1.0",
            profile_version="0.1.0",
        )


def test_research_macros_fit_profile_and_amplify_fault_cycles() -> None:
    """The public macros stay within research profile limits and separate buckets."""
    config = ResearchMacroConfig()
    measure = measure_program(0, config)
    step = step_program(config)

    assert measure.resources().instructions == 241
    assert measure.static_cycles() == 841
    assert measure.resources().encoded_gas == 841
    assert step.resources().instructions == 2
    assert step.static_cycles() == 2


def test_calibration_and_sequence_discretization_use_public_buckets() -> None:
    """Calibration picks the public high anchor and classifies membership outputs."""
    executor = FakeExecutor()
    config = ResearchMacroConfig()
    calibration = calibrate_measurement(
        executor,
        config=config,
        session_prefix="test",
        request_prefix="test",
        logical_batch_id="calibration",
        repetitions=1,
    )
    assert calibration.anchor_bank == 2
    assert calibration.threshold_bucket == 109

    trace = execute_membership_sequence(
        executor,
        (STEP_SYMBOL, MEASURE_SYMBOL),
        calibration=calibration,
        config=config,
        session_id="word",
        logical_batch_id="batch",
        request_prefix="word",
    )
    assert trace.outputs == (STEP_OK, MEASURE_HIGH)
    assert trace.steps[0].reset == "hard"
    assert trace.steps[1].reset == "none"


def test_one_state_learner_supports_per_symbol_outputs() -> None:
    """M8 no-learner baseline can emit fixed outputs for different macro symbols."""
    alphabet = research_alphabet()
    model = OneStateLearner().learn(
        model_id="per-symbol",
        alphabet=alphabet,
        outputs_by_symbol={STEP_SYMBOL: STEP_OK, MEASURE_SYMBOL: MEASURE_HIGH},
    )

    assert model.predict((STEP_SYMBOL, MEASURE_SYMBOL, MEASURE_SYMBOL)) == (
        STEP_OK,
        MEASURE_HIGH,
        MEASURE_HIGH,
    )
    with pytest.raises(ValueError, match="cover the input alphabet"):
        OneStateLearner().learn(
            model_id="bad",
            alphabet=alphabet,
            outputs_by_symbol={STEP_SYMBOL: MEASURE_LOW},
        )


def test_state_conditioned_constraint_is_nontrivial_and_state_bound() -> None:
    """M8 report helpers emit a real projection constraint, not literal true."""
    script = _load_state_script()
    candidates = script._effective_nibble_values(anchor_bank=2, token=0, epoch=0)
    assert 0 < len(candidates) < 16

    program = script._state_conditioned_constraint_program(
        group_id="constraint:test",
        model_id="model-1",
        state_label="q0",
        candidate_values=candidates,
        source_request_ids=("request-1",),
        states=("q0", "q1"),
    )

    assert program.assertion.to_data()["op"] != "literal"
    assert program.assertion.evaluate(
        {"effective_nibble_lane_0": candidates[0], "learned_state": "q0"}
    )
    rejected = next(value for value in "0123456789abcdef" if value not in candidates)
    assert not program.assertion.evaluate(
        {"effective_nibble_lane_0": rejected, "learned_state": "q0"}
    )
    assert not program.assertion.evaluate(
        {"effective_nibble_lane_0": candidates[0], "learned_state": "q1"}
    )
