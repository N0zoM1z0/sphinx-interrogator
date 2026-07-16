"""Executable typing, serialization, and concrete differential tests for the IR."""

from __future__ import annotations

import itertools
import json

import pytest

from sphinx_interrogator.constraint_ir import (
    ConstraintProgram,
    Expr,
    ExprOp,
    NamedAssumption,
    Sort,
)
from sphinx_interrogator.target_model import SBOX4, bank_of


def _sbox_expression(value: Expr) -> Expr:
    result = Expr.literal(Sort.bitvector(4), SBOX4[-1])
    for index in reversed(range(15)):
        result = Expr(
            ExprOp.ITE,
            Sort.bitvector(4),
            (
                Expr.equal(value, Expr.literal(Sort.bitvector(4), index)),
                Expr.literal(Sort.bitvector(4), SBOX4[index]),
                result,
            ),
        )
    return result


def _bank_expression(secret: Expr, token: Expr, epoch: Expr) -> Expr:
    transformed = Expr(ExprOp.BV_XOR, Sort.bitvector(4), (secret, token))
    substituted = _sbox_expression(transformed)
    low = Expr(ExprOp.BV_EXTRACT, Sort.bitvector(2), (substituted,), parameters=(1, 0))
    high = Expr(ExprOp.BV_EXTRACT, Sort.bitvector(2), (substituted,), parameters=(3, 2))
    return Expr(
        ExprOp.ITE,
        Sort.bitvector(2),
        (
            Expr.equal(epoch, Expr.literal(Sort.bitvector(1), 0)),
            low,
            high,
        ),
    )


def test_symbolic_bank_expression_matches_concrete_mapping_exhaustively() -> None:
    """Explicit-width XOR/S-box/extract semantics agree for all public cell inputs."""
    secret = Expr.variable("secret", Sort.bitvector(4))
    token = Expr.variable("token", Sort.bitvector(4))
    epoch = Expr.variable("epoch", Sort.bitvector(1))
    symbolic = _bank_expression(secret, token, epoch)
    for secret_value, token_value, epoch_value in itertools.product(range(16), range(16), range(2)):
        assert symbolic.evaluate(
            {"secret": secret_value, "token": token_value, "epoch": epoch_value}
        ) == bank_of(secret_value, token_value, epoch_value)


def test_symbolic_fault_and_replay_transition_match_reference_equations() -> None:
    """Boolean fault and saturating two-bit replay expressions cover the finite state."""
    collision = Expr.variable("collision", Sort.bool())
    guard = Expr.variable("guard", Sort.bool())
    suppress = Expr.variable("suppress", Sort.bool())
    fault = Expr.conjunction(
        (
            collision,
            guard,
            Expr(ExprOp.NOT, Sort.bool(), (suppress,)),
        )
    )
    replay = Expr.variable("replay", Sort.bitvector(2))
    zero = Expr.literal(Sort.bitvector(2), 0)
    three = Expr.literal(Sort.bitvector(2), 3)
    increment = Expr(
        ExprOp.ITE,
        Sort.bitvector(2),
        (
            Expr.equal(replay, three),
            three,
            Expr(ExprOp.BV_ADD, Sort.bitvector(2), (replay, Expr.literal(Sort.bitvector(2), 1))),
        ),
    )
    decrement = Expr(
        ExprOp.ITE,
        Sort.bitvector(2),
        (
            Expr.equal(replay, zero),
            zero,
            Expr(ExprOp.BV_SUB, Sort.bitvector(2), (replay, Expr.literal(Sort.bitvector(2), 1))),
        ),
    )
    next_replay = Expr(
        ExprOp.ITE,
        Sort.bitvector(2),
        (collision, increment, decrement),
    )
    for is_collision, is_guard, is_suppressed, credit in itertools.product(
        (False, True), (False, True), (False, True), range(4)
    ):
        environment = {
            "collision": is_collision,
            "guard": is_guard,
            "suppress": is_suppressed,
            "replay": credit,
        }
        assert fault.evaluate(environment) is (is_collision and is_guard and not is_suppressed)
        assert next_replay.evaluate(environment) == (
            min(3, credit + 1) if is_collision else max(0, credit - 1)
        )


def test_constraint_program_round_trips_named_assumptions_without_solver_objects() -> None:
    """The complete IR persists as canonical JSON and retains unsat-core provenance."""
    secret = Expr.variable("secret_0", Sort.bitvector(4))
    fault = Expr.variable(
        "fault_variant",
        Sort.finite("FaultVariant", ("off", "reference", "weak", "signed")),
    )
    bank_constraint = Expr.equal(
        _bank_expression(
            secret,
            Expr.literal(Sort.bitvector(4), 0),
            Expr.literal(Sort.bitvector(1), 0),
        ),
        Expr.literal(Sort.bitvector(2), 2),
    )
    reference_constraint = Expr.equal(
        fault,
        Expr.literal(fault.sort, "reference"),
    )
    assumption = NamedAssumption(
        "evidence_1",
        bank_constraint,
        "relation:anchor-1",
        ("request-a", "request-b", "cert:abc"),
    )
    program = ConstraintProgram(
        "1.0",
        (secret, fault),
        (assumption,),
        Expr.disjunction((bank_constraint, reference_constraint)),
    )
    encoded = program.canonical_json()
    decoded = ConstraintProgram.from_data(json.loads(encoded))
    assert decoded == program
    assert decoded.to_data() == program.to_data()
    assert "z3" not in encoded.lower()


def test_signed_unsigned_and_integer_comparisons_are_explicit() -> None:
    """The same bit pattern can be ordered differently only via named signed operators."""
    fifteen = Expr.literal(Sort.bitvector(4), 15)
    zero = Expr.literal(Sort.bitvector(4), 0)
    unsigned = Expr(ExprOp.BV_UGT, Sort.bool(), (fifteen, zero))
    signed = Expr(ExprOp.BV_SLT, Sort.bool(), (fifteen, zero))
    assert unsigned.evaluate({}) is True
    assert signed.evaluate({}) is True
    integer_sum = Expr(
        ExprOp.INT_ADD,
        Sort.int(),
        (Expr.literal(Sort.int(), -3), Expr.literal(Sort.int(), 5)),
    )
    assert integer_sum.evaluate({}) == 2


def test_ir_rejects_width_type_domain_and_shape_errors() -> None:
    """Malformed expressions fail at construction/decoding rather than coercing values."""
    with pytest.raises(ValueError, match="width"):
        Sort.bitvector(0)
    with pytest.raises(ValueError, match="outside"):
        Expr.literal(Sort.bitvector(4), 16)
    with pytest.raises(ValueError, match="finite"):
        Expr.literal(Sort.finite("Mode", ("a", "b")), "c")
    with pytest.raises(ValueError, match="equal-width"):
        Expr(
            ExprOp.BV_XOR,
            Sort.bitvector(4),
            (
                Expr.literal(Sort.bitvector(4), 0),
                Expr.literal(Sort.bitvector(3), 0),
            ),
        )
    with pytest.raises(ValueError, match="outside"):
        Expr(
            ExprOp.BV_EXTRACT,
            Sort.bitvector(2),
            (Expr.literal(Sort.bitvector(4), 0),),
            parameters=(4, 3),
        )
    with pytest.raises(ValueError, match="Boolean"):
        NamedAssumption(
            "bad",
            Expr.literal(Sort.int(), 1),
            "group",
            ("source",),
        )


def test_ir_rejects_unknown_fields_and_incomplete_declarations() -> None:
    """Strict decoding and declarations make persisted programs self-contained."""
    with pytest.raises(ValueError, match="unknown fields"):
        Sort.from_data({"kind": "bool", "width": 1})
    with pytest.raises(ValueError, match="unknown fields"):
        Expr.from_data(
            {
                "op": "literal",
                "sort": {"kind": "bool"},
                "value": True,
                "solver_hint": "ignored-by-old-readers",
            }
        )
    missing = Expr.variable("missing", Sort.bool())
    with pytest.raises(ValueError, match="undeclared variable missing"):
        ConstraintProgram("1.0", (), (), missing)
    declared = Expr.variable("value", Sort.bitvector(4))
    inconsistent = Expr.variable("value", Sort.bitvector(3))
    with pytest.raises(ValueError, match="inconsistent sort"):
        ConstraintProgram("1.0", (declared,), (), Expr.equal(inconsistent, inconsistent))
    with pytest.raises(ValueError, match="invalid fields or name"):
        Expr.variable("9invalid", Sort.bool())
