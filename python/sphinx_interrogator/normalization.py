"""Certified interval normalization for exact and bounded public observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from sphinx_interrogator.model import ExecutionResult


@dataclass(frozen=True, slots=True)
class IntegerInterval:
    """Closed integer interval with total arithmetic used by bounded extractors."""

    lower: int
    upper: int

    def __post_init__(self) -> None:
        if self.lower > self.upper:
            raise ValueError("interval lower bound exceeds upper bound")

    def subtract(self, other: IntegerInterval) -> IntegerInterval:
        """Return the exact interval hull for values `self - other`."""
        return IntegerInterval(self.lower - other.upper, self.upper - other.lower)

    def integers(self) -> tuple[int, ...]:
        """Enumerate the finite represented integers."""
        return tuple(range(self.lower, self.upper + 1))


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    """Possible pre-noise fault contribution for one public cycle bucket."""

    request_id: str
    bucket_interval: IntegerInterval
    fault_interval: IntegerInterval
    static_cycles: int
    noise_bound: int


class DecisionKind(StrEnum):
    """Sound result alphabet for one ordered source/follow-up comparison."""

    EXACT_LESS = "exact_less"
    EXACT_EQUAL = "exact_equal"
    EXACT_GREATER = "exact_greater"
    BOUNDED_LESS = "bounded_less"
    BOUNDED_GREATER = "bounded_greater"
    INCONCLUSIVE = "inconclusive"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class PairDecision:
    """Auditable exact/bounded decision; delta is follow-up minus source."""

    kind: DecisionKind
    delta_interval: IntegerInterval | None
    feasible_deltas: tuple[int, ...]
    source_request_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    reason: str | None = None

    @property
    def hard_eligible(self) -> bool:
        """Return whether the decision can support a hard extractor."""
        return self.kind not in {DecisionKind.INCONCLUSIVE, DecisionKind.INVALID}

    def to_data(self) -> dict[str, object]:
        """Return stable JSON-compatible decision data."""
        return {
            "kind": self.kind.value,
            "delta_interval": None if self.delta_interval is None else asdict(self.delta_interval),
            "feasible_deltas": list(self.feasible_deltas),
            "source_request_ids": list(self.source_request_ids),
            "assumptions": list(self.assumptions),
            "reason": self.reason,
        }


def normalize_execution(result: ExecutionResult, *, noise_bound: int) -> NormalizedObservation:
    """Subtract public static cost and conservatively eliminate bounded jitter."""
    if noise_bound < 0:
        raise ValueError("noise_bound must be nonnegative")
    observation = result.observation
    if observation.cycle_bucket < 0 or observation.bucket_width < 1:
        raise ValueError("execution contains an invalid public timing bucket")
    bucket = IntegerInterval(
        observation.lower_cycle_bound,
        observation.upper_cycle_bound,
    )
    fault = IntegerInterval(
        bucket.lower - result.static_cycles - noise_bound,
        bucket.upper - result.static_cycles + noise_bound,
    )
    return NormalizedObservation(
        request_id=result.request_id,
        bucket_interval=bucket,
        fault_interval=fault,
        static_cycles=result.static_cycles,
        noise_bound=noise_bound,
    )


def decide_pair(
    source: ExecutionResult,
    follow_up: ExecutionResult,
    *,
    expected_source_static: int,
    expected_follow_up_static: int,
    noise_bound: int,
    assumptions: tuple[str, ...] = (),
) -> PairDecision:
    """Classify all deltas consistent with quantization and bounded independent noise."""
    request_ids = (source.request_id, follow_up.request_id)
    invalid_reason = _validate_pair(
        source,
        follow_up,
        expected_source_static=expected_source_static,
        expected_follow_up_static=expected_follow_up_static,
    )
    if invalid_reason is not None:
        return PairDecision(
            kind=DecisionKind.INVALID,
            delta_interval=None,
            feasible_deltas=(),
            source_request_ids=request_ids,
            assumptions=assumptions,
            reason=invalid_reason,
        )
    source_normalized = normalize_execution(source, noise_bound=noise_bound)
    follow_normalized = normalize_execution(follow_up, noise_bound=noise_bound)
    delta = follow_normalized.fault_interval.subtract(source_normalized.fault_interval)
    feasible = delta.integers()
    if delta.lower == delta.upper:
        if delta.lower < 0:
            kind = DecisionKind.EXACT_LESS
        elif delta.lower > 0:
            kind = DecisionKind.EXACT_GREATER
        else:
            kind = DecisionKind.EXACT_EQUAL
    elif delta.upper < 0:
        kind = DecisionKind.BOUNDED_LESS
    elif delta.lower > 0:
        kind = DecisionKind.BOUNDED_GREATER
    else:
        kind = DecisionKind.INCONCLUSIVE
    return PairDecision(
        kind=kind,
        delta_interval=delta,
        feasible_deltas=feasible,
        source_request_ids=request_ids,
        assumptions=assumptions,
        reason=None,
    )


def _validate_pair(
    source: ExecutionResult,
    follow_up: ExecutionResult,
    *,
    expected_source_static: int,
    expected_follow_up_static: int,
) -> str | None:
    if source.status != "halted" or follow_up.status != "halted":
        return "both executions must halt normally"
    if source.public_digest != follow_up.public_digest:
        return "architectural public digests differ"
    if source.observation.bucket_width != follow_up.observation.bucket_width:
        return "paired executions use different bucket widths"
    if source.static_cycles != expected_source_static:
        return "source public static metric disagrees with its certified program"
    if follow_up.static_cycles != expected_follow_up_static:
        return "follow-up public static metric disagrees with its certified program"
    return None
