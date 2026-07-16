"""Tests for finite reference domains and the exact Z3 hypothesis store."""

from __future__ import annotations

import itertools

from sphinx_interrogator.constraint_ir import ConstraintProgram, Expr, ExprOp, NamedAssumption, Sort
from sphinx_interrogator.constraints import (
    ApproximationKind,
    FiniteModelAssignment,
    FiniteModelConstraint,
)
from sphinx_interrogator.solver import (
    BankEqualityConstraint,
    ConstraintGroup,
    GroupState,
    HypothesisStore,
    ImplicationStatus,
    SecretDomain,
    SolverStatus,
    Z3Translator,
    bank_of,
    finite_model_program,
)


def test_two_epochs_can_isolate_a_nibble() -> None:
    """Collecting exact projected banks for both epochs should identify a nibble."""
    target = 13
    domain = SecretDomain(1)
    for epoch in (0, 1):
        domain.apply(
            BankEqualityConstraint(
                lane=0,
                token=0,
                epoch=epoch,
                bank=bank_of(target, 0, epoch),
                equal=True,
                source_relation_instance_id=f"r{epoch}",
            )
        )
    assert domain.unique_secret() == (target,)
    assert not domain.alternative_model_exists((target,))


def test_constraint_history_retains_provenance() -> None:
    """Every domain intersection should retain its source relation identifier."""
    domain = SecretDomain(2)
    domain.apply(
        BankEqualityConstraint(
            lane=1,
            token=2,
            epoch=0,
            bank=1,
            equal=False,
            source_relation_instance_id="relation-7",
        )
    )
    assert domain.history[0].constraint.source_relation_instance_id == "relation-7"
    assert domain.candidate_count() < 16 * 16


def _program(expression: Expr) -> ConstraintProgram:
    declarations = tuple(_variables(expression))
    unique = {str(item.name): item for item in declarations}
    return ConstraintProgram(
        "1.0",
        tuple(unique[name] for name in sorted(unique)),
        (NamedAssumption("evidence", expression, "test", ("fixture",)),),
        Expr.literal(Sort.bool(), True),
    )


def _variables(expression: Expr) -> tuple[Expr, ...]:
    pending = [expression]
    found: list[Expr] = []
    while pending:
        current = pending.pop()
        if current.op is ExprOp.VARIABLE:
            found.append(current)
        pending.extend(current.args)
    return tuple(found)


def _equality_program(name: str, value: int) -> ConstraintProgram:
    variable = Expr.variable(name, Sort.bitvector(4))
    return ConstraintProgram(
        "1.0",
        (variable,),
        (
            NamedAssumption(
                f"{name}_equals_{value}",
                Expr.equal(variable, Expr.literal(variable.sort, value)),
                "test",
                (f"fixture:{name}:{value}",),
            ),
        ),
        Expr.literal(Sort.bool(), True),
    )


def test_z3_translation_preserves_explicit_bitvector_signedness() -> None:
    """Concrete IR and Z3 agree on all four-bit signed/unsigned comparisons."""
    left = Expr.variable("left", Sort.bitvector(4))
    right = Expr.variable("right", Sort.bitvector(4))
    unsigned = Expr(ExprOp.BV_ULT, Sort.bool(), (left, right))
    signed = Expr(ExprOp.BV_SLT, Sort.bool(), (left, right))
    for left_value, right_value in itertools.product(range(16), repeat=2):
        for expression in (unsigned, signed):
            concrete = expression.evaluate({"left": left_value, "right": right_value})
            fixed = Expr.conjunction(
                (
                    expression,
                    Expr.equal(left, Expr.literal(left.sort, left_value)),
                    Expr.equal(right, Expr.literal(right.sort, right_value)),
                )
            )
            program = ConstraintProgram(
                "1.0",
                (left, right),
                (),
                fixed,
            )
            store = HypothesisStore()
            store.add(ConstraintGroup("comparison", program))
            assert (store.solve().status is SolverStatus.SAT) is concrete


def test_finite_relation_constraint_enumerates_exact_correlated_models() -> None:
    """Finite evidence retains secret/fault correlation instead of projecting it away."""
    constraint = FiniteModelConstraint(
        constraint_version="1.0",
        constraint_id="constraint:111111111111111111111111",
        lanes=(0,),
        allowed_models=(
            FiniteModelAssignment((3,), "reference"),
            FiniteModelAssignment((5,), "off"),
        ),
        approximation=ApproximationKind.EXACT,
        relation_instance_id="relation-1",
        certificate_id="cert-1",
        decision_kind="exact_greater",
        source_request_ids=("request-source", "request-follow-up"),
        assumptions=("hard reset",),
    )
    program = finite_model_program(constraint, secret_cells=1)
    store = HypothesisStore()
    store.add(ConstraintGroup("finite-evidence", program, provenance=("campaign",)))
    enumeration = store.enumerate_models(limit=10)
    assert enumeration.complete
    assert enumeration.status is SolverStatus.SAT
    assert {tuple(model.values) for model in enumeration.models} == {
        (("fault_variant", "off"), ("secret_0", 5)),
        (("fault_variant", "reference"), ("secret_0", 3)),
    }
    snapshot = store.snapshot(limit=10)
    assert snapshot.approximation == "exact"
    assert snapshot.exact_count == 2
    assert snapshot.unique_model is None


def test_wrong_symbolic_model_evidence_is_unsat_not_false_exact() -> None:
    """A contradictory symbolic-model mutation is inconsistency, not a false singleton."""
    true_constraint = FiniteModelConstraint(
        constraint_version="1.0",
        constraint_id="constraint:true-symbolic-model",
        lanes=(0,),
        allowed_models=(FiniteModelAssignment((9,), "reference"),),
        approximation=ApproximationKind.EXACT,
        relation_instance_id="relation-true",
        certificate_id="cert-true",
        decision_kind="exact_greater",
        source_request_ids=("request-source", "request-follow-up"),
        assumptions=("reference symbolic model",),
    )
    wrong_constraint = FiniteModelConstraint(
        constraint_version="1.0",
        constraint_id="constraint:wrong-symbolic-model",
        lanes=(0,),
        allowed_models=(FiniteModelAssignment((10,), "reference"),),
        approximation=ApproximationKind.EXACT,
        relation_instance_id="relation-mutated",
        certificate_id="cert-mutated",
        decision_kind="exact_greater",
        source_request_ids=("request-source", "request-follow-up"),
        assumptions=("deliberately mutated symbolic bank model",),
    )
    store = HypothesisStore()
    store.add(
        ConstraintGroup(
            true_constraint.constraint_id,
            finite_model_program(true_constraint, secret_cells=1),
            provenance=("public-observation:true",),
        )
    )
    store.add(
        ConstraintGroup(
            wrong_constraint.constraint_id,
            finite_model_program(wrong_constraint, secret_cells=1),
            provenance=("mutation:wrong-symbolic-model",),
        )
    )

    inconsistent = store.solve()
    assert inconsistent.status is SolverStatus.UNSAT
    assert {entry.group_id for entry in inconsistent.unsat_core} == {
        true_constraint.constraint_id,
        wrong_constraint.constraint_id,
    }
    uniqueness = store.check_uniqueness(("secret_0",))
    assert uniqueness.status is SolverStatus.UNSAT
    assert uniqueness.unique is None
    assert uniqueness.candidate is None
    assert uniqueness.reason == "hypothesis is unsatisfiable"

    store.quarantine(wrong_constraint.constraint_id)
    repaired = store.check_uniqueness(("secret_0",))
    assert repaired.status is SolverStatus.UNSAT
    assert repaired.unique is True
    assert repaired.candidate is not None
    assert repaired.candidate.get("secret_0") == 9


def test_exact_uniqueness_requires_alternative_model_unsat() -> None:
    """A singleton claim is backed by a second query excluding the selected nibble."""
    store = HypothesisStore()
    store.add(ConstraintGroup("secret", _equality_program("secret_0", 7)))
    uniqueness = store.check_uniqueness(("secret_0",))
    assert uniqueness.status is SolverStatus.UNSAT
    assert uniqueness.unique is True
    assert uniqueness.candidate is not None
    assert uniqueness.candidate.get("secret_0") == 7
    assert uniqueness.reason == "alternative-model query is unsat"

    variable = Expr.variable("secret_0", Sort.bitvector(4))
    two_values = Expr.disjunction(
        (
            Expr.equal(variable, Expr.literal(variable.sort, 7)),
            Expr.equal(variable, Expr.literal(variable.sort, 8)),
        )
    )
    nonunique = HypothesisStore()
    nonunique.add(ConstraintGroup("two", _program(two_values)))
    alternative = nonunique.check_uniqueness(("secret_0",))
    assert alternative.status is SolverStatus.SAT
    assert alternative.unique is False
    assert alternative.alternative is not None


def test_named_unsat_core_quarantine_and_retraction_preserve_provenance() -> None:
    """Contradictory evidence is diagnosed and disabled without deleting history."""
    store = HypothesisStore()
    store.add(
        ConstraintGroup(
            "group-one",
            _equality_program("secret_0", 1),
            provenance=("request-1", "certificate-1"),
        )
    )
    store.add(
        ConstraintGroup(
            "group-two",
            _equality_program("secret_0", 2),
            provenance=("request-2", "certificate-2"),
        )
    )
    result = store.solve()
    assert result.status is SolverStatus.UNSAT
    assert {entry.group_id for entry in result.unsat_core} == {"group-one", "group-two"}
    assert all(entry.provenance for entry in result.unsat_core)
    assert store.quarantine_unsat_core(result.unsat_core) == ("group-one", "group-two")
    assert store.solve().status is SolverStatus.SAT
    store.reactivate("group-one")
    assert store.solve().model is not None
    store.retract("group-one")
    assert store.state("group-one") is GroupState.RETRACTED


def test_implication_is_three_valued_and_nonimplication_has_a_countermodel() -> None:
    """SAT negation means not implied; only UNSAT proves semantic redundancy."""
    store = HypothesisStore()
    store.add(ConstraintGroup("secret", _equality_program("secret_0", 4)))
    variable = Expr.variable("secret_0", Sort.bitvector(4))
    assert (
        store.implication(Expr.equal(variable, Expr.literal(variable.sort, 4)))
        is ImplicationStatus.IMPLIED
    )
    assert (
        store.implication(Expr.equal(variable, Expr.literal(variable.sort, 5)))
        is ImplicationStatus.NOT_IMPLIED
    )


def test_empty_store_and_bounded_diverse_models_label_approximations() -> None:
    """An empty hypothesis has one empty model; bounded committees remain sampled."""
    empty = HypothesisStore()
    snapshot = empty.snapshot(limit=2)
    assert snapshot.exact_count == 1
    assert snapshot.unique_model is not None
    assert snapshot.unique_model.values == ()

    variable = Expr.variable("secret_0", Sort.bitvector(4))
    unconstrained = ConstraintProgram(
        "1.0",
        (variable,),
        (),
        Expr.literal(Sort.bool(), True),
    )
    store = HypothesisStore()
    store.add(ConstraintGroup("domain", unconstrained))
    committee = store.diverse_models(limit=4, pool_limit=8)
    assert len(committee.models) == 4
    assert not committee.complete
    assert len({model.get("secret_0") for model in committee.models}) == 4


def test_translator_rejects_cross_program_sort_conflicts() -> None:
    """A shared variable name cannot silently change width across evidence groups."""
    translator = Z3Translator()
    translator.expression(Expr.variable("x", Sort.bitvector(4)))
    try:
        translator.expression(Expr.variable("x", Sort.bitvector(3)))
    except ValueError as error:
        assert "inconsistent sorts" in str(error)
    else:
        raise AssertionError("translator accepted a conflicting declaration")


def test_grouped_soft_weights_are_capped_and_ranked_without_weakening_hard_facts() -> None:
    """MaxSMT counts each correlation group once and enforces the configured cap."""
    store = HypothesisStore(max_soft_group_weight=10)
    store.add(
        ConstraintGroup(
            "prefer-one",
            _equality_program("secret_0", 1),
            hard=False,
            weight=7,
            provenance=("correlation-group-1",),
        )
    )
    store.add(
        ConstraintGroup(
            "prefer-two",
            _equality_program("secret_0", 2),
            hard=False,
            weight=3,
            provenance=("correlation-group-2",),
        )
    )
    ranked = store.optimize_soft()
    assert ranked.status is SolverStatus.SAT
    assert ranked.model is not None
    assert ranked.model.get("secret_0") == 1
    assert ranked.satisfied_groups == ("prefer-one",)
    assert ranked.total_satisfied_weight == 7

    try:
        store.add(
            ConstraintGroup(
                "uncapped",
                _equality_program("secret_0", 3),
                hard=False,
                weight=11,
                provenance=("bad",),
            )
        )
    except ValueError as error:
        assert "exceeds cap" in str(error)
    else:
        raise AssertionError("soft group weight cap was not enforced")
