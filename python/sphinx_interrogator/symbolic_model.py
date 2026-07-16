"""Solver-independent symbolic bank, fault, and reduced state-transition equations."""

from __future__ import annotations

from sphinx_interrogator.constraint_ir import Expr, ExprOp, Sort
from sphinx_interrogator.target_model import SBOX4


def bank_expression(secret: Expr, token: Expr, epoch: Expr) -> Expr:
    """Return the version-1 two-bit bank projection with explicit-width operations."""
    nibble = Sort.bitvector(4)
    epoch_sort = Sort.bitvector(1)
    if secret.sort != nibble or token.sort != nibble or epoch.sort != epoch_sort:
        raise ValueError("bank expression requires BV4 secret/token and BV1 epoch")
    transformed = Expr(ExprOp.BV_XOR, nibble, (secret, token))
    substituted = _sbox_expression(transformed)
    low = Expr(ExprOp.BV_EXTRACT, Sort.bitvector(2), (substituted,), parameters=(1, 0))
    high = Expr(ExprOp.BV_EXTRACT, Sort.bitvector(2), (substituted,), parameters=(3, 2))
    return Expr(
        ExprOp.ITE,
        Sort.bitvector(2),
        (
            Expr.equal(epoch, Expr.literal(epoch_sort, 0)),
            low,
            high,
        ),
    )


def reference_fault_expression(collision: Expr, guard: Expr, suppressed: Expr) -> Expr:
    """Return the Boolean reference-fault predicate."""
    boolean = Sort.bool()
    if any(item.sort != boolean for item in (collision, guard, suppressed)):
        raise ValueError("fault predicate requires Boolean operands")
    return Expr.conjunction(
        (
            collision,
            guard,
            Expr(ExprOp.NOT, boolean, (suppressed,)),
        )
    )


def replay_next_expression(replay_credit: Expr, collision: Expr) -> Expr:
    """Return the saturating two-bit replay-credit transition."""
    credit_sort = Sort.bitvector(2)
    if replay_credit.sort != credit_sort or collision.sort != Sort.bool():
        raise ValueError("replay transition requires BV2 credit and Boolean collision")
    zero = Expr.literal(credit_sort, 0)
    one = Expr.literal(credit_sort, 1)
    three = Expr.literal(credit_sort, 3)
    increment = Expr(
        ExprOp.ITE,
        credit_sort,
        (
            Expr.equal(replay_credit, three),
            three,
            Expr(ExprOp.BV_ADD, credit_sort, (replay_credit, one)),
        ),
    )
    decrement = Expr(
        ExprOp.ITE,
        credit_sort,
        (
            Expr.equal(replay_credit, zero),
            zero,
            Expr(ExprOp.BV_SUB, credit_sort, (replay_credit, one)),
        ),
    )
    return Expr(ExprOp.ITE, credit_sort, (collision, increment, decrement))


def probe_phase_next_expression(phase: Expr, epoch: Expr) -> Expr:
    """Return the two-bit `phase + 1 + epoch` probe transition."""
    phase_sort = Sort.bitvector(2)
    epoch_sort = Sort.bitvector(1)
    if phase.sort != phase_sort or epoch.sort != epoch_sort:
        raise ValueError("phase transition requires BV2 phase and BV1 epoch")
    epoch_as_phase = Expr(
        ExprOp.ITE,
        phase_sort,
        (
            Expr.equal(epoch, Expr.literal(epoch_sort, 0)),
            Expr.literal(phase_sort, 0),
            Expr.literal(phase_sort, 1),
        ),
    )
    plus_one = Expr(ExprOp.BV_ADD, phase_sort, (phase, Expr.literal(phase_sort, 1)))
    return Expr(ExprOp.BV_ADD, phase_sort, (plus_one, epoch_as_phase))


def _sbox_expression(value: Expr) -> Expr:
    nibble = Sort.bitvector(4)
    result = Expr.literal(nibble, SBOX4[-1])
    for index in reversed(range(15)):
        result = Expr(
            ExprOp.ITE,
            nibble,
            (
                Expr.equal(value, Expr.literal(nibble, index)),
                Expr.literal(nibble, SBOX4[index]),
                result,
            ),
        )
    return result
