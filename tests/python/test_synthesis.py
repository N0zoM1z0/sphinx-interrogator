"""Tests for finite grammar-guided relational query selection."""

from sphinx_interrogator.solver import SecretDomain
from sphinx_interrogator.synthesis import GrammarGuidedSelector, entropy_of_partition


def test_entropy_rewards_balanced_partition() -> None:
    """A balanced outcome partition should carry more information than a singleton split."""
    assert entropy_of_partition((4, 4, 8)) > entropy_of_partition((1, 1, 14))


def test_selector_returns_a_typed_candidate() -> None:
    """An unresolved domain should yield a novel query from the finite grammar."""
    selector = GrammarGuidedSelector(tokens=(0,), epochs=(0,), pads=(0,))
    selected = selector.choose(SecretDomain(1))
    assert selected is not None
    assert selected.query.lane == 0
    assert len(selected.outcome_partition) == 3
