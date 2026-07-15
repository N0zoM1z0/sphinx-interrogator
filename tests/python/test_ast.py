"""Tests for the immutable public probe AST."""

from sphinx_interrogator.ast import Program


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


def test_generated_program_requires_halt() -> None:
    """Generated programs reject an empty instruction sequence."""
    try:
        Program(())
    except ValueError as error:
        assert "at least one" in str(error)
    else:
        raise AssertionError("empty program unexpectedly accepted")
