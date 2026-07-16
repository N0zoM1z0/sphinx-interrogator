"""Robust paired estimators for coarse and noisy relational observations."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import median

from sphinx_interrogator.constraint_ir import ConstraintProgram
from sphinx_interrogator.solver import ConstraintGroup


@dataclass(frozen=True, slots=True)
class PairedEstimate:
    """Robust estimate and conservative uncertainty summary for paired deltas."""

    location: float
    median_absolute_deviation: float
    confidence: float
    samples: int


class SequentialDecisionKind(StrEnum):
    """Probabilistic soft-evidence outcomes; absence of evidence is inconclusive."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class CorrelatedPair:
    """One source/follow-up block counted once regardless of within-block reuse."""

    correlation_group: str
    source: float
    follow_up: float

    def __post_init__(self) -> None:
        if not self.correlation_group:
            raise ValueError("correlated pairs require a group ID")
        if not math.isfinite(self.source) or not math.isfinite(self.follow_up):
            raise ValueError("correlated pair observations must be finite")

    @property
    def delta(self) -> float:
        """Return follow-up minus source."""
        return self.follow_up - self.source


@dataclass(frozen=True, slots=True)
class SequentialSignConfig:
    """Predeclared robust sign-test checkpoints and family-wise error target."""

    minimum_pairs: int = 12
    maximum_pairs: int = 48
    check_every: int = 4
    familywise_alpha: float = 0.01
    dead_zone: float = 0.0
    minimum_nonzero: int = 8
    mom_groups: int = 4

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_pairs <= self.maximum_pairs:
            raise ValueError("sequential pair bounds are inconsistent")
        if self.check_every < 1 or self.minimum_nonzero < 1 or self.mom_groups < 1:
            raise ValueError("sequential sample/group counts must be positive")
        if not 0.0 < self.familywise_alpha < 1.0:
            raise ValueError("familywise alpha must lie strictly between zero and one")
        if self.dead_zone < 0.0 or not math.isfinite(self.dead_zone):
            raise ValueError("dead zone must be finite and nonnegative")

    @property
    def checkpoints(self) -> tuple[int, ...]:
        """Return the fixed looks used for Bonferroni alpha spending."""
        values = list(range(self.minimum_pairs, self.maximum_pairs + 1, self.check_every))
        if values[-1] != self.maximum_pairs:
            values.append(self.maximum_pairs)
        return tuple(values)


@dataclass(frozen=True, slots=True)
class SequentialDecision:
    """Auditable robust decision used only to construct grouped soft evidence."""

    kind: SequentialDecisionKind
    estimate: PairedEstimate
    pairs_used: int
    nonzero_pairs: int
    one_sided_p_value: float | None
    adjusted_p_value: float | None
    alpha_per_look: float
    stopped_early: bool
    correlation_groups: tuple[str, ...]
    approximation: str = "probabilistic-soft"

    def __post_init__(self) -> None:
        if self.approximation != "probabilistic-soft":
            raise ValueError("sequential decisions must remain explicitly probabilistic")
        if self.pairs_used != len(self.correlation_groups):
            raise ValueError("decision pair count disagrees with correlation provenance")
        if len(set(self.correlation_groups)) != len(self.correlation_groups):
            raise ValueError("correlation groups must be unique decision units")
        if self.kind is SequentialDecisionKind.INCONCLUSIVE:
            if self.one_sided_p_value is not None or self.adjusted_p_value is not None:
                raise ValueError("inconclusive decisions cannot carry a significance claim")
        elif self.one_sided_p_value is None or self.adjusted_p_value is None:
            raise ValueError("directional decisions require calibrated p-values")

    def to_data(self) -> dict[str, object]:
        """Return stable public statistical evidence metadata."""
        return {
            "kind": self.kind.value,
            "location": self.estimate.location,
            "median_absolute_deviation": self.estimate.median_absolute_deviation,
            "pairs_used": self.pairs_used,
            "nonzero_pairs": self.nonzero_pairs,
            "one_sided_p_value": self.one_sided_p_value,
            "adjusted_p_value": self.adjusted_p_value,
            "alpha_per_look": self.alpha_per_look,
            "stopped_early": self.stopped_early,
            "correlation_groups": list(self.correlation_groups),
            "approximation": self.approximation,
        }


def median_of_means(values: Sequence[float], groups: int) -> float:
    """Estimate a location by taking the median of approximately equal group means."""
    if not values:
        raise ValueError("median_of_means requires at least one value")
    if groups < 1 or groups > len(values):
        raise ValueError("groups must be between one and the sample count")
    buckets: list[list[float]] = [[] for _ in range(groups)]
    for index, value in enumerate(values):
        buckets[index % groups].append(value)
    means = [sum(bucket) / len(bucket) for bucket in buckets]
    return float(median(means))


def paired_location(
    source_samples: Sequence[float],
    follow_up_samples: Sequence[float],
    *,
    groups: int | None = None,
) -> PairedEstimate:
    """Estimate follow-up minus source using interleaved paired measurements."""
    if len(source_samples) != len(follow_up_samples):
        raise ValueError("paired sample sequences must have equal length")
    if not source_samples:
        raise ValueError("at least one pair is required")
    deltas = [right - left for left, right in zip(source_samples, follow_up_samples, strict=True)]
    group_count = groups if groups is not None else max(1, int(math.sqrt(len(deltas))))
    location = median_of_means(deltas, min(group_count, len(deltas)))
    absolute_deviations = [abs(value - location) for value in deltas]
    mad = float(median(absolute_deviations))
    if mad == 0.0:
        confidence = 1.0 if len(deltas) >= 3 else 0.75
    else:
        signal = abs(location) / (mad + 1e-12)
        confidence = min(0.999, 1.0 - math.exp(-signal * math.sqrt(len(deltas))))
    return PairedEstimate(
        location=location,
        median_absolute_deviation=mad,
        confidence=confidence,
        samples=len(deltas),
    )


def sequential_sign_decision(
    pairs: Sequence[CorrelatedPair],
    config: SequentialSignConfig | None = None,
) -> SequentialDecision:
    """Run a robust exact sign test at fixed Bonferroni-corrected checkpoints."""
    resolved = SequentialSignConfig() if config is None else config
    if len(pairs) < resolved.minimum_pairs:
        raise ValueError("insufficient pairs for the predeclared first checkpoint")
    considered = tuple(pairs[: resolved.maximum_pairs])
    identifiers = tuple(pair.correlation_group for pair in considered)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("each sequential decision unit needs a unique correlation group")
    alpha_per_look = resolved.familywise_alpha / len(resolved.checkpoints)
    for checkpoint in resolved.checkpoints:
        if checkpoint > len(considered):
            break
        current = considered[:checkpoint]
        deltas = tuple(pair.delta for pair in current)
        positive = sum(delta > resolved.dead_zone for delta in deltas)
        negative = sum(delta < -resolved.dead_zone for delta in deltas)
        nonzero = positive + negative
        estimate = paired_location(
            tuple(pair.source for pair in current),
            tuple(pair.follow_up for pair in current),
            groups=min(resolved.mom_groups, checkpoint),
        )
        if nonzero >= resolved.minimum_nonzero:
            positive_p = _binomial_upper_tail(positive, nonzero)
            negative_p = _binomial_upper_tail(negative, nonzero)
            if estimate.location > resolved.dead_zone and positive_p <= alpha_per_look:
                return _directional_decision(
                    SequentialDecisionKind.POSITIVE,
                    estimate,
                    checkpoint,
                    nonzero,
                    positive_p,
                    resolved,
                    identifiers[:checkpoint],
                    alpha_per_look,
                )
            if estimate.location < -resolved.dead_zone and negative_p <= alpha_per_look:
                return _directional_decision(
                    SequentialDecisionKind.NEGATIVE,
                    estimate,
                    checkpoint,
                    nonzero,
                    negative_p,
                    resolved,
                    identifiers[:checkpoint],
                    alpha_per_look,
                )
    used = min(len(considered), resolved.maximum_pairs)
    final = considered[:used]
    estimate = paired_location(
        tuple(pair.source for pair in final),
        tuple(pair.follow_up for pair in final),
        groups=min(resolved.mom_groups, used),
    )
    nonzero = sum(abs(pair.delta) > resolved.dead_zone for pair in final)
    return SequentialDecision(
        SequentialDecisionKind.INCONCLUSIVE,
        estimate,
        used,
        nonzero,
        None,
        None,
        alpha_per_look,
        False,
        identifiers[:used],
    )


def calibrated_soft_weight(
    decision: SequentialDecision,
    *,
    maximum_weight: int = 20,
    weight_per_decade: int = 3,
) -> int:
    """Map adjusted evidence monotonically to one capped correlation-group weight."""
    if maximum_weight < 1 or weight_per_decade < 1:
        raise ValueError("soft-weight parameters must be positive")
    if decision.kind is SequentialDecisionKind.INCONCLUSIVE:
        return 0
    assert decision.adjusted_p_value is not None
    decades = max(0.0, -math.log10(max(decision.adjusted_p_value, 1e-300)))
    return min(maximum_weight, max(1, math.floor(decades * weight_per_decade)))


def grouped_soft_constraint(
    group_id: str,
    program: ConstraintProgram,
    decision: SequentialDecision,
    *,
    maximum_weight: int = 20,
) -> ConstraintGroup | None:
    """Create at most one capped soft group for one correlated logical experiment."""
    weight = calibrated_soft_weight(decision, maximum_weight=maximum_weight)
    if weight == 0:
        return None
    return ConstraintGroup(
        group_id,
        program,
        hard=False,
        weight=weight,
        provenance=tuple(f"correlation:{group}" for group in decision.correlation_groups),
    )


def bucket_midpoint(cycle_bucket: int, bucket_width: int) -> float:
    """Map a public bucket to the midpoint of its represented cycle interval."""
    if cycle_bucket < 0 or bucket_width < 1:
        raise ValueError("invalid timing bucket")
    lower = cycle_bucket * bucket_width
    return lower + (bucket_width - 1) / 2.0


def _directional_decision(
    kind: SequentialDecisionKind,
    estimate: PairedEstimate,
    checkpoint: int,
    nonzero: int,
    p_value: float,
    config: SequentialSignConfig,
    correlation_groups: tuple[str, ...],
    alpha_per_look: float,
) -> SequentialDecision:
    adjusted = min(1.0, p_value * len(config.checkpoints))
    return SequentialDecision(
        kind,
        estimate,
        checkpoint,
        nonzero,
        p_value,
        adjusted,
        alpha_per_look,
        checkpoint < config.maximum_pairs,
        correlation_groups,
    )


def _binomial_upper_tail(successes: int, trials: int) -> float:
    if not 0 <= successes <= trials:
        raise ValueError("binomial counts are inconsistent")
    numerator = sum(math.comb(trials, count) for count in range(successes, trials + 1))
    return float(numerator) / float(2**trials)
