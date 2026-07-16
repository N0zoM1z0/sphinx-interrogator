"""Relation-aware witness reducer tests."""

from __future__ import annotations

from sphinx_interrogator.ast import Program
from sphinx_interrogator.reducer import (
    ReductionConfig,
    ReductionKind,
    ReductionMode,
    RelationReducer,
    SignatureKind,
    default_model_committee,
)
from sphinx_interrogator.relations import (
    AnchorSwitchTemplate,
    ContextLiftTemplate,
    RegisterRenameTemplate,
    RepeatAmplifyTemplate,
    SoftHistoryContrastTemplate,
)
from sphinx_interrogator.target_model import FaultVariant


def _config() -> ReductionConfig:
    return ReductionConfig(
        mode=ReductionMode.IMPLIES_CORE,
        signature_kind=SignatureKind.SIGN,
        max_predicate_evaluations=256,
        max_generated_candidates=512,
    )


def test_repeat_and_padding_reduction_preserves_sign_consequence() -> None:
    """Amplified witnesses shrink while retaining the finite public sign partition."""
    relation = RepeatAmplifyTemplate().instantiate(
        instance_id="repeat-reduce",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad=8,
        repeats=6,
    )
    reducer = RelationReducer(
        models=default_model_committee(
            relation.involved_lanes,
            fault_variants=(FaultVariant.OFF, FaultVariant.REFERENCE),
        ),
        config=_config(),
    )

    result = reducer.reduce(relation)

    assert result.status == "minimized"
    assert result.reduced_relation.holes["repeats"] == 2
    assert result.reduced_relation.holes["pad"] == 0
    assert result.reduced_cost < result.original_cost
    assert {step.kind for step in result.steps} >= {
        ReductionKind.REPEAT_SHRINK,
        ReductionKind.PADDING_SIMPLIFICATION,
    }
    assert result.to_data()["preservation"]["uses_true_secret"] is False


def test_context_lift_can_collapse_to_known_base_relation() -> None:
    """A composed context relation collapses only when its primitive base is known."""
    base = AnchorSwitchTemplate().instantiate(
        instance_id="base-anchor",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    lifted = ContextLiftTemplate().instantiate(
        instance_id="context-reduce",
        base=base,
        prefix_pad=4,
        suffix_fence=True,
    )
    reducer = RelationReducer(
        models=default_model_committee(lifted.involved_lanes),
        known_relations={base.instance_hash: base},
        config=ReductionConfig(
            mode=ReductionMode.SAME_PARTITION,
            signature_kind=SignatureKind.EXACT_RESIDUAL,
            max_predicate_evaluations=64,
            max_generated_candidates=128,
        ),
    )

    result = reducer.reduce(lifted)

    assert result.status == "minimized"
    assert result.reduced_relation.relation_id == "anchor-switch/v1"
    assert any(step.kind is ReductionKind.RELATION_COMPOSITION_COLLAPSE for step in result.steps)


def test_symmetric_deletion_reduces_register_rename_witness() -> None:
    """Dead ordinary instructions are deleted symmetrically through the typed template."""
    program = Program.parse(
        "MOVI r0, 7\nMOV r1, r0\nADD r2, r0, r1\nMIXOUT r2\nHALT\n",
        lanes=1,
    )
    relation = RegisterRenameTemplate().instantiate(
        instance_id="rename-reduce",
        source=program,
        permutation=(1, 2, 0, 3, 4, 5, 6, 7),
    )
    reducer = RelationReducer(
        models=default_model_committee(relation.involved_lanes),
        config=ReductionConfig(
            mode=ReductionMode.SAME_PARTITION,
            signature_kind=SignatureKind.EXACT_RESIDUAL,
            max_predicate_evaluations=128,
            max_generated_candidates=128,
        ),
    )

    result = reducer.reduce(relation)

    assert result.status == "minimized"
    assert len(result.reduced_relation.source_program.instructions) == 1
    assert result.reduced_relation.source_program.render() == "HALT\n"
    assert any(step.kind is ReductionKind.SYMMETRIC_DELETION for step in result.steps)


def test_soft_history_shortening_preserves_measurement_suffix() -> None:
    """State-conditioned witnesses can shorten public histories without touching measurement."""
    measurement = AnchorSwitchTemplate().instantiate(
        instance_id="measurement",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    relation = SoftHistoryContrastTemplate().instantiate(
        instance_id="soft-reduce",
        history_a=Program.parse("PAD 4\nFENCE\nHALT\n", lanes=1),
        history_b=Program.parse("PAD 8\nFENCE\nHALT\n", lanes=1),
        measurement=measurement,
        state_model_id="state-model-1",
        source_state="q0",
        follow_up_state="q1",
    )
    reducer = RelationReducer(
        models=default_model_committee(relation.involved_lanes),
        known_relations={measurement.instance_hash: measurement},
        config=_config(),
    )

    result = reducer.reduce(relation)

    assert result.status == "minimized"
    assert (
        result.reduced_relation.source_program.instructions[
            -len(measurement.source_program.instructions) :
        ]
        == measurement.source_program.instructions
    )
    assert any(step.kind is ReductionKind.CONTEXT_HISTORY_SHORTENING for step in result.steps)


def test_reducer_reuses_signature_cache_on_repeated_run() -> None:
    """Predicate/signature caches are deterministic and observable in run metrics."""
    relation = RepeatAmplifyTemplate().instantiate(
        instance_id="repeat-cache",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad=4,
        repeats=3,
    )
    reducer = RelationReducer(
        models=default_model_committee(
            relation.involved_lanes,
            fault_variants=(FaultVariant.REFERENCE,),
        ),
        config=_config(),
    )

    first = reducer.reduce(relation)
    second = reducer.reduce(relation)

    assert first.status == second.status == "minimized"
    assert second.cache_hits > first.cache_hits
