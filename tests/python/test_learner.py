"""Tests for exact-history and active state-learning abstractions."""

from __future__ import annotations

import pytest

from sphinx_interrogator.learner import (
    AalpyMealyLearner,
    ExactHistoryLearner,
    ExactHistoryTracker,
    HistorySymbol,
    MacroAlphabet,
    MembershipCache,
    OneStateLearner,
    OutputSymbol,
    ResetCapability,
    generated_sequences,
)


def _toggle_oracle(sequence: tuple[str, ...]) -> tuple[str, ...]:
    state = "OFF"
    outputs = []
    for symbol in sequence:
        if symbol == "toggle":
            state = "ON" if state == "OFF" else "OFF"
        elif symbol != "ping":
            raise ValueError(f"unexpected input {symbol}")
        outputs.append(state)
    return tuple(outputs)


def test_exact_history_tracks_suffix_and_only_hard_reset_clears() -> None:
    """Exact-history mode carries bounded public history through soft resets."""
    tracker = ExactHistoryTracker(maximum_depth=2)
    first = HistorySymbol("anchor-switch/v1", "lane=0", "REL_GREATER")
    second = HistorySymbol("repeat-amplify/v1", "lane=1", "REL_INCONCLUSIVE")
    third = HistorySymbol("repeat-amplify/v1", "lane=2", "REL_GREATER")

    assert tracker.state().state_id() == "history-empty"
    tracker.observe(first)
    tracker.observe(second)
    soft_state = tracker.state()
    tracker.reset(ResetCapability.SOFT)
    assert tracker.state() == soft_state

    bounded = tracker.observe(third)
    assert bounded.suffix == (second, third)
    assert bounded.state_id().startswith("history-")
    tracker.reset(ResetCapability.HARD)
    assert tracker.state().suffix == ()


def test_one_state_learner_models_hard_reset_campaigns() -> None:
    """The no-learner baseline is an explicit one-state Mealy model."""
    alphabet = MacroAlphabet(
        abstraction_version="test/v1",
        input_symbols=("measure",),
        output_symbols=(OutputSymbol.PUBLIC_OK.value,),
    )
    model = OneStateLearner().learn(model_id="one-state", alphabet=alphabet)
    assert model.predict(("measure", "measure")) == (
        OutputSymbol.PUBLIC_OK.value,
        OutputSymbol.PUBLIC_OK.value,
    )
    assert model.access_sequence("q0") == ()
    with pytest.raises(ValueError, match="at least two states"):
        model.distinguish(frozenset({"q0"}), max_depth=1)
    assert model.artifact_digest() == model.from_data(model.to_data()).artifact_digest()


def test_membership_cache_digest_is_stable_and_deduplicates_queries() -> None:
    """Membership evidence is cached by whole public input word."""
    calls = 0

    def oracle(sequence: tuple[str, ...]) -> tuple[str, ...]:
        nonlocal calls
        calls += 1
        return tuple("seen" for _ in sequence)

    cache = MembershipCache()
    assert cache.query(("a", "b"), oracle) == ("seen", "seen")
    digest = cache.digest()
    assert cache.query(("a", "b"), oracle) == ("seen", "seen")
    assert calls == 1
    assert cache.digest() == digest
    assert cache.to_data()["digest"] == digest


def test_exact_history_model_predicts_fixture_better_than_no_learner() -> None:
    """Exact-history mode carries enough bounded history for the stateful fixture."""
    alphabet = MacroAlphabet(
        abstraction_version="toggle/v1",
        input_symbols=("ping", "toggle"),
        output_symbols=("OFF", "ON"),
    )
    held_out = generated_sequences(alphabet.input_symbols, max_depth=4)
    exact = ExactHistoryLearner().learn(
        model_id="exact-history",
        alphabet=alphabet,
        oracle=_toggle_oracle,
        maximum_depth=4,
    )
    no_learner = OneStateLearner().learn(
        model_id="no-learner",
        alphabet=alphabet,
        output="OFF",
    )

    assert exact.status == "active"
    assert exact.conformance["held_out_accuracy"] == 1.0
    no_learner_matches = sum(
        no_learner.predict(sequence) == _toggle_oracle(sequence) for sequence in held_out
    )
    assert no_learner_matches / len(held_out) < 0.75


def test_aalpy_lstar_learns_known_two_state_mealy_fixture() -> None:
    """The real AALpy backend learns a deterministic fixture and predicts held-out words."""
    assert AalpyMealyLearner.available()
    alphabet = MacroAlphabet(
        abstraction_version="toggle/v1",
        input_symbols=("ping", "toggle"),
        output_symbols=("OFF", "ON"),
    )
    held_out = generated_sequences(alphabet.input_symbols, max_depth=4)
    model = AalpyMealyLearner(max_states=2).learn(
        model_id="toggle-model",
        alphabet=alphabet,
        oracle=_toggle_oracle,
        held_out_sequences=held_out,
    )

    assert model.status == "active"
    assert model.conformance["held_out_accuracy"] == 1.0
    assert len(model.states) == 2
    assert model.predict(("ping", "toggle", "ping")) == ("OFF", "ON", "ON")
    assert all(model.access_sequence(state) is not None for state in model.states)
    assert model.distinguish(frozenset(model.states), max_depth=2) is not None
    restored = model.from_data(model.to_data())
    assert restored.predict(("toggle", "toggle", "ping")) == ("ON", "OFF", "OFF")
    assert restored.artifact_digest() == model.artifact_digest()
