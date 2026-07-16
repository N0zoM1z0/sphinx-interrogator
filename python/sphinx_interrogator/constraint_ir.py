"""Small versioned expression IR independent of any concrete SMT implementation."""

from __future__ import annotations

import builtins
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

type Scalar = bool | int | str


class SortKind(StrEnum):
    """Supported first-order scalar sorts."""

    BOOL = "bool"
    INT = "int"
    BITVECTOR = "bitvector"
    FINITE = "finite"


@dataclass(frozen=True, slots=True)
class Sort:
    """An explicit expression sort; bit-vector widths are never inferred."""

    kind: SortKind
    width: int | None = None
    name: str | None = None
    values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind is SortKind.BITVECTOR:
            if self.width is None or not 1 <= self.width <= 256:
                raise ValueError("bit-vector width must be in 1..=256")
            if self.name is not None or self.values:
                raise ValueError("bit-vector sort cannot carry finite-domain metadata")
        elif self.kind is SortKind.FINITE:
            if not self.name or not self.values or len(set(self.values)) != len(self.values):
                raise ValueError("finite sort requires a name and unique nonempty values")
            if self.width is not None:
                raise ValueError("finite sort cannot carry a bit-vector width")
        elif self.width is not None or self.name is not None or self.values:
            raise ValueError("Boolean/integer sorts cannot carry extra metadata")

    @classmethod
    def bool(cls) -> Sort:
        """Construct the Boolean sort."""
        return cls(SortKind.BOOL)

    @classmethod
    def int(cls) -> Sort:
        """Construct the unbounded mathematical integer sort."""
        return cls(SortKind.INT)

    @classmethod
    def bitvector(cls, width: builtins.int) -> Sort:
        """Construct an explicit-width bit-vector sort."""
        return cls(SortKind.BITVECTOR, width=width)

    @classmethod
    def finite(cls, name: str, values: tuple[str, ...]) -> Sort:
        """Construct a named finite enumeration sort."""
        return cls(SortKind.FINITE, name=name, values=values)

    def to_data(self) -> dict[str, object]:
        """Return stable JSON-compatible sort data."""
        data: dict[str, object] = {"kind": self.kind.value}
        if self.width is not None:
            data["width"] = self.width
        if self.name is not None:
            data["name"] = self.name
            data["values"] = list(self.values)
        return data

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> Sort:
        """Decode and validate one sort document."""
        kind = SortKind(_string(data, "kind"))
        if kind is SortKind.BITVECTOR:
            _reject_extra(data, {"kind", "width"}, "sort")
            return cls.bitvector(_integer(data, "width"))
        if kind is SortKind.FINITE:
            _reject_extra(data, {"kind", "name", "values"}, "sort")
            raw_values = _list(data, "values")
            if any(not isinstance(value, str) for value in raw_values):
                raise ValueError("finite sort values must be strings")
            return cls.finite(_string(data, "name"), tuple(cast("list[str]", raw_values)))
        _reject_extra(data, {"kind"}, "sort")
        return cls(kind)


class ExprOp(StrEnum):
    """Closed operation set understood by concrete and Z3 evaluators."""

    LITERAL = "literal"
    VARIABLE = "variable"
    NOT = "not"
    AND = "and"
    OR = "or"
    EQ = "eq"
    DISTINCT = "distinct"
    ITE = "ite"
    INT_ADD = "int_add"
    INT_SUB = "int_sub"
    INT_LT = "int_lt"
    INT_LE = "int_le"
    INT_GT = "int_gt"
    INT_GE = "int_ge"
    BV_XOR = "bv_xor"
    BV_AND = "bv_and"
    BV_OR = "bv_or"
    BV_ADD = "bv_add"
    BV_SUB = "bv_sub"
    BV_EXTRACT = "bv_extract"
    BV_ULT = "bv_ult"
    BV_ULE = "bv_ule"
    BV_UGT = "bv_ugt"
    BV_UGE = "bv_uge"
    BV_SLT = "bv_slt"
    BV_SLE = "bv_sle"
    BV_SGT = "bv_sgt"
    BV_SGE = "bv_sge"


@dataclass(frozen=True, slots=True)
class Expr:
    """Immutable, recursively typed expression node."""

    op: ExprOp
    sort: Sort
    args: tuple[Expr, ...] = ()
    value: Scalar | None = None
    name: str | None = None
    parameters: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        self._validate()

    @classmethod
    def literal(cls, sort: Sort, value: Scalar) -> Expr:
        """Construct a validated scalar literal."""
        return cls(ExprOp.LITERAL, sort, value=value)

    @classmethod
    def variable(cls, name: str, sort: Sort) -> Expr:
        """Construct a named variable declaration/reference."""
        return cls(ExprOp.VARIABLE, sort, name=name)

    @classmethod
    def equal(cls, left: Expr, right: Expr) -> Expr:
        """Construct sort-safe equality."""
        return cls(ExprOp.EQ, Sort.bool(), (left, right))

    @classmethod
    def conjunction(cls, expressions: tuple[Expr, ...]) -> Expr:
        """Construct a nonempty Boolean conjunction."""
        return cls(ExprOp.AND, Sort.bool(), expressions)

    @classmethod
    def disjunction(cls, expressions: tuple[Expr, ...]) -> Expr:
        """Construct a nonempty Boolean disjunction."""
        return cls(ExprOp.OR, Sort.bool(), expressions)

    def to_data(self) -> dict[str, object]:
        """Return a stable recursively serialized node."""
        data: dict[str, object] = {
            "op": self.op.value,
            "sort": self.sort.to_data(),
        }
        if self.args:
            data["args"] = [argument.to_data() for argument in self.args]
        if self.value is not None:
            data["value"] = self.value
        if self.name is not None:
            data["name"] = self.name
        if self.parameters:
            data["parameters"] = list(self.parameters)
        return data

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> Expr:
        """Recursively decode a node and rerun all typing checks."""
        _reject_extra(
            data,
            {"op", "sort", "args", "value", "name", "parameters"},
            "expression",
        )
        raw_sort = _mapping(data, "sort")
        raw_args = data.get("args", [])
        if not isinstance(raw_args, list):
            raise ValueError("expression args must be a list")
        arguments = []
        for raw_argument in raw_args:
            if not isinstance(raw_argument, dict):
                raise ValueError("expression argument must be an object")
            arguments.append(cls.from_data(cast("dict[str, object]", raw_argument)))
        raw_parameters = data.get("parameters", [])
        if not isinstance(raw_parameters, list) or any(
            not isinstance(value, int) or isinstance(value, bool) for value in raw_parameters
        ):
            raise ValueError("expression parameters must be integers")
        value = data.get("value")
        if value is not None and not isinstance(value, (bool, int, str)):
            raise ValueError("expression literal value has unsupported type")
        name = data.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError("expression name must be a string")
        return cls(
            ExprOp(_string(data, "op")),
            Sort.from_data(raw_sort),
            tuple(arguments),
            value,
            name,
            tuple(cast("list[int]", raw_parameters)),
        )

    def evaluate(self, environment: Mapping[str, Scalar]) -> Scalar:
        """Evaluate exactly with explicit modular and signed bit-vector rules."""
        if self.op is ExprOp.LITERAL:
            return cast("Scalar", self.value)
        if self.op is ExprOp.VARIABLE:
            if self.name not in environment:
                raise KeyError(f"missing IR variable {self.name}")
            value = environment[cast("str", self.name)]
            _validate_scalar(self.sort, value)
            return value
        values = tuple(argument.evaluate(environment) for argument in self.args)
        if self.op is ExprOp.NOT:
            return not cast("bool", values[0])
        if self.op is ExprOp.AND:
            return all(cast("tuple[bool, ...]", values))
        if self.op is ExprOp.OR:
            return any(cast("tuple[bool, ...]", values))
        if self.op is ExprOp.EQ:
            return values[0] == values[1]
        if self.op is ExprOp.DISTINCT:
            return len(set(values)) == len(values)
        if self.op is ExprOp.ITE:
            return values[1] if cast("bool", values[0]) else values[2]
        if self.op in {ExprOp.INT_ADD, ExprOp.BV_ADD}:
            result = cast("int", values[0]) + cast("int", values[1])
            return self._wrap(result)
        if self.op in {ExprOp.INT_SUB, ExprOp.BV_SUB}:
            result = cast("int", values[0]) - cast("int", values[1])
            return self._wrap(result)
        if self.op in {ExprOp.BV_XOR, ExprOp.BV_AND, ExprOp.BV_OR}:
            left, right = cast("tuple[int, int]", values)
            if self.op is ExprOp.BV_XOR:
                result = left ^ right
            elif self.op is ExprOp.BV_AND:
                result = left & right
            else:
                result = left | right
            return self._wrap(result)
        if self.op is ExprOp.BV_EXTRACT:
            high, low = self.parameters
            mask = (1 << (high - low + 1)) - 1
            return (cast("int", values[0]) >> low) & mask
        if self.op in {ExprOp.INT_LT, ExprOp.INT_LE, ExprOp.INT_GT, ExprOp.INT_GE}:
            return _compare(self.op, cast("int", values[0]), cast("int", values[1]))
        if self.op in {
            ExprOp.BV_ULT,
            ExprOp.BV_ULE,
            ExprOp.BV_UGT,
            ExprOp.BV_UGE,
        }:
            return _compare_unsigned(self.op, cast("int", values[0]), cast("int", values[1]))
        if self.op in {
            ExprOp.BV_SLT,
            ExprOp.BV_SLE,
            ExprOp.BV_SGT,
            ExprOp.BV_SGE,
        }:
            width = _width(self.args[0].sort)
            return _compare_signed(
                self.op,
                _signed(cast("int", values[0]), width),
                _signed(cast("int", values[1]), width),
            )
        raise ValueError(f"unsupported concrete IR operation {self.op}")

    def _wrap(self, value: int) -> int:
        if self.sort.kind is SortKind.BITVECTOR:
            return value & ((1 << _width(self.sort)) - 1)
        return value

    def _validate(self) -> None:
        if self.op is ExprOp.LITERAL:
            if self.args or self.name is not None or self.parameters or self.value is None:
                raise ValueError("literal expression has invalid extra fields")
            _validate_scalar(self.sort, self.value)
            return
        if self.op is ExprOp.VARIABLE:
            if (
                not self.name
                or self.args
                or self.value is not None
                or self.parameters
                or not _is_identifier(self.name)
            ):
                raise ValueError("variable expression has invalid fields or name")
            return
        if self.value is not None or self.name is not None:
            raise ValueError("non-leaf expression cannot carry literal/name fields")
        if self.op is ExprOp.NOT:
            _require_args(self, 1, Sort.bool())
        elif self.op in {ExprOp.AND, ExprOp.OR}:
            if (
                not self.args
                or self.sort != Sort.bool()
                or any(argument.sort != Sort.bool() for argument in self.args)
            ):
                raise ValueError("Boolean n-ary expression has incompatible operands")
        elif self.op in {ExprOp.EQ, ExprOp.DISTINCT}:
            if (
                len(self.args) < 2
                or self.sort != Sort.bool()
                or len({argument.sort for argument in self.args}) != 1
            ):
                raise ValueError("equality/distinct operands must share one sort")
        elif self.op is ExprOp.ITE:
            if (
                len(self.args) != 3
                or self.args[0].sort != Sort.bool()
                or self.args[1].sort != self.args[2].sort
                or self.sort != self.args[1].sort
            ):
                raise ValueError("ITE condition/branch sorts are incompatible")
        elif self.op in {
            ExprOp.INT_ADD,
            ExprOp.INT_SUB,
        }:
            _require_args(self, 2, Sort.int(), result_sort=Sort.int())
        elif self.op in {ExprOp.INT_LT, ExprOp.INT_LE, ExprOp.INT_GT, ExprOp.INT_GE}:
            _require_args(self, 2, Sort.int(), result_sort=Sort.bool())
        elif self.op in {
            ExprOp.BV_XOR,
            ExprOp.BV_AND,
            ExprOp.BV_OR,
            ExprOp.BV_ADD,
            ExprOp.BV_SUB,
        }:
            _require_same_bitvectors(self, result_matches=True)
        elif self.op is ExprOp.BV_EXTRACT:
            if len(self.args) != 1 or self.args[0].sort.kind is not SortKind.BITVECTOR:
                raise ValueError("BV_EXTRACT requires one bit-vector argument")
            if len(self.parameters) != 2:
                raise ValueError("BV_EXTRACT requires high/low parameters")
            high, low = self.parameters
            if low < 0 or high < low or high >= _width(self.args[0].sort):
                raise ValueError("BV_EXTRACT range is outside its operand")
            if self.sort != Sort.bitvector(high - low + 1):
                raise ValueError("BV_EXTRACT result width is inconsistent")
        elif self.op in {
            ExprOp.BV_ULT,
            ExprOp.BV_ULE,
            ExprOp.BV_UGT,
            ExprOp.BV_UGE,
            ExprOp.BV_SLT,
            ExprOp.BV_SLE,
            ExprOp.BV_SGT,
            ExprOp.BV_SGE,
        }:
            _require_same_bitvectors(self, result_matches=False)
        else:
            raise ValueError(f"unknown expression operation {self.op}")
        if self.op is not ExprOp.BV_EXTRACT and self.parameters:
            raise ValueError("operation does not accept integer parameters")


@dataclass(frozen=True, slots=True)
class NamedAssumption:
    """A Boolean expression with a stable unsat-core/provenance name."""

    name: str
    expression: Expr
    group: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.group or self.expression.sort != Sort.bool():
            raise ValueError("named assumption requires names and a Boolean expression")
        if not self.provenance:
            raise ValueError("named assumption requires provenance")

    def to_data(self) -> dict[str, object]:
        """Return stable assumption data."""
        return {
            "name": self.name,
            "expression": self.expression.to_data(),
            "group": self.group,
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> NamedAssumption:
        """Decode and validate one named assumption."""
        _reject_extra(data, {"name", "expression", "group", "provenance"}, "assumption")
        raw_expression = _mapping(data, "expression")
        raw_provenance = _list(data, "provenance")
        if any(not isinstance(value, str) for value in raw_provenance):
            raise ValueError("assumption provenance must contain strings")
        return cls(
            _string(data, "name"),
            Expr.from_data(raw_expression),
            _string(data, "group"),
            tuple(cast("list[str]", raw_provenance)),
        )


@dataclass(frozen=True, slots=True)
class ConstraintProgram:
    """Versioned declarations, named assumptions, and one Boolean assertion."""

    ir_version: str
    declarations: tuple[Expr, ...]
    assumptions: tuple[NamedAssumption, ...]
    assertion: Expr

    def __post_init__(self) -> None:
        if self.ir_version != "1.0":
            raise ValueError("unsupported constraint IR version")
        if any(declaration.op is not ExprOp.VARIABLE for declaration in self.declarations):
            raise ValueError("constraint declarations must be variable expressions")
        names = tuple(cast("str", declaration.name) for declaration in self.declarations)
        if len(set(names)) != len(names):
            raise ValueError("constraint declarations contain duplicate names")
        assumption_names = tuple(assumption.name for assumption in self.assumptions)
        if len(set(assumption_names)) != len(assumption_names):
            raise ValueError("constraint assumptions contain duplicate names")
        if self.assertion.sort != Sort.bool():
            raise ValueError("constraint assertion must be Boolean")
        declared = {
            cast("str", declaration.name): declaration.sort for declaration in self.declarations
        }
        expressions = (
            *(assumption.expression for assumption in self.assumptions),
            self.assertion,
        )
        for expression in expressions:
            for variable in _variables(expression):
                variable_name = cast("str", variable.name)
                if variable_name not in declared:
                    raise ValueError(f"constraint references undeclared variable {variable_name}")
                if variable.sort != declared[variable_name]:
                    raise ValueError(f"constraint variable {variable_name} has inconsistent sort")

    def to_data(self) -> dict[str, object]:
        """Return stable program data without solver-specific objects."""
        return {
            "ir_version": self.ir_version,
            "declarations": [declaration.to_data() for declaration in self.declarations],
            "assumptions": [assumption.to_data() for assumption in self.assumptions],
            "assertion": self.assertion.to_data(),
        }

    def canonical_json(self) -> str:
        """Serialize deterministically for append-only persistence."""
        return json.dumps(self.to_data(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> ConstraintProgram:
        """Decode one complete IR program."""
        _reject_extra(
            data,
            {"ir_version", "declarations", "assumptions", "assertion"},
            "constraint program",
        )
        declarations = tuple(Expr.from_data(item) for item in _object_list(data, "declarations"))
        assumptions = tuple(
            NamedAssumption.from_data(item) for item in _object_list(data, "assumptions")
        )
        return cls(
            _string(data, "ir_version"),
            declarations,
            assumptions,
            Expr.from_data(_mapping(data, "assertion")),
        )


def _validate_scalar(sort: Sort, value: Scalar) -> None:
    if sort.kind is SortKind.BOOL:
        if not isinstance(value, bool):
            raise ValueError("Boolean expression requires a Boolean value")
    elif sort.kind is SortKind.INT:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("integer expression requires an integer value")
    elif sort.kind is SortKind.BITVECTOR:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value >= 1 << _width(sort)
        ):
            raise ValueError("bit-vector literal/value is outside its explicit width")
    elif not isinstance(value, str) or value not in sort.values:
        raise ValueError("finite expression value is outside its declared domain")


def _require_args(
    expression: Expr,
    count: int,
    argument_sort: Sort,
    *,
    result_sort: Sort | None = None,
) -> None:
    expected_result = argument_sort if result_sort is None else result_sort
    if (
        len(expression.args) != count
        or expression.sort != expected_result
        or any(argument.sort != argument_sort for argument in expression.args)
    ):
        raise ValueError(f"{expression.op.value} has incompatible operands/result")


def _require_same_bitvectors(expression: Expr, *, result_matches: bool) -> None:
    if (
        len(expression.args) != 2
        or expression.args[0].sort.kind is not SortKind.BITVECTOR
        or expression.args[0].sort != expression.args[1].sort
        or expression.sort != (expression.args[0].sort if result_matches else Sort.bool())
    ):
        raise ValueError(f"{expression.op.value} requires equal-width bit-vector operands")


def _width(sort: Sort) -> int:
    if sort.kind is not SortKind.BITVECTOR or sort.width is None:
        raise ValueError("operation requires an explicit bit-vector width")
    return sort.width


def _signed(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def _compare(op: ExprOp, left: int, right: int) -> bool:
    return {
        ExprOp.INT_LT: left < right,
        ExprOp.INT_LE: left <= right,
        ExprOp.INT_GT: left > right,
        ExprOp.INT_GE: left >= right,
    }[op]


def _compare_unsigned(op: ExprOp, left: int, right: int) -> bool:
    return {
        ExprOp.BV_ULT: left < right,
        ExprOp.BV_ULE: left <= right,
        ExprOp.BV_UGT: left > right,
        ExprOp.BV_UGE: left >= right,
    }[op]


def _compare_signed(op: ExprOp, left: int, right: int) -> bool:
    return {
        ExprOp.BV_SLT: left < right,
        ExprOp.BV_SLE: left <= right,
        ExprOp.BV_SGT: left > right,
        ExprOp.BV_SGE: left >= right,
    }[op]


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _list(data: Mapping[str, object], key: str) -> list[object]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return cast("list[object]", value)


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return cast("dict[str, object]", value)


def _object_list(data: Mapping[str, object], key: str) -> list[dict[str, object]]:
    values = _list(data, key)
    if any(not isinstance(value, dict) for value in values):
        raise ValueError(f"{key} must contain objects")
    return cast("list[dict[str, object]]", values)


def _reject_extra(data: Mapping[str, object], allowed: set[str], context: str) -> None:
    extras = sorted(set(data) - allowed)
    if extras:
        raise ValueError(f"{context} contains unknown fields: {', '.join(extras)}")


def _is_identifier(value: str) -> bool:
    return value.isascii() and value.isidentifier()


def _variables(expression: Expr) -> tuple[Expr, ...]:
    variables: list[Expr] = []
    pending = [expression]
    while pending:
        current = pending.pop()
        if current.op is ExprOp.VARIABLE:
            variables.append(current)
        pending.extend(current.args)
    return tuple(variables)
