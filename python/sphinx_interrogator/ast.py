"""Typed, immutable AST for the public Sphinx probe DSL."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Op(StrEnum):
    """Opcodes implemented by the Python-side query generator scaffold."""

    MOVI = "MOVI"
    MOV = "MOV"
    ADD = "ADD"
    XOR = "XOR"
    AND = "AND"
    OR = "OR"
    SHL = "SHL"
    SHR = "SHR"
    MIXOUT = "MIXOUT"
    PROBE = "PROBE"
    ANCHOR = "ANCHOR"
    PAD = "PAD"
    FENCE = "FENCE"
    HALT = "HALT"


_ARITY: dict[Op, int] = {
    Op.MOVI: 2,
    Op.MOV: 2,
    Op.ADD: 3,
    Op.XOR: 3,
    Op.AND: 3,
    Op.OR: 3,
    Op.SHL: 3,
    Op.SHR: 3,
    Op.MIXOUT: 1,
    Op.PROBE: 3,
    Op.ANCHOR: 2,
    Op.PAD: 1,
    Op.FENCE: 0,
    Op.HALT: 0,
}

_STATIC_CYCLES: dict[Op, int] = {
    Op.MOVI: 1,
    Op.MOV: 1,
    Op.ADD: 2,
    Op.XOR: 2,
    Op.AND: 2,
    Op.OR: 2,
    Op.SHL: 2,
    Op.SHR: 2,
    Op.MIXOUT: 1,
    Op.PROBE: 5,
    Op.ANCHOR: 4,
    Op.PAD: 0,
    Op.FENCE: 2,
    Op.HALT: 1,
}


@dataclass(frozen=True, slots=True)
class Instruction:
    """One canonical instruction with integer operands.

    Register operands are represented by their numeric index. Rendering adds the
    `r` prefix according to the opcode's operand shape.
    """

    op: Op
    operands: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        """Validate arity and bounded experiment operands."""
        expected = _ARITY[self.op]
        if len(self.operands) != expected:
            raise ValueError(f"{self.op.value} expects {expected} operands")
        if self.op is Op.PROBE:
            lane, token, epoch = self.operands
            if lane < 0 or not 0 <= token <= 15 or epoch not in (0, 1):
                raise ValueError("invalid PROBE operands")
        elif self.op is Op.ANCHOR:
            bank, epoch = self.operands
            if not 0 <= bank <= 3 or epoch not in (0, 1):
                raise ValueError("invalid ANCHOR operands")
        elif self.op is Op.PAD and self.operands[0] < 0:
            raise ValueError("PAD amount must be non-negative")

    @classmethod
    def probe(cls, lane: int, token: int, epoch: int) -> Instruction:
        """Construct a probe instruction."""
        return cls(Op.PROBE, (lane, token, epoch))

    @classmethod
    def anchor(cls, bank: int, epoch: int) -> Instruction:
        """Construct a public anchor instruction."""
        return cls(Op.ANCHOR, (bank, epoch))

    @classmethod
    def pad(cls, amount: int) -> Instruction:
        """Construct a phase-padding instruction."""
        return cls(Op.PAD, (amount,))

    @classmethod
    def fence(cls) -> Instruction:
        """Construct a replay-draining fence."""
        return cls(Op.FENCE)

    @classmethod
    def halt(cls) -> Instruction:
        """Construct a halt instruction."""
        return cls(Op.HALT)

    def static_cycles(self) -> int:
        """Return the public fault-free static cost."""
        if self.op is Op.PAD:
            return self.operands[0]
        return _STATIC_CYCLES[self.op]

    def render(self) -> str:
        """Render canonical version-1 DSL syntax."""
        if self.op in {Op.FENCE, Op.HALT}:
            return self.op.value
        if self.op in {Op.MOVI}:
            register, value = self.operands
            return f"{self.op.value} r{register}, {value}"
        if self.op in {Op.MOV}:
            destination, source = self.operands
            return f"{self.op.value} r{destination}, r{source}"
        if self.op in {Op.ADD, Op.XOR, Op.AND, Op.OR}:
            destination, left, right = self.operands
            return f"{self.op.value} r{destination}, r{left}, r{right}"
        if self.op in {Op.SHL, Op.SHR}:
            destination, source, amount = self.operands
            return f"{self.op.value} r{destination}, r{source}, {amount}"
        if self.op is Op.MIXOUT:
            return f"MIXOUT r{self.operands[0]}"
        return f"{self.op.value} " + ", ".join(str(value) for value in self.operands)


@dataclass(frozen=True, slots=True)
class Program:
    """A finite immutable probe program."""

    instructions: tuple[Instruction, ...]

    def __post_init__(self) -> None:
        """Reject empty or unterminated generated programs."""
        if not self.instructions:
            raise ValueError("program must contain at least one instruction")
        if self.instructions[-1].op is not Op.HALT:
            raise ValueError("generated programs must end in HALT")

    @classmethod
    def experiment_cell(
        cls,
        *,
        lane: int,
        token: int,
        epoch: int,
        anchor: int,
        pad: int = 0,
        fence: bool = True,
        repeats: int = 1,
    ) -> Program:
        """Build a canonical probe/anchor experiment with optional amplification."""
        if repeats < 1:
            raise ValueError("repeats must be positive")
        instructions: list[Instruction] = []
        if pad:
            instructions.append(Instruction.pad(pad))
        for _ in range(repeats):
            instructions.extend(
                (
                    Instruction.probe(lane, token, epoch),
                    Instruction.anchor(anchor, epoch),
                )
            )
        if fence:
            instructions.append(Instruction.fence())
        instructions.append(Instruction.halt())
        return cls(tuple(instructions))

    def static_cycles(self) -> int:
        """Return the sum of public instruction costs."""
        return sum(instruction.static_cycles() for instruction in self.instructions)

    def render(self) -> str:
        """Render the program as canonical newline-terminated text."""
        return "".join(f"{instruction.render()}\n" for instruction in self.instructions)
