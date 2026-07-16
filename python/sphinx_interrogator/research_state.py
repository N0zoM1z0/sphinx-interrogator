"""Public research-profile state-learning macros and evidence helpers."""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from sphinx_interrogator.ast import Instruction, Program
from sphinx_interrogator.learner import (
    ConformanceResult,
    Counterexample,
    LearnedMealyMachine,
    MacroAlphabet,
)
from sphinx_interrogator.model import ExecutionResult

RESEARCH_ABSTRACTION_VERSION = "research-soft-reset-phase/v1"
RESEARCH_DISCRETIZER_VERSION = "research-bucket-threshold/v1"
STEP_SYMBOL = "step"
MEASURE_SYMBOL = "measure"
STEP_OK = "STEP_OK"
MEASURE_HIGH = "MEASURE_HIGH"
MEASURE_LOW = "MEASURE_LOW"


class PublicExecutor(Protocol):
    """Subset of the public VM client used by the state-learning macros."""

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
        """Execute one public program and return only public observations."""
        ...


@dataclass(frozen=True, slots=True)
class ResearchMacroConfig:
    """Public parameters for the robust phase-measurement macro."""

    lane: int = 0
    token: int = 0
    epoch: int = 0
    measure_repeats: int = 60
    lanes: int = 8
    max_instructions: int = 256
    max_gas: int = 32_768

    def __post_init__(self) -> None:
        if not 0 <= self.lane < self.lanes:
            raise ValueError("measurement lane is outside the public profile")
        if not 0 <= self.token <= 15:
            raise ValueError("measurement token must fit in four bits")
        if self.epoch not in {0, 1}:
            raise ValueError("measurement epoch must be zero or one")
        if self.measure_repeats < 1:
            raise ValueError("measurement repeats must be positive")
        measure = measure_program(0, self)
        step = step_program(self)
        for program in (measure, step):
            resources = program.resources()
            if resources.instructions > self.max_instructions:
                raise ValueError("state-learning macro exceeds max instructions")
            if resources.encoded_gas > self.max_gas:
                raise ValueError("state-learning macro exceeds max gas")


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    """One public hard-reset calibration measurement."""

    anchor_bank: int
    request_id: str
    cycle_bucket: int
    static_cycles: int

    def to_data(self) -> dict[str, object]:
        """Return stable report data."""
        return {
            "anchor_bank": self.anchor_bank,
            "request_id": self.request_id,
            "cycle_bucket": self.cycle_bucket,
            "static_cycles": self.static_cycles,
        }


@dataclass(frozen=True, slots=True)
class MeasurementCalibration:
    """Public threshold selected from hard-reset calibration observations."""

    anchor_bank: int
    threshold_bucket: int
    high_median_bucket: float
    runner_up_median_bucket: float
    observations: tuple[CalibrationObservation, ...]

    def to_data(self) -> dict[str, object]:
        """Return stable report data without private challenge paths."""
        medians = {
            str(bank): statistics.median(
                item.cycle_bucket for item in self.observations if item.anchor_bank == bank
            )
            for bank in sorted({item.anchor_bank for item in self.observations})
        }
        return {
            "anchor_bank": self.anchor_bank,
            "threshold_bucket": self.threshold_bucket,
            "high_median_bucket": self.high_median_bucket,
            "runner_up_median_bucket": self.runner_up_median_bucket,
            "median_buckets_by_anchor": medians,
            "observations": [item.to_data() for item in self.observations],
        }


@dataclass(frozen=True, slots=True)
class StepEvidence:
    """One public macro execution within a membership word."""

    symbol: str
    output: str
    request_id: str
    reset: str
    cycle_bucket: int
    static_cycles: int

    def to_data(self) -> dict[str, object]:
        """Return stable report data."""
        return {
            "symbol": self.symbol,
            "output": self.output,
            "request_id": self.request_id,
            "reset": self.reset,
            "cycle_bucket": self.cycle_bucket,
            "static_cycles": self.static_cycles,
        }


@dataclass(frozen=True, slots=True)
class MembershipTrace:
    """One real VM membership word and its public execution provenance."""

    sequence: tuple[str, ...]
    outputs: tuple[str, ...]
    steps: tuple[StepEvidence, ...]

    @property
    def request_ids(self) -> tuple[str, ...]:
        """Return public request provenance for this membership word."""
        return tuple(item.request_id for item in self.steps)

    def to_data(self) -> dict[str, object]:
        """Return stable report data."""
        return {
            "sequence": list(self.sequence),
            "outputs": list(self.outputs),
            "request_ids": list(self.request_ids),
            "steps": [item.to_data() for item in self.steps],
        }


def research_alphabet() -> MacroAlphabet:
    """Return the finite public alphabet for M8 research-profile learning."""
    return MacroAlphabet(
        abstraction_version=RESEARCH_ABSTRACTION_VERSION,
        input_symbols=(STEP_SYMBOL, MEASURE_SYMBOL),
        output_symbols=(STEP_OK, MEASURE_HIGH, MEASURE_LOW),
        discretizer_version=RESEARCH_DISCRETIZER_VERSION,
    )


def measure_program(anchor_bank: int, config: ResearchMacroConfig | None = None) -> Program:
    """Build the repeated phase-sensitive measurement macro for one public anchor."""
    resolved = ResearchMacroConfig() if config is None else config
    if not 0 <= anchor_bank <= 3:
        raise ValueError("anchor bank must fit in two bits")
    instructions: list[Instruction] = []
    for _ in range(resolved.measure_repeats):
        instructions.extend(
            (
                Instruction.probe(resolved.lane, resolved.token, resolved.epoch),
                Instruction.anchor(anchor_bank, resolved.epoch),
                Instruction.fence(),
                Instruction.pad(3),
            )
        )
    instructions.append(Instruction.halt())
    return Program(tuple(instructions)).validate(
        lanes=resolved.lanes,
        max_instructions=resolved.max_instructions,
        max_gas=resolved.max_gas,
    )


def step_program(config: ResearchMacroConfig | None = None) -> Program:
    """Build the public phase-step macro."""
    resolved = ResearchMacroConfig() if config is None else config
    return Program((Instruction.pad(1), Instruction.halt())).validate(
        lanes=resolved.lanes,
        max_instructions=resolved.max_instructions,
        max_gas=resolved.max_gas,
    )


def calibrate_measurement(
    executor: PublicExecutor,
    *,
    config: ResearchMacroConfig,
    session_prefix: str,
    request_prefix: str,
    logical_batch_id: str,
    repetitions: int = 3,
    minimum_bucket_gap: int = 3,
) -> MeasurementCalibration:
    """Select the colliding anchor and threshold from public hard-reset timings."""
    if repetitions < 1:
        raise ValueError("calibration repetitions must be positive")
    observations: list[CalibrationObservation] = []
    for sample_index in range(repetitions):
        for anchor_bank in range(4):
            request_id = f"{request_prefix}-cal-{sample_index}-{anchor_bank}"
            result = executor.execute(
                measure_program(anchor_bank, config).render(),
                session_id=f"{session_prefix}-cal-{sample_index}-{anchor_bank}",
                logical_batch_id=logical_batch_id,
                reset="hard",
                execution_seed_id=request_id,
                request_id=request_id,
            )
            observations.append(
                CalibrationObservation(
                    anchor_bank=anchor_bank,
                    request_id=result.request_id,
                    cycle_bucket=result.observation.cycle_bucket,
                    static_cycles=result.static_cycles,
                )
            )
    medians = {
        bank: statistics.median(
            item.cycle_bucket for item in observations if item.anchor_bank == bank
        )
        for bank in range(4)
    }
    ranked = sorted(medians.items(), key=lambda item: (item[1], -item[0]), reverse=True)
    anchor_bank, high = ranked[0]
    _runner_bank, runner_up = ranked[1]
    if high - runner_up < minimum_bucket_gap:
        raise RuntimeError(
            "measurement calibration did not separate the colliding anchor "
            f"(high={high}, runner_up={runner_up})"
        )
    return MeasurementCalibration(
        anchor_bank=anchor_bank,
        threshold_bucket=int((high + runner_up) // 2) + 1,
        high_median_bucket=float(high),
        runner_up_median_bucket=float(runner_up),
        observations=tuple(observations),
    )


def execute_membership_sequence(
    executor: PublicExecutor,
    sequence: Sequence[str],
    *,
    calibration: MeasurementCalibration,
    config: ResearchMacroConfig,
    session_id: str,
    logical_batch_id: str,
    request_prefix: str,
) -> MembershipTrace:
    """Execute one membership word from hard reset and classify public outputs."""
    word = tuple(sequence)
    if any(symbol not in {STEP_SYMBOL, MEASURE_SYMBOL} for symbol in word):
        raise ValueError("sequence contains a symbol outside the research alphabet")
    steps: list[StepEvidence] = []
    outputs: list[str] = []
    for position, symbol in enumerate(word):
        reset = "hard" if position == 0 else "none"
        request_id = f"{request_prefix}-{position:02d}"
        if symbol == STEP_SYMBOL:
            program = step_program(config)
        else:
            program = measure_program(calibration.anchor_bank, config)
        result = executor.execute(
            program.render(),
            session_id=session_id,
            logical_batch_id=logical_batch_id,
            reset=reset,
            execution_seed_id=request_id,
            request_id=request_id,
        )
        output = (
            STEP_OK
            if symbol == STEP_SYMBOL
            else discretize_measurement(result, calibration=calibration)
        )
        outputs.append(output)
        steps.append(
            StepEvidence(
                symbol=symbol,
                output=output,
                request_id=result.request_id,
                reset=reset,
                cycle_bucket=result.observation.cycle_bucket,
                static_cycles=result.static_cycles,
            )
        )
    return MembershipTrace(word, tuple(outputs), tuple(steps))


def discretize_measurement(
    result: ExecutionResult,
    *,
    calibration: MeasurementCalibration,
) -> str:
    """Map one public timing bucket into the M8 high/low output alphabet."""
    if result.observation.cycle_bucket >= calibration.threshold_bucket:
        return MEASURE_HIGH
    return MEASURE_LOW


def evaluate_model_with_traces(
    model: LearnedMealyMachine,
    traces: Iterable[MembershipTrace],
) -> ConformanceResult:
    """Evaluate a learned model against already-measured public membership traces."""
    normalized = tuple(traces)
    exact = 0
    counterexamples: list[Counterexample] = []
    for trace in normalized:
        expected = model.predict(trace.sequence)
        if expected == trace.outputs:
            exact += 1
        else:
            counterexamples.append(Counterexample(trace.sequence, expected, trace.outputs))
    return ConformanceResult(
        tested_sequences=len(normalized),
        exact_matches=exact,
        counterexamples=tuple(counterexamples),
        transition_coverage=model.transition_coverage(trace.sequence for trace in normalized),
    )
