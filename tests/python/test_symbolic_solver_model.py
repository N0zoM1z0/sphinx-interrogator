"""Exhaustive concrete-versus-Z3 checks for bank, fault, and reduced state IR."""

from __future__ import annotations

import itertools

from sphinx_interrogator.constraint_ir import ConstraintProgram, Expr, ExprOp, Sort
from sphinx_interrogator.solver import ConstraintGroup, HypothesisStore, SolverStatus
from sphinx_interrogator.symbolic_model import (
    bank_expression,
    probe_phase_next_expression,
    reference_fault_expression,
    replay_next_expression,
)
from sphinx_interrogator.target_model import bank_of


def _mismatch_is_unsat(
    declarations: tuple[Expr, ...],
    symbolic: Expr,
    expected: Expr,
    fixed: tuple[Expr, ...],
) -> None:
    mismatch = Expr(ExprOp.NOT, Sort.bool(), (Expr.equal(symbolic, expected),))
    assertion = Expr.conjunction((*fixed, mismatch))
    store = HypothesisStore()
    store.add(
        ConstraintGroup(
            "differential",
            ConstraintProgram("1.0", declarations, (), assertion),
        )
    )
    assert store.solve().status is SolverStatus.UNSAT


def test_z3_bank_expression_matches_all_concrete_cells() -> None:
    """All 16x16x2 public mapping inputs agree after actual Z3 translation."""
    secret = Expr.variable("secret", Sort.bitvector(4))
    token = Expr.variable("token", Sort.bitvector(4))
    epoch = Expr.variable("epoch", Sort.bitvector(1))
    symbolic = bank_expression(secret, token, epoch)
    for secret_value, token_value, epoch_value in itertools.product(range(16), range(16), range(2)):
        fixed = (
            Expr.equal(secret, Expr.literal(secret.sort, secret_value)),
            Expr.equal(token, Expr.literal(token.sort, token_value)),
            Expr.equal(epoch, Expr.literal(epoch.sort, epoch_value)),
        )
        expected = Expr.literal(
            Sort.bitvector(2),
            bank_of(secret_value, token_value, epoch_value),
        )
        _mismatch_is_unsat((secret, token, epoch), symbolic, expected, fixed)


def test_z3_fault_replay_and_phase_match_complete_reduced_state_domain() -> None:
    """Boolean fault and every two-bit transition input agree with concrete equations."""
    collision = Expr.variable("collision", Sort.bool())
    guard = Expr.variable("guard", Sort.bool())
    suppressed = Expr.variable("suppressed", Sort.bool())
    fault = reference_fault_expression(collision, guard, suppressed)
    for values in itertools.product((False, True), repeat=3):
        fixed = tuple(
            Expr.equal(variable, Expr.literal(Sort.bool(), value))
            for variable, value in zip((collision, guard, suppressed), values, strict=True)
        )
        expected = Expr.literal(Sort.bool(), values[0] and values[1] and not values[2])
        _mismatch_is_unsat((collision, guard, suppressed), fault, expected, fixed)

    replay = Expr.variable("replay", Sort.bitvector(2))
    replay_next = replay_next_expression(replay, collision)
    for credit, is_collision in itertools.product(range(4), (False, True)):
        expected_credit = min(3, credit + 1) if is_collision else max(0, credit - 1)
        fixed = (
            Expr.equal(replay, Expr.literal(replay.sort, credit)),
            Expr.equal(collision, Expr.literal(collision.sort, is_collision)),
        )
        _mismatch_is_unsat(
            (replay, collision),
            replay_next,
            Expr.literal(replay.sort, expected_credit),
            fixed,
        )

    phase = Expr.variable("phase", Sort.bitvector(2))
    epoch = Expr.variable("epoch", Sort.bitvector(1))
    phase_next = probe_phase_next_expression(phase, epoch)
    for phase_value, epoch_value in itertools.product(range(4), range(2)):
        fixed = (
            Expr.equal(phase, Expr.literal(phase.sort, phase_value)),
            Expr.equal(epoch, Expr.literal(epoch.sort, epoch_value)),
        )
        _mismatch_is_unsat(
            (phase, epoch),
            phase_next,
            Expr.literal(phase.sort, (phase_value + 1 + epoch_value) & 3),
            fixed,
        )
