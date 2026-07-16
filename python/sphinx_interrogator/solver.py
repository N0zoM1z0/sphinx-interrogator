"""Sound finite-domain constraint layer for the identity-mapping profiles."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from math import prod
from typing import cast

import z3  # type: ignore[import-untyped]

from sphinx_interrogator.constraint_ir import (
    ConstraintProgram,
    Expr,
    ExprOp,
    NamedAssumption,
    Scalar,
    Sort,
    SortKind,
)
from sphinx_interrogator.constraints import FiniteModelConstraint
from sphinx_interrogator.model import CandidateSummary
from sphinx_interrogator.relations import BankFact
from sphinx_interrogator.target_model import SBOX4


class InconsistentModelError(RuntimeError):
    """Raised when hard evidence eliminates every value for a secret cell."""


@dataclass(frozen=True, slots=True)
class BankEqualityConstraint:
    """Constraint on a two-bit projection of `SBOX4[secret XOR token]`."""

    lane: int
    token: int
    epoch: int
    bank: int
    equal: bool
    source_relation_instance_id: str
    confidence: float = 1.0

    @classmethod
    def from_fact(cls, fact: BankFact) -> BankEqualityConstraint:
        """Convert a relation extractor fact into the solver IR."""
        return cls(
            lane=fact.lane,
            token=fact.token,
            epoch=fact.epoch,
            bank=fact.bank,
            equal=fact.equal,
            source_relation_instance_id=fact.source_relation_instance_id,
            confidence=fact.confidence,
        )

    def accepts(self, secret_nibble: int) -> bool:
        """Evaluate this identity-profile constraint on one candidate nibble."""
        mapped = bank_of(secret_nibble, self.token, self.epoch)
        return (mapped == self.bank) is self.equal


@dataclass(frozen=True, slots=True)
class AppliedConstraint:
    """Audit record describing one domain update."""

    constraint: BankEqualityConstraint
    domain_before: frozenset[int]
    domain_after: frozenset[int]


class SecretDomain:
    """Factorized exact domains for tutorial and standard identity profiles.

    This is not a replacement for the required Z3/MaxSMT milestone. It is an
    executable reference model for the constraint semantics and supports exact
    uniqueness checks when lane mapping and salts are public identities.
    """

    def __init__(self, cells: int) -> None:
        """Initialize every four-bit cell to all sixteen possible values."""
        if cells < 1:
            raise ValueError("cells must be positive")
        self._domains: list[frozenset[int]] = [frozenset(range(16)) for _ in range(cells)]
        self._history: list[AppliedConstraint] = []

    @property
    def cells(self) -> int:
        """Return the number of ordered secret cells."""
        return len(self._domains)

    @property
    def history(self) -> tuple[AppliedConstraint, ...]:
        """Return the immutable constraint-application trace."""
        return tuple(self._history)

    def domain(self, lane: int) -> frozenset[int]:
        """Return the current exact nibble domain for one identity-mapped lane."""
        return self._domains[lane]

    def apply(self, constraint: BankEqualityConstraint) -> AppliedConstraint:
        """Intersect one lane domain with a hard bank constraint."""
        if not 0 <= constraint.lane < self.cells:
            raise ValueError(f"lane {constraint.lane} is outside the secret domain")
        before = self._domains[constraint.lane]
        after = frozenset(value for value in before if constraint.accepts(value))
        if not after:
            raise InconsistentModelError(
                "constraint from "
                f"{constraint.source_relation_instance_id} empties lane {constraint.lane}"
            )
        self._domains[constraint.lane] = after
        record = AppliedConstraint(constraint=constraint, domain_before=before, domain_after=after)
        self._history.append(record)
        return record

    def apply_all(
        self, constraints: Iterable[BankEqualityConstraint]
    ) -> tuple[AppliedConstraint, ...]:
        """Apply constraints in order and return their audit records."""
        return tuple(self.apply(constraint) for constraint in constraints)

    def candidate_count(self) -> int:
        """Return the exact Cartesian-product candidate count."""
        return prod(len(domain) for domain in self._domains)

    def unique_secret(self) -> tuple[int, ...] | None:
        """Return the ordered secret exactly when every lane has one candidate."""
        if any(len(domain) != 1 for domain in self._domains):
            return None
        return tuple(next(iter(domain)) for domain in self._domains)

    def alternative_model_exists(self, proposed: tuple[int, ...]) -> bool:
        """Perform the factorized equivalent of an SMT alternative-model query."""
        if len(proposed) != self.cells:
            raise ValueError("proposed secret has the wrong number of cells")
        for lane, domain in enumerate(self._domains):
            if proposed[lane] not in domain:
                raise ValueError("proposed secret does not satisfy the current hard constraints")
        return self.candidate_count() > 1

    def summary(self) -> CandidateSummary:
        """Build a public campaign summary without enumerating the Cartesian product."""
        unique = self.unique_secret()
        return CandidateSummary(
            exact_count=self.candidate_count(),
            lane_domains=tuple(self._domains),
            unique_secret_hex=None
            if unique is None
            else "".join(format(value, "x") for value in unique),
        )


def bank_of(secret_nibble: int, token: int, epoch: int) -> int:
    """Evaluate the public version-1 bank mapping for identity profiles."""
    if not 0 <= secret_nibble <= 15:
        raise ValueError("secret_nibble must fit in four bits")
    if not 0 <= token <= 15:
        raise ValueError("token must fit in four bits")
    if epoch not in (0, 1):
        raise ValueError("epoch must be zero or one")
    value = SBOX4[secret_nibble ^ token]
    return (value >> (2 * epoch)) & 0b11


class SolverStatus(StrEnum):
    """Total public result alphabet for bounded solver operations."""

    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


class ImplicationStatus(StrEnum):
    """Three-valued implication result; unknown is never proof."""

    IMPLIED = "implied"
    NOT_IMPLIED = "not_implied"
    UNKNOWN = "unknown"


class GroupState(StrEnum):
    """Lifecycle of one append-only constraint group."""

    ACTIVE = "active"
    QUARANTINED = "quarantined"
    RETRACTED = "retracted"


@dataclass(frozen=True, slots=True)
class ModelAssignment:
    """Stable scalar model independent of Z3 object identity."""

    values: tuple[tuple[str, Scalar], ...]

    def __post_init__(self) -> None:
        names = tuple(name for name, _ in self.values)
        if names != tuple(sorted(names)):
            raise ValueError("model values must be sorted by variable name")
        if len(set(names)) != len(self.values):
            raise ValueError("model contains duplicate variable names")

    def get(self, name: str) -> Scalar:
        """Return one concrete variable value."""
        for variable, value in self.values:
            if variable == name:
                return value
        raise KeyError(name)

    def to_data(self) -> dict[str, Scalar]:
        """Return stable JSON-compatible model data."""
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class CoreEntry:
    """One named unsat-core item with constraint and raw-evidence provenance."""

    tracking_name: str
    group_id: str
    assumption_name: str
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SolveResult:
    """One bounded solver check and any model/core diagnostics."""

    status: SolverStatus
    model: ModelAssignment | None
    unsat_core: tuple[CoreEntry, ...]
    reason_unknown: str | None


@dataclass(frozen=True, slots=True)
class EnumerationResult:
    """Finite or explicitly truncated/unknown model enumeration."""

    models: tuple[ModelAssignment, ...]
    complete: bool
    status: SolverStatus
    reason: str | None


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """Exact or sampled candidate/marginal summary with no hidden approximation."""

    solver_status: SolverStatus
    approximation: str
    exact_count: int | None
    sampled_count: int
    unique_model: ModelAssignment | None
    marginals: tuple[tuple[str, tuple[tuple[Scalar, int], ...]], ...]
    reason: str | None

    def __post_init__(self) -> None:
        if self.approximation not in {"exact", "sampled", "unknown"}:
            raise ValueError("unknown candidate snapshot approximation")

    def to_data(self) -> dict[str, object]:
        """Return persistence-safe snapshot data."""
        return {
            "solver_status": self.solver_status.value,
            "approximation": self.approximation,
            "exact_count": self.exact_count,
            "sampled_count": self.sampled_count,
            "unique_model": None if self.unique_model is None else self.unique_model.to_data(),
            "marginals": {
                name: [{"value": value, "count": count} for value, count in values]
                for name, values in self.marginals
            },
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class UniquenessResult:
    """Alternative-model proof result for a selected variable projection."""

    status: SolverStatus
    candidate: ModelAssignment | None
    unique: bool | None
    alternative: ModelAssignment | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class SoftSolveResult:
    """Weighted grouped soft-evidence ranking result."""

    status: SolverStatus
    model: ModelAssignment | None
    satisfied_groups: tuple[str, ...]
    total_satisfied_weight: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class ConstraintGroup:
    """Versioned IR program plus hard/soft policy and append-only provenance."""

    group_id: str
    program: ConstraintProgram
    hard: bool = True
    weight: int = 1
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.group_id:
            raise ValueError("constraint group ID must not be empty")
        if self.weight < 1:
            raise ValueError("constraint group weight must be positive")
        if not self.hard and not self.provenance:
            raise ValueError("soft constraint groups require provenance")


@dataclass(frozen=True, slots=True)
class _TranslatedProgram:
    declarations: tuple[tuple[str, Sort, z3.ExprRef], ...]
    domain_constraints: tuple[z3.BoolRef, ...]
    assumptions: tuple[tuple[NamedAssumption, z3.BoolRef], ...]
    assertion: z3.BoolRef


class Z3Translator:
    """Translate the project-owned typed IR without changing widths or signedness."""

    def __init__(self) -> None:
        self._variables: dict[str, tuple[Sort, z3.ExprRef]] = {}
        self._finite_sorts: dict[str, tuple[str, ...]] = {}

    @property
    def declarations(self) -> tuple[tuple[str, Sort, z3.ExprRef], ...]:
        """Return all translated variables in deterministic order."""
        return tuple(
            (name, sort, expression) for name, (sort, expression) in sorted(self._variables.items())
        )

    def program(self, program: ConstraintProgram) -> _TranslatedProgram:
        """Translate declarations, assumptions, and assertion into Z3 expressions."""
        domains: list[z3.BoolRef] = []
        for declaration in program.declarations:
            variable = self.expression(declaration)
            if declaration.sort.kind is SortKind.FINITE:
                domains.append(variable >= 0)
                domains.append(variable < len(declaration.sort.values))
        assumptions = tuple(
            (assumption, cast("z3.BoolRef", self.expression(assumption.expression)))
            for assumption in program.assumptions
        )
        return _TranslatedProgram(
            self.declarations,
            tuple(domains),
            assumptions,
            cast("z3.BoolRef", self.expression(program.assertion)),
        )

    def expression(self, expression: Expr) -> z3.ExprRef:
        """Translate one recursively typed expression."""
        if expression.op is ExprOp.LITERAL:
            return self._literal(expression.sort, cast("Scalar", expression.value))
        if expression.op is ExprOp.VARIABLE:
            return self._variable(cast("str", expression.name), expression.sort)
        arguments = tuple(self.expression(argument) for argument in expression.args)
        if expression.op is ExprOp.NOT:
            return z3.Not(arguments[0])
        if expression.op is ExprOp.AND:
            return z3.And(*arguments)
        if expression.op is ExprOp.OR:
            return z3.Or(*arguments)
        if expression.op is ExprOp.EQ:
            return arguments[0] == arguments[1]
        if expression.op is ExprOp.DISTINCT:
            return z3.Distinct(*arguments)
        if expression.op is ExprOp.ITE:
            return z3.If(arguments[0], arguments[1], arguments[2])
        if expression.op in {ExprOp.INT_ADD, ExprOp.BV_ADD}:
            return arguments[0] + arguments[1]
        if expression.op in {ExprOp.INT_SUB, ExprOp.BV_SUB}:
            return arguments[0] - arguments[1]
        if expression.op is ExprOp.BV_XOR:
            return arguments[0] ^ arguments[1]
        if expression.op is ExprOp.BV_AND:
            return arguments[0] & arguments[1]
        if expression.op is ExprOp.BV_OR:
            return arguments[0] | arguments[1]
        if expression.op is ExprOp.BV_EXTRACT:
            high, low = expression.parameters
            return z3.Extract(high, low, arguments[0])
        if expression.op is ExprOp.INT_LT:
            return arguments[0] < arguments[1]
        if expression.op is ExprOp.INT_LE:
            return arguments[0] <= arguments[1]
        if expression.op is ExprOp.INT_GT:
            return arguments[0] > arguments[1]
        if expression.op is ExprOp.INT_GE:
            return arguments[0] >= arguments[1]
        if expression.op is ExprOp.BV_ULT:
            return z3.ULT(arguments[0], arguments[1])
        if expression.op is ExprOp.BV_ULE:
            return z3.ULE(arguments[0], arguments[1])
        if expression.op is ExprOp.BV_UGT:
            return z3.UGT(arguments[0], arguments[1])
        if expression.op is ExprOp.BV_UGE:
            return z3.UGE(arguments[0], arguments[1])
        if expression.op is ExprOp.BV_SLT:
            return arguments[0] < arguments[1]
        if expression.op is ExprOp.BV_SLE:
            return arguments[0] <= arguments[1]
        if expression.op is ExprOp.BV_SGT:
            return arguments[0] > arguments[1]
        if expression.op is ExprOp.BV_SGE:
            return arguments[0] >= arguments[1]
        raise ValueError(f"unsupported Z3 IR operation {expression.op}")

    def model_assignment(self, model: z3.ModelRef) -> ModelAssignment:
        """Convert a total Z3 model into scalar values declared by the project IR."""
        values = []
        for name, sort, variable in self.declarations:
            value = model.eval(variable, model_completion=True)
            values.append((name, self._scalar_from_z3(sort, value)))
        return ModelAssignment(tuple(values))

    def literal_for(self, sort: Sort, value: Scalar) -> z3.ExprRef:
        """Translate a concrete scalar for blocking/uniqueness constraints."""
        return self._literal(sort, value)

    def _variable(self, name: str, sort: Sort) -> z3.ExprRef:
        existing = self._variables.get(name)
        if existing is not None:
            if existing[0] != sort:
                raise ValueError(f"Z3 variable {name} was declared with inconsistent sorts")
            return existing[1]
        if sort.kind is SortKind.BOOL:
            variable: z3.ExprRef = z3.Bool(name)
        elif sort.kind in {SortKind.INT, SortKind.FINITE}:
            variable = z3.Int(name)
        else:
            assert sort.width is not None
            variable = z3.BitVec(name, sort.width)
        if sort.kind is SortKind.FINITE:
            assert sort.name is not None
            existing_domain = self._finite_sorts.get(sort.name)
            if existing_domain is not None and existing_domain != sort.values:
                raise ValueError(f"finite sort {sort.name} has inconsistent domains")
            self._finite_sorts[sort.name] = sort.values
        self._variables[name] = (sort, variable)
        return variable

    def _literal(self, sort: Sort, value: Scalar) -> z3.ExprRef:
        if sort.kind is SortKind.BOOL:
            return z3.BoolVal(cast("bool", value))
        if sort.kind is SortKind.INT:
            return z3.IntVal(cast("int", value))
        if sort.kind is SortKind.BITVECTOR:
            assert sort.width is not None
            return z3.BitVecVal(cast("int", value), sort.width)
        return z3.IntVal(sort.values.index(cast("str", value)))

    @staticmethod
    def _scalar_from_z3(sort: Sort, value: z3.ExprRef) -> Scalar:
        if sort.kind is SortKind.BOOL:
            return bool(z3.is_true(value))
        integer = int(cast("z3.IntNumRef | z3.BitVecNumRef", value).as_long())
        if sort.kind is SortKind.FINITE:
            return sort.values[integer]
        return integer


class HypothesisStore:
    """Exact named-constraint solver with quarantine, replay, and bounded queries."""

    def __init__(self, *, timeout_ms: int = 5_000, max_soft_group_weight: int = 100) -> None:
        if timeout_ms < 1:
            raise ValueError("solver timeout must be positive")
        if max_soft_group_weight < 1:
            raise ValueError("maximum soft group weight must be positive")
        self.timeout_ms = timeout_ms
        self.max_soft_group_weight = max_soft_group_weight
        self._groups: dict[str, ConstraintGroup] = {}
        self._states: dict[str, GroupState] = {}

    @property
    def groups(self) -> tuple[ConstraintGroup, ...]:
        """Return groups in stable ID order."""
        return tuple(self._groups[group_id] for group_id in sorted(self._groups))

    def add(self, group: ConstraintGroup) -> None:
        """Append a constraint group once without silently replacing evidence."""
        existing = self._groups.get(group.group_id)
        if existing is not None:
            if existing != group:
                raise ValueError(f"constraint group {group.group_id} conflicts with existing data")
            return
        if not group.hard and group.weight > self.max_soft_group_weight:
            raise ValueError(f"soft group weight exceeds cap {self.max_soft_group_weight}")
        self._groups[group.group_id] = group
        self._states[group.group_id] = GroupState.ACTIVE

    def state(self, group_id: str) -> GroupState:
        """Return one group's current lifecycle state."""
        return self._states[group_id]

    def quarantine(self, group_id: str) -> None:
        """Disable a suspect group without deleting its provenance."""
        if group_id not in self._groups:
            raise KeyError(group_id)
        self._states[group_id] = GroupState.QUARANTINED

    def retract(self, group_id: str) -> None:
        """Permanently deactivate a group invalidated by later evidence."""
        if group_id not in self._groups:
            raise KeyError(group_id)
        self._states[group_id] = GroupState.RETRACTED

    def reactivate(self, group_id: str) -> None:
        """Re-enable a quarantined but not retracted group after review."""
        if self._states[group_id] is GroupState.RETRACTED:
            raise ValueError("retracted constraint groups cannot be reactivated")
        self._states[group_id] = GroupState.ACTIVE

    def solve(self) -> SolveResult:
        """Check all active hard evidence and return a model or named unsat core."""
        solver, translator, tracked = self._hard_solver()
        status = _solver_status(solver.check())
        if status is SolverStatus.SAT:
            return SolveResult(status, translator.model_assignment(solver.model()), (), None)
        if status is SolverStatus.UNSAT:
            core = tuple(tracked[str(item)] for item in solver.unsat_core() if str(item) in tracked)
            return SolveResult(status, None, core, None)
        return SolveResult(status, None, (), solver.reason_unknown())

    def enumerate_models(self, *, limit: int = 1_024) -> EnumerationResult:
        """Enumerate with exact blocking until unsat, timeout, or an explicit cap."""
        if limit < 1:
            raise ValueError("model enumeration limit must be positive")
        solver, translator, _ = self._hard_solver()
        models: list[ModelAssignment] = []
        declarations = translator.declarations
        while len(models) < limit:
            status = _solver_status(solver.check())
            if status is SolverStatus.UNSAT:
                hypothesis_status = SolverStatus.SAT if models else SolverStatus.UNSAT
                return EnumerationResult(tuple(models), True, hypothesis_status, None)
            if status is SolverStatus.UNKNOWN:
                return EnumerationResult(tuple(models), False, status, solver.reason_unknown())
            assignment = translator.model_assignment(solver.model())
            models.append(assignment)
            blocking = [
                variable != translator.literal_for(sort, assignment.get(name))
                for name, sort, variable in declarations
            ]
            if not blocking:
                return EnumerationResult(tuple(models), True, SolverStatus.SAT, None)
            solver.add(z3.Or(*blocking))
        return EnumerationResult(
            tuple(models),
            False,
            SolverStatus.SAT,
            f"model enumeration reached explicit limit {limit}",
        )

    def diverse_models(self, *, limit: int, pool_limit: int = 256) -> EnumerationResult:
        """Greedily choose deterministic maximum-Hamming models from a bounded pool."""
        if limit < 1 or pool_limit < limit:
            raise ValueError("diverse model limits are inconsistent")
        enumerated = self.enumerate_models(limit=pool_limit)
        pool = list(enumerated.models)
        if len(pool) <= limit:
            return enumerated
        selected = [min(pool, key=lambda model: model.values)]
        pool.remove(selected[0])
        while pool and len(selected) < limit:
            candidate = max(
                pool,
                key=lambda model: (
                    min(_hamming(model, chosen) for chosen in selected),
                    tuple(repr(item) for item in model.values),
                ),
            )
            selected.append(candidate)
            pool.remove(candidate)
        return EnumerationResult(
            tuple(selected),
            False,
            enumerated.status,
            "diverse subset selected from bounded enumeration pool",
        )

    def snapshot(self, *, limit: int = 65_536) -> CandidateSnapshot:
        """Compute exact marginals only when enumeration reaches unsat."""
        enumerated = self.enumerate_models(limit=limit)
        counts: dict[str, dict[Scalar, int]] = {}
        for model in enumerated.models:
            for name, value in model.values:
                counts.setdefault(name, {})[value] = counts.setdefault(name, {}).get(value, 0) + 1
        marginals = tuple(
            (
                name,
                tuple(sorted(values.items(), key=lambda item: repr(item[0]))),
            )
            for name, values in sorted(counts.items())
        )
        exact = enumerated.complete
        unique = enumerated.models[0] if exact and len(enumerated.models) == 1 else None
        approximation = (
            "exact"
            if exact
            else ("unknown" if enumerated.status is SolverStatus.UNKNOWN else "sampled")
        )
        return CandidateSnapshot(
            solver_status=enumerated.status,
            approximation=approximation,
            exact_count=len(enumerated.models) if exact else None,
            sampled_count=len(enumerated.models),
            unique_model=unique,
            marginals=marginals,
            reason=enumerated.reason,
        )

    def check_uniqueness(self, variable_names: tuple[str, ...]) -> UniquenessResult:
        """Prove uniqueness only by an explicit alternative-model exclusion query."""
        if not variable_names or len(set(variable_names)) != len(variable_names):
            raise ValueError("uniqueness projection must be nonempty and unique")
        solver, translator, _ = self._hard_solver()
        first_status = _solver_status(solver.check())
        if first_status is SolverStatus.UNSAT:
            return UniquenessResult(first_status, None, None, None, "hypothesis is unsatisfiable")
        if first_status is SolverStatus.UNKNOWN:
            return UniquenessResult(first_status, None, None, None, solver.reason_unknown())
        candidate = translator.model_assignment(solver.model())
        declarations = {name: (sort, variable) for name, sort, variable in translator.declarations}
        missing = sorted(set(variable_names) - set(declarations))
        if missing:
            raise ValueError(f"unknown uniqueness variables: {missing}")
        solver.add(
            z3.Or(
                *(
                    declarations[name][1]
                    != translator.literal_for(declarations[name][0], candidate.get(name))
                    for name in variable_names
                )
            )
        )
        alternative_status = _solver_status(solver.check())
        if alternative_status is SolverStatus.UNSAT:
            return UniquenessResult(
                alternative_status, candidate, True, None, "alternative-model query is unsat"
            )
        if alternative_status is SolverStatus.UNKNOWN:
            return UniquenessResult(
                alternative_status, candidate, None, None, solver.reason_unknown()
            )
        return UniquenessResult(
            alternative_status,
            candidate,
            False,
            translator.model_assignment(solver.model()),
            "a distinct projected model exists",
        )

    def implication(self, expression: Expr) -> ImplicationStatus:
        """Check `active hard evidence => expression` with honest unknown handling."""
        if expression.sort != Sort.bool():
            raise ValueError("implication target must be Boolean")
        solver, translator, _ = self._hard_solver()
        solver.add(z3.Not(translator.expression(expression)))
        status = _solver_status(solver.check())
        if status is SolverStatus.UNSAT:
            return ImplicationStatus.IMPLIED
        if status is SolverStatus.SAT:
            return ImplicationStatus.NOT_IMPLIED
        return ImplicationStatus.UNKNOWN

    def optimize_soft(self) -> SoftSolveResult:
        """Rank active grouped soft evidence while all hard constraints remain mandatory."""
        optimizer = z3.Optimize()
        optimizer.set(timeout=self.timeout_ms)
        translator = Z3Translator()
        translated = [
            (group, translator.program(group.program))
            for group in self.groups
            if self._states[group.group_id] is GroupState.ACTIVE
        ]
        for _group, program in translated:
            optimizer.add(*program.domain_constraints)
        soft_expressions: dict[str, z3.BoolRef] = {}
        for group, program in translated:
            complete = z3.And(
                *(expression for _assumption, expression in program.assumptions),
                program.assertion,
            )
            if group.hard:
                optimizer.add(complete)
            else:
                soft_expressions[group.group_id] = complete
                optimizer.add_soft(complete, weight=str(group.weight), id=group.group_id)
        status = _solver_status(optimizer.check())
        if status is SolverStatus.UNKNOWN:
            return SoftSolveResult(status, None, (), None, optimizer.reason_unknown())
        if status is SolverStatus.UNSAT:
            return SoftSolveResult(status, None, (), None, "active hard constraints are unsat")
        model = optimizer.model()
        satisfied = tuple(
            group_id
            for group_id, expression in sorted(soft_expressions.items())
            if bool(z3.is_true(model.eval(expression, model_completion=True)))
        )
        weight = sum(self._groups[group_id].weight for group_id in satisfied)
        return SoftSolveResult(
            status,
            translator.model_assignment(model),
            satisfied,
            weight,
            None,
        )

    def quarantine_unsat_core(self, core: tuple[CoreEntry, ...]) -> tuple[str, ...]:
        """Quarantine all active evidence groups named by a diagnostic unsat core."""
        groups = tuple(sorted({entry.group_id for entry in core if entry.group_id in self._groups}))
        for group_id in groups:
            self.quarantine(group_id)
        return groups

    def _hard_solver(
        self,
    ) -> tuple[z3.Solver, Z3Translator, dict[str, CoreEntry]]:
        solver = z3.Solver()
        solver.set(timeout=self.timeout_ms)
        translator = Z3Translator()
        translated = []
        for group in self.groups:
            if self._states[group.group_id] is GroupState.ACTIVE and group.hard:
                translated.append((group, translator.program(group.program)))
        for _group, program in translated:
            solver.add(*program.domain_constraints)
        tracked: dict[str, CoreEntry] = {}
        for group, program in translated:
            for assumption, expression in program.assumptions:
                tracking_name = _tracking_name(group.group_id, assumption.name)
                entry = CoreEntry(
                    tracking_name,
                    group.group_id,
                    assumption.name,
                    (*group.provenance, *assumption.provenance),
                )
                tracked[tracking_name] = entry
                solver.assert_and_track(expression, z3.Bool(tracking_name))
            assertion_name = _tracking_name(group.group_id, "assertion")
            tracked[assertion_name] = CoreEntry(
                assertion_name,
                group.group_id,
                "assertion",
                group.provenance,
            )
            solver.assert_and_track(program.assertion, z3.Bool(assertion_name))
        return solver, translator, tracked


def finite_model_program(
    constraint: FiniteModelConstraint,
    *,
    secret_cells: int,
) -> ConstraintProgram:
    """Compile finite relation evidence into the generic project expression IR."""
    if secret_cells < 1 or any(lane >= secret_cells for lane in constraint.lanes):
        raise ValueError("finite constraint lanes exceed the declared secret domain")
    nibble_sort = Sort.bitvector(4)
    fault_sort = Sort.finite("FaultVariant", ("off", "reference", "weak", "signed"))
    secret_variables = tuple(
        Expr.variable(f"secret_{lane}", nibble_sort) for lane in range(secret_cells)
    )
    fault_variable = Expr.variable("fault_variant", fault_sort)
    allowed = []
    for model in constraint.allowed_models:
        terms = [
            Expr.equal(secret_variables[lane], Expr.literal(nibble_sort, value))
            for lane, value in zip(constraint.lanes, model.secret_values, strict=True)
        ]
        terms.append(Expr.equal(fault_variable, Expr.literal(fault_sort, model.fault_variant)))
        allowed.append(Expr.conjunction(tuple(terms)))
    allowed_expression = Expr.disjunction(tuple(allowed))
    assumption = NamedAssumption(
        constraint.constraint_id,
        allowed_expression,
        constraint.constraint_id,
        (
            *constraint.source_request_ids,
            f"relation:{constraint.relation_instance_id}",
            f"certificate:{constraint.certificate_id}",
        ),
    )
    return ConstraintProgram(
        "1.0",
        (*secret_variables, fault_variable),
        (assumption,),
        Expr.literal(Sort.bool(), True),
    )


def _solver_status(status: z3.CheckSatResult) -> SolverStatus:
    if status == z3.sat:
        return SolverStatus.SAT
    if status == z3.unsat:
        return SolverStatus.UNSAT
    return SolverStatus.UNKNOWN


def _tracking_name(group_id: str, assumption_name: str) -> str:
    digest = hashlib.sha256(f"{group_id}\0{assumption_name}".encode()).hexdigest()
    return f"track_{digest[:24]}"


def _hamming(left: ModelAssignment, right: ModelAssignment) -> int:
    if tuple(name for name, _ in left.values) != tuple(name for name, _ in right.values):
        raise ValueError("cannot compare models with different declarations")
    return sum(
        left_value != right_value
        for (_, left_value), (_, right_value) in zip(left.values, right.values, strict=True)
    )
