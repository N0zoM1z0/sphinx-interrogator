"""Independent typed AST, parser, validator, and formatter for the public probe DSL."""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Op(StrEnum):
    """Version-1 public SphinxVM opcodes."""

    MOVI = "MOVI"
    MOV = "MOV"
    ADD = "ADD"
    XOR = "XOR"
    AND = "AND"
    OR = "OR"
    SHL = "SHL"
    SHR = "SHR"
    LOAD = "LOAD"
    STORE = "STORE"
    CMP = "CMP"
    JMP = "JMP"
    JZ = "JZ"
    JNZ = "JNZ"
    CALL = "CALL"
    RET = "RET"
    LOOP = "LOOP"
    MIXOUT = "MIXOUT"
    PROBE = "PROBE"
    ANCHOR = "ANCHOR"
    PAD = "PAD"
    FENCE = "FENCE"
    HALT = "HALT"


_ARITY: Final[dict[Op, int]] = {
    Op.MOVI: 2,
    Op.MOV: 2,
    Op.ADD: 3,
    Op.XOR: 3,
    Op.AND: 3,
    Op.OR: 3,
    Op.SHL: 3,
    Op.SHR: 3,
    Op.LOAD: 3,
    Op.STORE: 3,
    Op.CMP: 2,
    Op.JMP: 1,
    Op.JZ: 1,
    Op.JNZ: 1,
    Op.CALL: 1,
    Op.RET: 0,
    Op.LOOP: 2,
    Op.MIXOUT: 1,
    Op.PROBE: 3,
    Op.ANCHOR: 2,
    Op.PAD: 1,
    Op.FENCE: 0,
    Op.HALT: 0,
}

_SOURCE_ARITY: Final[dict[Op, int]] = {**_ARITY, Op.LOAD: 2, Op.STORE: 2}

_STATIC_CYCLES: Final[dict[Op, int]] = {
    Op.MOVI: 1,
    Op.MOV: 1,
    Op.ADD: 2,
    Op.XOR: 2,
    Op.AND: 2,
    Op.OR: 2,
    Op.SHL: 2,
    Op.SHR: 2,
    Op.LOAD: 3,
    Op.STORE: 3,
    Op.CMP: 1,
    Op.JMP: 1,
    Op.JZ: 1,
    Op.JNZ: 1,
    Op.CALL: 1,
    Op.RET: 1,
    Op.LOOP: 1,
    Op.MIXOUT: 1,
    Op.PROBE: 5,
    Op.ANCHOR: 4,
    Op.PAD: 0,
    Op.FENCE: 2,
    Op.HALT: 1,
}

_REGISTER_POSITIONS: Final[dict[Op, tuple[int, ...]]] = {
    Op.MOVI: (0,),
    Op.MOV: (0, 1),
    Op.ADD: (0, 1, 2),
    Op.XOR: (0, 1, 2),
    Op.AND: (0, 1, 2),
    Op.OR: (0, 1, 2),
    Op.SHL: (0, 1),
    Op.SHR: (0, 1),
    Op.LOAD: (0, 1),
    Op.STORE: (0, 2),
    Op.CMP: (0, 1),
    Op.MIXOUT: (0,),
}

_BRANCH_OPS: Final[frozenset[Op]] = frozenset({Op.JMP, Op.JZ, Op.JNZ, Op.CALL})
_CONTROL_OPS: Final[frozenset[Op]] = _BRANCH_OPS | frozenset({Op.RET, Op.LOOP})
_EXPERIMENT_OPS: Final[frozenset[Op]] = frozenset({Op.PROBE, Op.ANCHOR, Op.PAD, Op.FENCE})
_LABEL_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_RETURN_STACK_LIMIT: Final[int] = 16
_MAX_ABSTRACT_STATES: Final[int] = 65_536
_MAX_GENERATED_REPEATS: Final[int] = 4_096


class DslError(ValueError):
    """Location-aware public DSL parse, validation, or limit error."""

    def __init__(
        self,
        kind: str,
        message: str,
        *,
        line: int | None = None,
        column: int = 1,
        instruction: int | None = None,
    ) -> None:
        self.kind = kind
        self.message = message
        self.line = line
        self.column = column
        self.instruction = instruction
        if line is not None:
            rendered = f"line {line}, column {column}: {message}"
        elif instruction is not None:
            rendered = f"instruction {instruction}: {message}"
        else:
            rendered = f"program {kind}: {message}"
        super().__init__(rendered)


@dataclass(frozen=True, slots=True)
class EffectSummary:
    """Deterministic public summary of possible architectural effects."""

    reads_memory: bool
    writes_memory: bool
    changes_control_flow: bool
    writes_digest: bool
    experiment_instructions: int


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    """Deterministic static resource summary for encoded instructions."""

    instructions: int
    static_cycles: int
    encoded_gas: int


@dataclass(frozen=True, slots=True)
class Instruction:
    """One validated instruction using numeric, opcode-specific operands.

    Branch targets are zero-based instruction indices. LOAD operands are
    ``(destination, base, signed_offset)`` and STORE operands are
    ``(base, signed_offset, source)``. Canonical rendering supplies labels and
    register prefixes, so this representation is stable and unambiguous.
    """

    op: Op
    operands: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        """Validate the complete opcode-local operand domain."""
        if not isinstance(self.op, Op):
            raise TypeError("instruction op must be an Op")
        if not isinstance(self.operands, tuple):
            raise TypeError("instruction operands must be an immutable tuple")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in self.operands):
            raise TypeError("instruction operands must be integers")
        expected = _ARITY[self.op]
        if len(self.operands) != expected:
            raise ValueError(f"{self.op.value} expects {expected} operands")
        for position in _REGISTER_POSITIONS.get(self.op, ()):
            _require_range(self.operands[position], 0, 7, f"{self.op.value} register")
        if self.op is Op.MOVI:
            _require_range(self.operands[1], 0, 65_535, "MOVI immediate")
        elif self.op in {Op.SHL, Op.SHR}:
            _require_range(self.operands[2], 0, 15, f"{self.op.value} shift amount")
        elif self.op in {Op.LOAD, Op.STORE}:
            _require_range(self.operands[2 if self.op is Op.LOAD else 1], -32_768, 32_767, "offset")
        elif self.op in _BRANCH_OPS:
            _require_range(self.operands[0], 0, None, f"{self.op.value} target")
        elif self.op is Op.LOOP:
            _require_range(self.operands[0], 0, 65_535, "LOOP count")
            _require_range(self.operands[1], 0, None, "LOOP target")
        elif self.op is Op.PROBE:
            lane, token, epoch = self.operands
            _require_range(lane, 0, None, "PROBE lane")
            _require_range(token, 0, 15, "PROBE token")
            _require_range(epoch, 0, 1, "PROBE epoch")
        elif self.op is Op.ANCHOR:
            bank, epoch = self.operands
            _require_range(bank, 0, 3, "ANCHOR bank")
            _require_range(epoch, 0, 1, "ANCHOR epoch")
        elif self.op is Op.PAD:
            _require_range(self.operands[0], 0, 65_535, "PAD amount")

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

    def branch_target(self) -> int | None:
        """Return a resolved control-flow target, if present."""
        if self.op in _BRANCH_OPS:
            return self.operands[0]
        if self.op is Op.LOOP:
            return self.operands[1]
        return None

    def static_cycles(self) -> int:
        """Return the documented public one-retirement static cost."""
        if self.op is Op.PAD:
            return self.operands[0]
        return _STATIC_CYCLES[self.op]

    def gas_cost(self) -> int:
        """Return the gas charged for one retirement."""
        return max(self.static_cycles(), 1)

    def render(self) -> str:
        """Render this resolved instruction in canonical version-1 syntax."""
        op = self.op.value
        if self.op in {Op.RET, Op.FENCE, Op.HALT}:
            return op
        if self.op is Op.MOVI:
            register, value = self.operands
            return f"{op} r{register}, {value}"
        if self.op is Op.MOV:
            destination, source = self.operands
            return f"{op} r{destination}, r{source}"
        if self.op in {Op.ADD, Op.XOR, Op.AND, Op.OR}:
            destination, left, right = self.operands
            return f"{op} r{destination}, r{left}, r{right}"
        if self.op in {Op.SHL, Op.SHR}:
            destination, source, amount = self.operands
            return f"{op} r{destination}, r{source}, {amount}"
        if self.op is Op.LOAD:
            destination, base, offset = self.operands
            return f"LOAD r{destination}, {_render_address(base, offset)}"
        if self.op is Op.STORE:
            base, offset, source = self.operands
            return f"STORE {_render_address(base, offset)}, r{source}"
        if self.op is Op.CMP:
            left, right = self.operands
            return f"CMP r{left}, r{right}"
        if self.op in _BRANCH_OPS:
            return f"{op} {_canonical_label(self.operands[0])}"
        if self.op is Op.LOOP:
            count, target = self.operands
            return f"LOOP {count}, {_canonical_label(target)}"
        if self.op is Op.MIXOUT:
            return f"MIXOUT r{self.operands[0]}"
        return f"{op} " + ", ".join(str(value) for value in self.operands)

    def to_data(self) -> dict[str, object]:
        """Return the stable public typed-AST representation."""
        return {"op": self.op.value, "operands": list(self.operands)}


@dataclass(frozen=True, slots=True)
class Program:
    """A finite, immutable, resolved, and structurally validated program."""

    instructions: tuple[Instruction, ...]

    def __post_init__(self) -> None:
        """Reject mutable, empty, malformed, or unterminated programs."""
        if not isinstance(self.instructions, tuple):
            raise TypeError("program instructions must be an immutable tuple")
        if any(not isinstance(instruction, Instruction) for instruction in self.instructions):
            raise TypeError("program entries must be Instruction values")
        _validate_program(self.instructions, lanes=None, max_instructions=None, max_gas=None)

    @classmethod
    def parse(
        cls,
        source: str,
        *,
        lanes: int,
        max_instructions: int = 128,
        max_gas: int = 4_096,
    ) -> Program:
        """Independently parse and validate public DSL text."""
        if not isinstance(source, str):
            raise TypeError("program source must be text")
        if lanes <= 0:
            raise DslError("limit", "profile declares zero lanes")
        labels: dict[str, int] = {}
        unresolved: list[tuple[Op, tuple[int | str, ...], int]] = []
        for line_number, raw_line in enumerate(source.splitlines(), start=1):
            line = _strip_comment(raw_line).strip()
            if not line:
                continue
            instruction_text = line
            if ":" in line:
                candidate, instruction_text = line.split(":", maxsplit=1)
                label = candidate.strip()
                if _LABEL_RE.fullmatch(label) is None:
                    raise _parse_error(line_number, f"invalid label {label!r}")
                if label in labels:
                    raise _parse_error(line_number, f"duplicate label {label}")
                labels[label] = len(unresolved)
                instruction_text = instruction_text.strip()
            if instruction_text:
                op, operands = _parse_instruction(instruction_text, line_number)
                unresolved.append((op, operands, line_number))
        if not unresolved:
            raise _parse_error(1, "program contains no instruction")

        instructions: list[Instruction] = []
        for op, operands, line_number in unresolved:
            resolved: list[int] = []
            for operand in operands:
                if isinstance(operand, str):
                    try:
                        resolved.append(labels[operand])
                    except KeyError as error:
                        raise _parse_error(line_number, f"unknown label {operand}") from error
                else:
                    resolved.append(operand)
            try:
                instructions.append(Instruction(op, tuple(resolved)))
            except (TypeError, ValueError) as error:
                raise _parse_error(line_number, str(error)) from error
        program = cls(tuple(instructions))
        return program.validate(
            lanes=lanes,
            max_instructions=max_instructions,
            max_gas=max_gas,
        )

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
        """Build a bounded canonical probe/anchor experiment cell."""
        if not 1 <= repeats <= _MAX_GENERATED_REPEATS:
            raise ValueError(f"repeats must be in 1..={_MAX_GENERATED_REPEATS}")
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

    def validate(self, *, lanes: int, max_instructions: int, max_gas: int) -> Program:
        """Validate profile-dependent operands, resources, and control flow."""
        if lanes <= 0 or max_instructions <= 0 or max_gas < 0:
            raise DslError("limit", "profile limits must be positive")
        _validate_program(
            self.instructions,
            lanes=lanes,
            max_instructions=max_instructions,
            max_gas=max_gas,
        )
        return self

    def static_cycles(self) -> int:
        """Return the encoded one-retirement static-cycle sum."""
        return sum(instruction.static_cycles() for instruction in self.instructions)

    def resources(self) -> ResourceSummary:
        """Return deterministic static resource usage."""
        return ResourceSummary(
            instructions=len(self.instructions),
            static_cycles=self.static_cycles(),
            encoded_gas=sum(instruction.gas_cost() for instruction in self.instructions),
        )

    def effects(self) -> EffectSummary:
        """Return a conservative exact summary of encoded instruction effects."""
        ops = tuple(instruction.op for instruction in self.instructions)
        return EffectSummary(
            reads_memory=Op.LOAD in ops,
            writes_memory=Op.STORE in ops,
            changes_control_flow=any(op in _CONTROL_OPS for op in ops),
            writes_digest=Op.MIXOUT in ops,
            experiment_instructions=sum(op in _EXPERIMENT_OPS for op in ops),
        )

    def render(self) -> str:
        """Render canonical label-normalized, newline-terminated DSL text."""
        targets = {
            target
            for instruction in self.instructions
            if (target := instruction.branch_target()) is not None
        }
        lines: list[str] = []
        for index, instruction in enumerate(self.instructions):
            if index in targets:
                lines.append(f"{_canonical_label(index)}:")
            lines.append(instruction.render())
        return "".join(f"{line}\n" for line in lines)

    def canonical_sha256(self) -> str:
        """Return SHA-256 of canonical UTF-8 program text."""
        return hashlib.sha256(self.render().encode("utf-8")).hexdigest()

    def canonical_ast_json(self) -> str:
        """Serialize the resolved typed AST with stable JSON ordering."""
        data = {
            "instructions": [instruction.to_data() for instruction in self.instructions],
            "version": 1,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validate_program(
    instructions: tuple[Instruction, ...],
    *,
    lanes: int | None,
    max_instructions: int | None,
    max_gas: int | None,
) -> None:
    if not instructions:
        raise DslError("limit", "program must contain at least one instruction")
    if max_instructions is not None and len(instructions) > max_instructions:
        raise DslError(
            "limit",
            f"{len(instructions)} instructions exceed maximum {max_instructions}",
        )
    if instructions[-1].op is not Op.HALT:
        raise _validation_error(len(instructions) - 1, "program must end with HALT")
    for pc, instruction in enumerate(instructions):
        if lanes is not None and instruction.op is Op.PROBE and instruction.operands[0] >= lanes:
            raise _validation_error(
                pc,
                f"lane {instruction.operands[0]} is outside 0..{lanes}",
            )
        target = instruction.branch_target()
        if target is not None and target >= len(instructions):
            raise _validation_error(pc, f"target {target} is outside the program")
        if instruction.op in _BRANCH_OPS and target is not None and target <= pc:
            raise _validation_error(
                pc,
                "backward control flow is allowed only through LOOP",
            )
        if instruction.op is Op.LOOP and target is not None and target > pc:
            raise _validation_error(pc, "LOOP target must not be forward")
    _validate_control_flow(instructions)


def _validate_control_flow(instructions: tuple[Instruction, ...]) -> None:
    pending: deque[tuple[int, tuple[int, ...]]] = deque([(0, ())])
    visited: set[tuple[int, tuple[int, ...]]] = set()

    def enqueue(pc: int, returns: tuple[int, ...], origin: int) -> None:
        if pc >= len(instructions):
            raise _validation_error(origin, "reachable path falls off the program")
        pending.append((pc, returns))

    while pending:
        pc, returns = pending.popleft()
        state = (pc, returns)
        if state in visited:
            continue
        visited.add(state)
        if len(visited) > _MAX_ABSTRACT_STATES:
            raise DslError(
                "limit",
                f"control-flow analysis exceeds {_MAX_ABSTRACT_STATES} states",
            )
        instruction = instructions[pc]
        target = instruction.branch_target()
        if instruction.op is Op.HALT:
            continue
        if instruction.op is Op.JMP:
            enqueue(_target(target), returns, pc)
        elif instruction.op in {Op.JZ, Op.JNZ}:
            enqueue(_target(target), returns, pc)
            enqueue(pc + 1, returns, pc)
        elif instruction.op is Op.CALL:
            if len(returns) >= _RETURN_STACK_LIMIT:
                raise _validation_error(pc, "return stack may exceed 16 entries")
            enqueue(_target(target), (*returns, pc + 1), pc)
        elif instruction.op is Op.RET:
            if not returns:
                raise _validation_error(pc, "RET is reachable with an empty return stack")
            enqueue(returns[-1], returns[:-1], pc)
        elif instruction.op is Op.LOOP:
            enqueue(_target(target), returns, pc)
            enqueue(pc + 1, returns, pc)
        else:
            enqueue(pc + 1, returns, pc)


def _parse_instruction(source: str, line: int) -> tuple[Op, tuple[int | str, ...]]:
    pieces = source.split(maxsplit=1)
    opcode_text = pieces[0].upper()
    try:
        op = Op(opcode_text)
    except ValueError as error:
        raise _parse_error(line, f"unknown opcode {opcode_text}") from error
    operand_text = pieces[1].strip() if len(pieces) == 2 else ""
    operands = _split_operands(operand_text, line)
    expected = _SOURCE_ARITY[op]
    if len(operands) != expected:
        raise _parse_error(line, f"{op.value} expects {expected} operands, got {len(operands)}")

    if op is Op.MOVI:
        return op, (_parse_register(operands[0], line), _parse_word(operands[1], line))
    if op is Op.MOV:
        return op, tuple(_parse_register(value, line) for value in operands)
    if op in {Op.ADD, Op.XOR, Op.AND, Op.OR}:
        return op, tuple(_parse_register(value, line) for value in operands)
    if op in {Op.SHL, Op.SHR}:
        return op, (
            _parse_register(operands[0], line),
            _parse_register(operands[1], line),
            _parse_bounded(operands[2], line, "shift amount", 0, 15),
        )
    if op is Op.LOAD:
        base, offset = _parse_address(operands[1], line)
        return op, (_parse_register(operands[0], line), base, offset)
    if op is Op.STORE:
        base, offset = _parse_address(operands[0], line)
        return op, (base, offset, _parse_register(operands[1], line))
    if op is Op.CMP:
        return op, tuple(_parse_register(value, line) for value in operands)
    if op in _BRANCH_OPS:
        return op, (_parse_label_ref(operands[0], line),)
    if op is Op.LOOP:
        return op, (
            _parse_bounded(operands[0], line, "loop count", 0, 65_535),
            _parse_label_ref(operands[1], line),
        )
    if op is Op.MIXOUT:
        return op, (_parse_register(operands[0], line),)
    if op is Op.PROBE:
        return op, (
            _parse_bounded(operands[0], line, "lane", 0, None),
            _parse_bounded(operands[1], line, "token", 0, 15),
            _parse_bounded(operands[2], line, "epoch", 0, 1),
        )
    if op is Op.ANCHOR:
        return op, (
            _parse_bounded(operands[0], line, "bank", 0, 3),
            _parse_bounded(operands[1], line, "epoch", 0, 1),
        )
    if op is Op.PAD:
        return op, (_parse_bounded(operands[0], line, "padding", 0, 65_535),)
    return op, ()


def _split_operands(source: str, line: int) -> tuple[str, ...]:
    if not source:
        return ()
    operands = tuple(value.strip() for value in source.split(","))
    if any(not operand for operand in operands):
        raise _parse_error(line, "empty operand")
    return operands


def _parse_address(value: str, line: int) -> tuple[int, int]:
    if not value.startswith("[") or not value.endswith("]"):
        raise _parse_error(line, f"invalid memory address {value}")
    compact = "".join(value[1:-1].split())
    split_at: int | None = None
    for index, character in enumerate(compact[1:], start=1):
        if character in "+-":
            split_at = index
            break
    if split_at is None:
        return _parse_register(compact, line), 0
    register = compact[:split_at]
    magnitude = compact[split_at + 1 :]
    if not magnitude or magnitude.startswith(("+", "-")):
        raise _parse_error(line, f"invalid memory offset {value}")
    parsed = _parse_integer(magnitude, line, "memory offset")
    if compact[split_at] == "-":
        parsed = -parsed
    if not -32_768 <= parsed <= 32_767:
        raise _parse_error(line, f"memory offset {parsed} is not i16")
    return _parse_register(register, line), parsed


def _parse_register(value: str, line: int) -> int:
    if len(value) != 2 or value[0] not in "rR" or value[1] not in "0123456789":
        raise _parse_error(line, f"invalid register {value}")
    return _parse_bounded(value[1:], line, "register", 0, 7)


def _parse_word(value: str, line: int) -> int:
    parsed = _parse_integer(value, line, "immediate")
    if not -32_768 <= parsed <= 65_535:
        raise _parse_error(
            line,
            f"immediate {value} is outside signed/unsigned 16-bit syntax",
        )
    return parsed & 0xFFFF


def _parse_bounded(
    value: str,
    line: int,
    role: str,
    minimum: int,
    maximum: int | None,
) -> int:
    parsed = _parse_integer(value, line, role)
    if parsed < minimum or (maximum is not None and parsed > maximum):
        bound = f"{minimum}..={maximum}" if maximum is not None else f">={minimum}"
        raise _parse_error(line, f"{role} {value} is outside {bound}")
    return parsed


def _parse_integer(value: str, line: int, role: str) -> int:
    negative = value.startswith("-")
    magnitude = value[1:] if negative else value
    if not magnitude:
        raise _parse_error(line, f"invalid {role} {value}")
    base = 10
    if magnitude.startswith(("0x", "0X")):
        base = 16
        magnitude = magnitude[2:]
    if not magnitude:
        raise _parse_error(line, f"invalid {role} {value}")
    alphabet = "0123456789" if base == 10 else "0123456789abcdefABCDEF"
    if not magnitude.isascii() or any(character not in alphabet for character in magnitude):
        raise _parse_error(line, f"invalid {role} {value}")
    try:
        parsed = int(magnitude, base)
    except ValueError as error:
        raise _parse_error(line, f"invalid {role} {value}") from error
    return -parsed if negative else parsed


def _parse_label_ref(value: str, line: int) -> str:
    if _LABEL_RE.fullmatch(value) is None:
        raise _parse_error(line, f"invalid target label {value}")
    return value


def _strip_comment(line: str) -> str:
    positions = tuple(index for marker in ("#", ";") if (index := line.find(marker)) >= 0)
    return line[: min(positions)] if positions else line


def _render_address(base: int, offset: int) -> str:
    if offset == 0:
        return f"[r{base}]"
    if offset > 0:
        return f"[r{base} + {offset}]"
    return f"[r{base} - {-offset}]"


def _canonical_label(target: int) -> str:
    return f"L{target:03d}"


def _require_range(value: int, minimum: int, maximum: int | None, role: str) -> None:
    if value < minimum or (maximum is not None and value > maximum):
        rendered_max = str(maximum) if maximum is not None else "unbounded"
        raise ValueError(f"{role} {value} is outside {minimum}..{rendered_max}")


def _target(value: int | None) -> int:
    if value is None:
        raise AssertionError("validated control-flow instruction has no target")
    return value


def _parse_error(line: int, message: str) -> DslError:
    return DslError("parse", message, line=line)


def _validation_error(instruction: int, message: str) -> DslError:
    return DslError("validation", message, instruction=instruction)
