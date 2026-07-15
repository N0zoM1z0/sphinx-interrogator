"""Cross-language golden tests for the independent public target-family model."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from sphinx_interrogator.target_model import (
    FaultVariant,
    MicroState,
    anchor_transition,
    bank_of,
    probe_transition,
    soft_reset,
)

VECTORS = Path(__file__).parents[1] / "fixtures/model/micro-vectors.json"


def test_bank_and_guarded_replay_vectors() -> None:
    """Python agrees with vectors also executed by the Rust concrete model."""
    document = cast("dict[str, Any]", json.loads(VECTORS.read_text(encoding="utf-8")))
    for raw in cast("list[dict[str, int]]", document["bank_vectors"]):
        assert bank_of(raw["secret"], raw["token"], raw["epoch"], salt=raw["salt"]) == raw["bank"]
    for raw in cast("list[dict[str, int]]", document["cell_vectors"]):
        state = MicroState(phase=raw["phase"], replay_credit=raw["replay_credit"])
        probed = probe_transition(
            state,
            lane=raw["lane"],
            token=raw["token"],
            epoch=raw["epoch"],
            secret_bank=raw["secret_bank"],
        )
        for variant, expected_key in (
            (FaultVariant.REFERENCE, "reference_delta"),
            (FaultVariant.WEAK, "weak_delta"),
            (FaultVariant.SIGNED, "signed_delta"),
        ):
            next_state, delta, context = anchor_transition(
                probed,
                bank=raw["anchor_bank"],
                epoch=raw["epoch"],
                variant=variant,
            )
            assert context is not None
            assert next_state.phase == raw["next_phase"]
            assert next_state.replay_credit == raw["next_replay_credit"]
            assert next_state.last_bank == raw["last_bank"]
            assert delta == raw[expected_key]


def test_soft_reset_preserves_only_named_symbolic_fields() -> None:
    """The symbolic reset projection clears pending and every unnamed field."""
    state = probe_transition(
        MicroState(phase=2, last_bank=1, replay_credit=2),
        lane=1,
        token=0,
        epoch=0,
        secret_bank=3,
    )
    reset = soft_reset(state, frozenset({"phase", "replay_credit"}))
    assert reset.phase == state.phase
    assert reset.replay_credit == state.replay_credit
    assert reset.last_bank is None
    assert reset.pending_probe is None
    assert not reset.uop_cache_valid


def test_symbolic_model_rejects_out_of_domain_and_unknown_reset_fields() -> None:
    """Malformed symbolic inputs fail instead of being silently truncated."""
    with pytest.raises(ValueError, match="phase"):
        MicroState(phase=4)
    with pytest.raises(ValueError, match="secret"):
        bank_of(16, 0, 0)
    with pytest.raises(TypeError, match="token"):
        bank_of(0, True, 0)
    with pytest.raises(ValueError, match="unknown soft-reset fields"):
        soft_reset(MicroState(), frozenset({"history_hash"}))
