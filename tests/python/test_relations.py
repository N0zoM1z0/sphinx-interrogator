"""Tests for certified relation templates and fact extraction."""

from sphinx_interrogator.model import OutcomeClass, RelationEvidence
from sphinx_interrogator.relations import AnchorSwitchTemplate


def test_anchor_switch_preserves_architectural_silence_and_static_cost() -> None:
    """Changing only an anchor should preserve the scaffold proof obligations."""
    relation = AnchorSwitchTemplate().instantiate(
        instance_id="r1",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    assert relation.architectural_precheck()
    assert relation.source_program.static_cycles() == relation.follow_up_programs[0].static_cycles()
    assert len(relation.certificate.artifact_digest) == 64


def test_positive_violation_extracts_directional_bank_facts() -> None:
    """A certified slower follow-up should identify its anchor bank."""
    template = AnchorSwitchTemplate()
    relation = template.instantiate(
        instance_id="r2",
        lane=1,
        token=4,
        epoch=1,
        bank_a=0,
        bank_b=3,
        pad=0,
    )
    evidence = RelationEvidence(
        relation_instance_id="r2",
        outcome=OutcomeClass.VIOLATED_POSITIVE,
        normalized_delta=1.0,
        confidence=1.0,
        source_request_ids=("a", "b"),
    )
    facts = template.extract_facts(
        relation,
        evidence,
        hard_preconditions_certified=True,
    )
    assert {(fact.bank, fact.equal) for fact in facts} == {(3, True), (0, False)}


def test_exact_holds_excludes_both_compared_banks() -> None:
    """An exact high-confidence equality response excludes both anchor banks."""
    template = AnchorSwitchTemplate()
    relation = template.instantiate(
        instance_id="r3",
        lane=2,
        token=1,
        epoch=0,
        bank_a=1,
        bank_b=2,
        pad=0,
    )
    evidence = RelationEvidence(
        relation_instance_id="r3",
        outcome=OutcomeClass.HOLDS,
        normalized_delta=0.0,
        confidence=1.0,
        source_request_ids=("a", "b"),
    )
    facts = template.extract_facts(
        relation,
        evidence,
        hard_preconditions_certified=True,
    )
    assert {(fact.bank, fact.equal) for fact in facts} == {(1, False), (2, False)}
