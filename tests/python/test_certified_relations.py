"""Reduced exhaustive tests for the M3 relation/certificate/extractor contracts."""

from __future__ import annotations

import itertools
import json
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest

from sphinx_interrogator.ast import Program
from sphinx_interrogator.certificates import CertificateRegistry, ProofMethod, RelationCertificate
from sphinx_interrogator.constraints import ExtractionStatus
from sphinx_interrogator.extractors import extract_finite_models
from sphinx_interrogator.model import ExecutionObservation, ExecutionResult
from sphinx_interrogator.normalization import DecisionKind, decide_pair
from sphinx_interrogator.relations import (
    TEMPLATE_REGISTRY,
    AnchorSwitchTemplate,
    Cell,
    ContextLiftTemplate,
    EpochSwitchTemplate,
    HardReplayTemplate,
    IndependentSwapTemplate,
    PhaseShiftTemplate,
    RegisterRenameTemplate,
    RelationInstance,
    RepeatAmplifyTemplate,
    TokenSwitchTemplate,
)
from sphinx_interrogator.target_model import (
    FaultVariant,
    execute_experiment_program,
)

ROOT = Path(__file__).resolve().parents[2]
RELATION_SCHEMA = json.loads((ROOT / "spec/relation.schema.json").read_text(encoding="utf-8"))
CONSTRAINT_SCHEMA = json.loads((ROOT / "spec/constraint.schema.json").read_text(encoding="utf-8"))


def _sample_relations() -> tuple[RelationInstance, ...]:
    anchor = AnchorSwitchTemplate().instantiate(
        instance_id="anchor",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    token = TokenSwitchTemplate().instantiate(
        instance_id="token",
        lane=0,
        token_a=0,
        token_b=1,
        epoch=0,
        anchor=2,
        pad=0,
    )
    epoch = EpochSwitchTemplate().instantiate(
        instance_id="epoch",
        lane=0,
        token=0,
        epoch_a=0,
        epoch_b=1,
        anchor=2,
        pad_a=0,
        pad_b=1,
    )
    phase = PhaseShiftTemplate().instantiate(
        instance_id="phase",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad_a=0,
        pad_b=1,
    )
    repeat = RepeatAmplifyTemplate().instantiate(
        instance_id="repeat",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad=0,
        repeats=3,
    )
    swap = IndependentSwapTemplate().instantiate(
        instance_id="swap",
        first=Cell(0, 0, 0, 2),
        second=Cell(1, 1, 1, 3, 2),
    )
    context = ContextLiftTemplate().instantiate(
        instance_id="context",
        base=anchor,
        prefix_pad=3,
    )
    register_program = Program.parse(
        "MOVI r0, 7\nMOV r1, r0\nADD r2, r0, r1\nMIXOUT r2\nHALT\n",
        lanes=2,
    )
    register = RegisterRenameTemplate().instantiate(
        instance_id="register",
        source=register_program,
        permutation=(1, 2, 0, 3, 4, 5, 6, 7),
    )
    replay = HardReplayTemplate().instantiate(
        instance_id="replay",
        program=anchor.source_program,
        repetitions=3,
        deterministic_observation=True,
    )
    return anchor, token, epoch, phase, repeat, swap, context, register, replay


def _result(
    relation: RelationInstance,
    *,
    follow_up: bool,
    secret: tuple[int, ...],
    variant: FaultVariant,
    noise: int,
    width: int,
    request_id: str,
) -> ExecutionResult:
    program = relation.follow_up_programs[0] if follow_up else relation.source_program
    secret_by_lane = {lane: secret[lane] for lane in relation.involved_lanes}
    model = execute_experiment_program(program, secret_by_lane, variant=variant)
    cycles = max(0, model.static_cycles + model.fault_cycles + noise)
    return ExecutionResult(
        request_id=request_id,
        session_id="certified-relation-test",
        status="halted",
        public_digest="0000000000000000",
        observation=ExecutionObservation(cycles // width, width),
        retired_instructions=len(program.instructions),
        static_cycles=model.static_cycles,
        physical_executions_used=1,
        physical_executions_remaining=999,
        logical_queries_used=1,
        logical_queries_remaining=79,
        hard_resets_used=1,
        hard_resets_remaining=999,
        server_version="0.1.0",
        profile_version="0.1.0",
    )


def _decision(
    relation: RelationInstance,
    source: ExecutionResult,
    follow_up: ExecutionResult,
    *,
    noise_bound: int,
):
    return decide_pair(
        source,
        follow_up,
        expected_source_static=relation.source_program.static_cycles(),
        expected_follow_up_static=relation.follow_up_programs[0].static_cycles(),
        noise_bound=noise_bound,
        assumptions=("test profile",),
    )


def test_template_registry_and_every_precondition_path() -> None:
    """Every M3 template has a positive and a structured negative precondition."""
    assert set(TEMPLATE_REGISTRY) == {
        "anchor-switch/v1",
        "token-switch/v1",
        "epoch-switch/v1",
        "phase-shift/v1",
        "repeat-amplify/v1",
        "independent-swap/v1",
        "context-lift/v1",
        "register-rename/v1",
        "hard-replay/v1",
    }
    assert AnchorSwitchTemplate().applicable(bank_a=0, bank_b=1).accepted
    assert not AnchorSwitchTemplate().applicable(bank_a=1, bank_b=1).accepted
    assert TokenSwitchTemplate().applicable(token_a=0, token_b=1).accepted
    assert not TokenSwitchTemplate().applicable(token_a=1, token_b=1).accepted
    assert EpochSwitchTemplate().applicable(epoch_a=0, epoch_b=1).accepted
    assert not EpochSwitchTemplate().applicable(epoch_a=0, epoch_b=0).accepted
    assert PhaseShiftTemplate().applicable(pad_a=0, pad_b=1).accepted
    assert not PhaseShiftTemplate().applicable(pad_a=0, pad_b=4).accepted
    assert RepeatAmplifyTemplate().applicable(repeats=2).accepted
    assert not RepeatAmplifyTemplate().applicable(repeats=1).accepted
    assert not RepeatAmplifyTemplate().applicable(repeats=2, drain_between=False).accepted
    first = Cell(0, 0, 0, 0)
    second = Cell(1, 0, 0, 0)
    assert IndependentSwapTemplate().applicable(first=first, second=second).accepted
    assert not IndependentSwapTemplate().applicable(first=first, second=first).accepted
    anchor = _sample_relations()[0]
    assert ContextLiftTemplate().applicable(base=anchor, prefix_pad=0).accepted
    many_followups = _sample_relations()[-1]
    assert not ContextLiftTemplate().applicable(base=many_followups, prefix_pad=0).accepted
    identity = tuple(range(8))
    assert RegisterRenameTemplate().applicable(permutation=(1, 0, 2, 3, 4, 5, 6, 7)).accepted
    assert not RegisterRenameTemplate().applicable(permutation=identity).accepted
    assert HardReplayTemplate().applicable(repetitions=2, deterministic_observation=True).accepted
    assert (
        not HardReplayTemplate().applicable(repetitions=2, deterministic_observation=False).accepted
    )
    with pytest.raises(ValueError, match="distinct banks"):
        AnchorSwitchTemplate().instantiate(
            instance_id="bad",
            lane=0,
            token=0,
            epoch=0,
            bank_a=1,
            bank_b=1,
            pad=0,
        )


def test_instances_are_certified_serializable_and_registry_cached() -> None:
    """Canonical hashes bind programs/holes and actual instance data validates."""
    for relation in _sample_relations():
        template = TEMPLATE_REGISTRY[relation.relation_id]
        assert relation.architectural_precheck()
        assert relation.fault_free_precheck()
        assert template.reduction_rules(relation) == relation.reducer_rules
        assert relation.certificate.relation_instance_hash == relation.instance_hash
        assert relation.certificate.proof_method is not ProofMethod.EMPIRICAL_ONLY
        jsonschema.Draft202012Validator(RELATION_SCHEMA).validate(relation.to_data())

    left = AnchorSwitchTemplate().instantiate(
        instance_id="cache-left",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=1,
        pad=0,
    )
    right = AnchorSwitchTemplate().instantiate(
        instance_id="cache-right",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=1,
        pad=0,
    )
    assert left.instance_hash == right.instance_hash
    assert left.certificate is right.certificate

    registry = CertificateRegistry()
    restored = registry.load(left.certificate.to_data())
    assert restored == left.certificate
    assert registry.load(left.certificate.to_data()) is restored


def test_certificate_artifact_binding_rejects_semantic_or_claim_tampering() -> None:
    """Persisted proof metadata invalidates when semantics or certified claims change."""
    certificate = _sample_relations()[0].certificate
    for field, replacement in (
        ("semantic_version", "9.9.9"),
        ("architectural_claim", "unverified replacement claim"),
    ):
        data = certificate.to_data()
        data[field] = replacement
        with pytest.raises(ValueError, match="artifact digest"):
            RelationCertificate.from_data(data)
    data = certificate.to_data()
    data["future_field"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        RelationCertificate.from_data(data)


def test_reduced_domain_architecture_and_fault_free_normalization() -> None:
    """All reduced relation instances are silent/equivalent and off-fault residual is zero."""
    relations: list[RelationInstance] = []
    for lane, token, epoch, bank_a, bank_b, pad in itertools.product(
        range(2), range(4), range(2), range(4), range(4), range(4)
    ):
        if bank_a != bank_b:
            relations.append(
                AnchorSwitchTemplate().instantiate(
                    instance_id=f"reduced-anchor-{len(relations)}",
                    lane=lane,
                    token=token,
                    epoch=epoch,
                    bank_a=bank_a,
                    bank_b=bank_b,
                    pad=pad,
                )
            )
    for token_a, token_b, epoch, anchor in itertools.product(
        range(4), range(4), range(2), range(4)
    ):
        if token_a != token_b:
            relations.append(
                TokenSwitchTemplate().instantiate(
                    instance_id=f"reduced-token-{len(relations)}",
                    lane=0,
                    token_a=token_a,
                    token_b=token_b,
                    epoch=epoch,
                    anchor=anchor,
                    pad=0,
                )
            )
    relations.extend(_sample_relations()[2:7])
    for relation in relations:
        assert relation.architectural_precheck()
        assert relation.fault_free_precheck()
        secret = {lane: (lane + 3) & 15 for lane in relation.involved_lanes}
        for program in relation.programs:
            model = execute_experiment_program(program, secret, variant=FaultVariant.OFF)
            assert model.static_cycles == program.static_cycles()
            assert model.fault_cycles == 0


@pytest.mark.parametrize("relation", _sample_relations()[:7], ids=lambda item: item.relation_id)
def test_exact_extractors_keep_the_true_secret_and_fault(
    relation: RelationInstance,
) -> None:
    """Every secret-bearing template keeps the concrete generating model."""
    secret = (0, 9)
    source = _result(
        relation,
        follow_up=False,
        secret=secret,
        variant=FaultVariant.REFERENCE,
        noise=0,
        width=1,
        request_id=f"{relation.instance_id}:s",
    )
    follow_up = _result(
        relation,
        follow_up=True,
        secret=secret,
        variant=FaultVariant.REFERENCE,
        noise=0,
        width=1,
        request_id=f"{relation.instance_id}:f",
    )
    decision = _decision(relation, source, follow_up, noise_bound=0)
    extraction = extract_finite_models(
        relation,
        source,
        follow_up,
        decision,
        noise_bound=0,
    )
    if extraction.status is ExtractionStatus.EMITTED:
        assert extraction.hard_constraints[0].accepts(
            secret, fault_variant=FaultVariant.REFERENCE.value
        )
    else:
        assert extraction.status is ExtractionStatus.UNINFORMATIVE


def test_all_bounded_noise_generators_preserve_the_true_model() -> None:
    """For every reduced secret/noise pair, any emitted bounded constraint is sound."""
    relation = AnchorSwitchTemplate().instantiate(
        instance_id="bounded",
        lane=0,
        token=3,
        epoch=1,
        bank_a=0,
        bank_b=3,
        pad=(0 ^ 3 ^ 1) & 3,
    )
    for secret_value, source_noise, follow_noise in itertools.product(
        range(16), range(-1, 2), range(-1, 2)
    ):
        secret = (secret_value,)
        source = _result(
            relation,
            follow_up=False,
            secret=secret,
            variant=FaultVariant.REFERENCE,
            noise=source_noise,
            width=4,
            request_id="bounded:s",
        )
        follow_up = _result(
            relation,
            follow_up=True,
            secret=secret,
            variant=FaultVariant.REFERENCE,
            noise=follow_noise,
            width=4,
            request_id="bounded:f",
        )
        decision = _decision(relation, source, follow_up, noise_bound=1)
        extraction = extract_finite_models(
            relation,
            source,
            follow_up,
            decision,
            noise_bound=1,
        )
        if extraction.status is ExtractionStatus.EMITTED:
            assert extraction.hard_constraints[0].accepts(
                secret, fault_variant=FaultVariant.REFERENCE.value
            )
        else:
            assert extraction.status in {
                ExtractionStatus.INCONCLUSIVE,
                ExtractionStatus.UNINFORMATIVE,
            }


@pytest.mark.parametrize("relation", _sample_relations()[:7], ids=lambda item: item.relation_id)
def test_every_hard_extractor_is_sound_for_all_declared_noise_and_faults(
    relation: RelationInstance,
) -> None:
    """Every emitted bounded formula retains each concrete latent-fault generator."""
    secret = (5, 11)
    for variant, source_noise, follow_noise in itertools.product(
        tuple(FaultVariant), range(-1, 2), range(-1, 2)
    ):
        source = _result(
            relation,
            follow_up=False,
            secret=secret,
            variant=variant,
            noise=source_noise,
            width=4,
            request_id=f"all-bounded:{relation.instance_id}:source",
        )
        follow_up = _result(
            relation,
            follow_up=True,
            secret=secret,
            variant=variant,
            noise=follow_noise,
            width=4,
            request_id=f"all-bounded:{relation.instance_id}:follow-up",
        )
        decision = _decision(relation, source, follow_up, noise_bound=1)
        extraction = extract_finite_models(
            relation,
            source,
            follow_up,
            decision,
            noise_bound=1,
        )
        if extraction.status is ExtractionStatus.EMITTED:
            assert extraction.hard_constraints[0].accepts(secret, fault_variant=variant.value)
        else:
            assert extraction.status in {
                ExtractionStatus.INCONCLUSIVE,
                ExtractionStatus.UNINFORMATIVE,
            }


def test_emitted_constraint_round_trips_through_the_normative_schema() -> None:
    """A concrete exact violation produces stable schema-valid latent-fault IR."""
    relation = _sample_relations()[0]
    secret = (0,)
    source = _result(
        relation,
        follow_up=False,
        secret=secret,
        variant=FaultVariant.REFERENCE,
        noise=0,
        width=1,
        request_id="schema:s",
    )
    follow_up = _result(
        relation,
        follow_up=True,
        secret=secret,
        variant=FaultVariant.REFERENCE,
        noise=0,
        width=1,
        request_id="schema:f",
    )
    decision = _decision(relation, source, follow_up, noise_bound=0)
    extraction = extract_finite_models(relation, source, follow_up, decision, noise_bound=0)
    assert extraction.status is ExtractionStatus.EMITTED
    constraint = extraction.hard_constraints[0]
    jsonschema.Draft202012Validator(CONSTRAINT_SCHEMA).validate(constraint.to_data())
    assert json.loads(constraint.canonical_json()) == constraint.to_data()


def test_repeat_amplification_can_emit_a_bounded_standard_constraint() -> None:
    """Certified drain/phase restoration moves a real signal across width-four buckets."""
    relation = RepeatAmplifyTemplate().instantiate(
        instance_id="bounded-amplification",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad=0,
        repeats=16,
    )
    secret = (0,)
    emitted = 0
    for source_noise, follow_noise in itertools.product(range(-1, 2), repeat=2):
        source = _result(
            relation,
            follow_up=False,
            secret=secret,
            variant=FaultVariant.REFERENCE,
            noise=source_noise,
            width=4,
            request_id="amplify:s",
        )
        follow_up = _result(
            relation,
            follow_up=True,
            secret=secret,
            variant=FaultVariant.REFERENCE,
            noise=follow_noise,
            width=4,
            request_id="amplify:f",
        )
        decision = _decision(relation, source, follow_up, noise_bound=1)
        assert decision.kind is DecisionKind.BOUNDED_GREATER
        extraction = extract_finite_models(relation, source, follow_up, decision, noise_bound=1)
        assert extraction.status is ExtractionStatus.EMITTED
        constraint = extraction.hard_constraints[0]
        assert constraint.approximation.value == "bounded"
        assert constraint.accepts(secret, fault_variant=FaultVariant.REFERENCE.value)
        emitted += 1
    assert emitted == 9


def test_equal_quantized_buckets_remain_an_interval_not_false_equality() -> None:
    """A width-four equality crossing all signs is inconclusive and emits no hard fact."""
    relation = AnchorSwitchTemplate().instantiate(
        instance_id="quantized-equal",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    source = _result(
        relation,
        follow_up=False,
        secret=(0,),
        variant=FaultVariant.OFF,
        noise=0,
        width=4,
        request_id="equal:s",
    )
    follow_up = _result(
        relation,
        follow_up=True,
        secret=(0,),
        variant=FaultVariant.OFF,
        noise=0,
        width=4,
        request_id="equal:f",
    )
    assert source.observation.cycle_bucket == follow_up.observation.cycle_bucket
    decision = _decision(relation, source, follow_up, noise_bound=1)
    assert decision.kind is DecisionKind.INCONCLUSIVE
    assert {-1, 0, 1}.issubset(decision.feasible_deltas)
    extraction = extract_finite_models(relation, source, follow_up, decision, noise_bound=1)
    assert extraction.status is ExtractionStatus.INCONCLUSIVE
    assert extraction.hard_constraints == ()


def test_invalid_inconclusive_control_and_policy_paths_emit_nothing() -> None:
    """Architecture failures, apparatus relations, and weak certificates stay out of hard state."""
    anchor, *_, register, replay = _sample_relations()
    source = _result(
        anchor,
        follow_up=False,
        secret=(0,),
        variant=FaultVariant.REFERENCE,
        noise=0,
        width=1,
        request_id="invalid:s",
    )
    follow_up = _result(
        anchor,
        follow_up=True,
        secret=(0,),
        variant=FaultVariant.REFERENCE,
        noise=0,
        width=1,
        request_id="invalid:f",
    )
    bad_follow_up = replace(follow_up, public_digest="ffffffffffffffff")
    invalid = _decision(anchor, source, bad_follow_up, noise_bound=0)
    assert invalid.kind is DecisionKind.INVALID
    assert (
        extract_finite_models(
            anchor, source, bad_follow_up, invalid, noise_bound=0
        ).hard_constraints
        == ()
    )

    for control in (register, replay):
        assert not control.emits_secret_constraints

    exact = _decision(anchor, source, follow_up, noise_bound=0)
    rejected = extract_finite_models(
        anchor,
        source,
        follow_up,
        exact,
        noise_bound=0,
        minimum_certificate=ProofMethod.THEOREM,
    )
    assert rejected.status is ExtractionStatus.POLICY_REJECTED
    assert rejected.hard_constraints == ()


def test_off_control_constraints_never_exclude_the_true_off_model() -> None:
    """Keeping fault identity latent prevents equal off-control observations from false recovery."""
    relation = AnchorSwitchTemplate().instantiate(
        instance_id="off-control",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    for secret_value in range(16):
        secret = (secret_value,)
        source = _result(
            relation,
            follow_up=False,
            secret=secret,
            variant=FaultVariant.OFF,
            noise=0,
            width=1,
            request_id="off:s",
        )
        follow_up = _result(
            relation,
            follow_up=True,
            secret=secret,
            variant=FaultVariant.OFF,
            noise=0,
            width=1,
            request_id="off:f",
        )
        decision = _decision(relation, source, follow_up, noise_bound=0)
        extraction = extract_finite_models(relation, source, follow_up, decision, noise_bound=0)
        if extraction.status is ExtractionStatus.EMITTED:
            constraint = extraction.hard_constraints[0]
            assert constraint.accepts(secret, fault_variant=FaultVariant.OFF.value)
            assert set(constraint.allowed_assignments) == {(value,) for value in range(16)}
