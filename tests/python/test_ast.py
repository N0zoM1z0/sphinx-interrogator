"""Tests for the independent immutable public probe AST and parser."""

from contextlib import suppress
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sphinx_interrogator.ast import DslError, Instruction, Op, Program

FIXTURES = Path(__file__).parents[1] / "fixtures" / "programs"


def test_experiment_cell_has_expected_static_cost() -> None:
    """A one-repeat cell should match the documented public timing envelope."""
    program = Program.experiment_cell(
        lane=0,
        token=3,
        epoch=1,
        anchor=2,
        pad=2,
    )
    assert program.static_cycles() == 14
    assert program.render() == ("PAD 2\nPROBE 0, 3, 1\nANCHOR 2, 1\nFENCE\nHALT\n")


def test_cross_language_golden_corpus_covers_every_opcode() -> None:
    """Python independently agrees with the canonical text, AST, and hash fixtures."""
    source = (FIXTURES / "full-v1.source.spx").read_text(encoding="utf-8")
    canonical = (FIXTURES / "full-v1.canonical.spx").read_text(encoding="utf-8")
    expected_hash = (FIXTURES / "full-v1.sha256").read_text(encoding="ascii").strip()
    expected_ast = (FIXTURES / "full-v1.ast.json").read_text(encoding="ascii").strip()

    program = Program.parse(source, lanes=4, max_instructions=128, max_gas=4_096)

    assert {instruction.op for instruction in program.instructions} == set(Op)
    assert program.render() == canonical
    assert program.canonical_sha256() == expected_hash
    assert program.canonical_ast_json() == expected_ast
    assert Program.parse(canonical, lanes=4).render() == canonical
    assert program.resources().instructions == 26
    assert program.resources().static_cycles == 45
    assert program.resources().encoded_gas == 45
    assert program.effects().reads_memory
    assert program.effects().writes_memory
    assert program.effects().changes_control_flow
    assert program.effects().writes_digest
    assert program.effects().experiment_instructions == 4


@pytest.mark.parametrize("op", list(Op))
def test_every_opcode_rejects_wrong_arity(op: Op) -> None:
    """Each typed node rejects an operand count inconsistent with its opcode."""
    invalid_operands = (0,) if op in {Op.RET, Op.FENCE, Op.HALT} else ()
    with pytest.raises(ValueError, match="expects"):
        Instruction(op, invalid_operands)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "no instruction"),
        ("MOVI r0, 0\n", "end with HALT"),
        ("MOVI r8, 0\nHALT\n", "register"),
        ("MOVI r01, 0\nHALT\n", "register"),
        ("MOVI r0, 65536\nHALT\n", "16-bit"),
        ("MOVI r0, \u0661\nHALT\n", "invalid immediate"),
        ("SHL r0, r0, 16\nHALT\n", "shift amount"),
        ("LOAD r0, [r1 + 32768]\nHALT\n", "not i16"),
        ("LOAD r0, [r1 + -1]\nHALT\n", "invalid memory offset"),
        ("PROBE 4, 0, 0\nHALT\n", "outside 0..4"),
        ("PROBE 0, 16, 0\nHALT\n", "token"),
        ("ANCHOR 4, 0\nHALT\n", "bank"),
        ("again: PAD 1\nagain: HALT\n", "duplicate label"),
        ("JMP absent\nHALT\n", "unknown label"),
        ("start: PAD 1\nJMP start\nHALT\n", "backward control"),
        ("LOOP 1, later\nlater: HALT\n", "must not be forward"),
        ("RET\nHALT\n", "empty return stack"),
    ],
)
def test_parser_reports_operand_label_and_control_failures(source: str, message: str) -> None:
    """Malformed source is rejected before it can be executed."""
    with pytest.raises(DslError, match=message):
        Program.parse(source, lanes=4)


def test_profile_instruction_limit_is_enforced() -> None:
    """Encoded instruction count is checked before program use."""
    with pytest.raises(DslError, match="instructions exceed"):
        Program.parse("PAD 1\nHALT\n", lanes=1, max_instructions=1)


def test_generated_program_requires_halt_and_immutable_collections() -> None:
    """Direct AST construction preserves the immutable finite-program invariant."""
    with pytest.raises(ValueError, match="at least one"):
        Program(())
    with pytest.raises(TypeError, match="immutable tuple"):
        Program([])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="immutable tuple"):
        Instruction(Op.HALT, [])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="repeats"):
        Program.experiment_cell(lane=0, token=0, epoch=0, anchor=0, repeats=4_097)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=512))
def test_arbitrary_bounded_text_has_only_structured_parse_failures(source: str) -> None:
    """Bounded Unicode input either validates or raises the public DSL error type."""
    with suppress(DslError):
        Program.parse(source, lanes=4)
