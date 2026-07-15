"""Tests for the executable finite-domain constraint reference model."""

from sphinx_interrogator.solver import BankEqualityConstraint, SecretDomain, bank_of


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
