"""Tests for robust paired timing estimators and grouped soft evidence."""

from __future__ import annotations

import random

from sphinx_interrogator.constraint_ir import ConstraintProgram, Expr, NamedAssumption, Sort
from sphinx_interrogator.solver import HypothesisStore
from sphinx_interrogator.statistics import (
    CorrelatedPair,
    SequentialDecisionKind,
    SequentialSignConfig,
    calibrated_soft_weight,
    grouped_soft_constraint,
    median_of_means,
    paired_location,
    sequential_sign_decision,
)


def test_median_of_means_resists_one_large_outlier() -> None:
    """A single extreme sample should not dominate grouped location estimation."""
    estimate = median_of_means([1.0, 1.0, 1.0, 1.0, 1000.0], groups=5)
    assert estimate == 1.0


def test_paired_location_preserves_direction() -> None:
    """Follow-up-minus-source estimates should retain the intended sign."""
    estimate = paired_location([10.0, 11.0, 9.0], [11.0, 12.0, 10.0])
    assert estimate.location == 1.0
    assert estimate.confidence == 1.0


def _pairs(seed: int, effect: int) -> tuple[CorrelatedPair, ...]:
    generator = random.Random(seed)
    pairs = []
    for index in range(48):
        source_noise = generator.randint(-2, 2)
        follow_noise = generator.randint(-2, 2)
        if generator.random() < 0.02:
            follow_noise += generator.choice((-8, 8))
        pairs.append(
            CorrelatedPair(
                f"seed-{seed}:block-{index}",
                100 + source_noise,
                100 + effect + follow_noise,
            )
        )
    return tuple(pairs)


def _preference_program(value: int) -> ConstraintProgram:
    secret = Expr.variable("secret_0", Sort.bitvector(4))
    predicate = Expr.equal(secret, Expr.literal(secret.sort, value))
    return ConstraintProgram(
        "1.0",
        (secret,),
        (NamedAssumption("soft-direction", predicate, "statistical-test", ("fake",)),),
        Expr.literal(Sort.bool(), True),
    )


def test_predeclared_sequential_rule_stops_for_signal_but_not_for_equality() -> None:
    """A robust directional result stops early; all ties remain inconclusive."""
    positive = sequential_sign_decision(_pairs(11, 4))
    assert positive.kind is SequentialDecisionKind.POSITIVE
    assert positive.stopped_early
    assert positive.pairs_used >= 12
    assert positive.adjusted_p_value is not None
    ties = tuple(CorrelatedPair(f"tie-{index}", 7.0, 7.0) for index in range(48))
    inconclusive = sequential_sign_decision(ties)
    assert inconclusive.kind is SequentialDecisionKind.INCONCLUSIVE
    assert inconclusive.pairs_used == 48
    assert inconclusive.adjusted_p_value is None


def test_deterministic_mixture_simulation_calibrates_false_positive_and_power() -> None:
    """Fixed synthetic distributions bound null errors and retain effect-two power."""
    config = SequentialSignConfig()
    null = [sequential_sign_decision(_pairs(seed, 0), config) for seed in range(1_000)]
    signaled = [sequential_sign_decision(_pairs(seed, 2), config) for seed in range(1_000)]
    null_false = sum(item.kind is not SequentialDecisionKind.INCONCLUSIVE for item in null)
    positive = sum(item.kind is SequentialDecisionKind.POSITIVE for item in signaled)
    assert null_false <= 10
    assert positive >= 950
    assert all(item.approximation == "probabilistic-soft" for item in (*null, *signaled))


def test_soft_weights_are_monotone_capped_and_group_correlated_repetitions_once() -> None:
    """One logical experiment produces one capped MaxSMT group with full provenance."""
    weaker = sequential_sign_decision(_pairs(10, 2))
    stronger = sequential_sign_decision(_pairs(10, 4))
    assert calibrated_soft_weight(stronger) >= calibrated_soft_weight(weaker) > 0
    group = grouped_soft_constraint(
        "soft-anchor",
        _preference_program(7),
        stronger,
        maximum_weight=5,
    )
    assert group is not None
    assert not group.hard
    assert group.weight == 5
    assert len(group.provenance) == stronger.pairs_used
    store = HypothesisStore(max_soft_group_weight=5)
    store.add(group)
    assert store.high_influence_soft_groups(limit=1) == (group,)
    assert store.optimize_soft().satisfied_groups == ("soft-anchor",)

    ties = tuple(CorrelatedPair(f"tie-{index}", 1.0, 1.0) for index in range(48))
    assert (
        grouped_soft_constraint(
            "not-equality",
            _preference_program(8),
            sequential_sign_decision(ties),
        )
        is None
    )
