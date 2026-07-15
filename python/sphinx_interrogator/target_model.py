"""Independent symbolic model of the public Sphinx bank/fault/state family."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SBOX4: tuple[int, ...] = (6, 11, 0, 4, 13, 3, 15, 8, 10, 2, 5, 12, 1, 14, 7, 9)


class FaultVariant(StrEnum):
    """Known public fault-model family; a challenge's concrete member is private."""

    OFF = "off"
    REFERENCE = "reference"
    WEAK = "weak"
    SIGNED = "signed"


@dataclass(frozen=True, slots=True)
class PendingProbe:
    """Symbolic pending vault request."""

    bank: int
    epoch: int
    guard: bool


@dataclass(frozen=True, slots=True)
class MicroState:
    """Relevant hidden-state abstraction known to Interrogator, not its concrete value."""

    phase: int = 0
    last_bank: int | None = None
    replay_credit: int = 0
    uop_cache_tag: int = 0
    uop_cache_valid: bool = False
    pending_probe: PendingProbe | None = None

    def __post_init__(self) -> None:
        """Validate the finite symbolic state domain."""
        _bounded(self.phase, 0, 3, "phase")
        if self.last_bank is not None:
            _bounded(self.last_bank, 0, 3, "last_bank")
        _bounded(self.replay_credit, 0, 3, "replay_credit")
        _bounded(self.uop_cache_tag, 0, 15, "uop_cache_tag")


@dataclass(frozen=True, slots=True)
class FaultContext:
    """Pure guarded-replay predicates for one completed cell."""

    collision: bool
    guard: bool
    suppress: bool
    replay_credit: int


def bank_of(secret: int, token: int, epoch: int, *, salt: int = 0) -> int:
    """Evaluate one public S-box projection with a symbolic cell and salt."""
    _bounded(secret, 0, 15, "secret")
    _bounded(token, 0, 15, "token")
    _bounded(epoch, 0, 1, "epoch")
    _bounded(salt, 0, 15, "salt")
    return (SBOX4[secret ^ token ^ salt] >> (2 * epoch)) & 0b11


def probe_transition(
    state: MicroState,
    *,
    lane: int,
    token: int,
    epoch: int,
    secret_bank: int,
) -> MicroState:
    """Apply the pure resolved PROBE transition."""
    _bounded(lane, 0, None, "lane")
    _bounded(token, 0, 15, "token")
    _bounded(epoch, 0, 1, "epoch")
    _bounded(secret_bank, 0, 3, "secret_bank")
    guard = state.phase == ((lane ^ token ^ epoch) & 0b11)
    return MicroState(
        phase=(state.phase + 1 + epoch) & 0b11,
        last_bank=state.last_bank,
        replay_credit=state.replay_credit,
        uop_cache_tag=0xC,
        uop_cache_valid=True,
        pending_probe=PendingProbe(secret_bank, epoch, guard),
    )


def anchor_transition(
    state: MicroState,
    *,
    bank: int,
    epoch: int,
    variant: FaultVariant,
) -> tuple[MicroState, int, FaultContext | None]:
    """Apply ANCHOR state update and the separately selected timing policy."""
    _bounded(bank, 0, 3, "bank")
    _bounded(epoch, 0, 1, "epoch")
    next_state = MicroState(
        phase=state.phase,
        last_bank=state.last_bank,
        replay_credit=state.replay_credit,
        uop_cache_tag=0xD,
        uop_cache_valid=True,
        pending_probe=None,
    )
    pending = state.pending_probe
    if pending is None or pending.epoch != epoch:
        return next_state, 0, None
    collision = pending.bank == bank
    context = FaultContext(
        collision=collision,
        guard=pending.guard,
        suppress=state.replay_credit == 3,
        replay_credit=state.replay_credit,
    )
    next_state = MicroState(
        phase=state.phase,
        last_bank=pending.bank,
        replay_credit=(
            min(3, state.replay_credit + 1) if collision else max(0, state.replay_credit - 1)
        ),
        uop_cache_tag=0xD,
        uop_cache_valid=True,
        pending_probe=None,
    )
    return next_state, fault_delta(variant, context), context


def pad_transition(state: MicroState, amount: int) -> MicroState:
    """Apply a public phase step and cache update."""
    _bounded(amount, 0, 65_535, "amount")
    return MicroState(
        phase=(state.phase + amount) & 0b11,
        last_bank=state.last_bank,
        replay_credit=state.replay_credit,
        uop_cache_tag=0xE,
        uop_cache_valid=True,
        pending_probe=state.pending_probe,
    )


def fence_transition(state: MicroState) -> MicroState:
    """Drain replay/pending state without changing phase or last bank."""
    return MicroState(
        phase=state.phase,
        last_bank=state.last_bank,
        replay_credit=0,
        uop_cache_tag=0xF,
        uop_cache_valid=True,
        pending_probe=None,
    )


def soft_reset(state: MicroState, preserved: frozenset[str]) -> MicroState:
    """Reset all hidden fields except the exact declared public subset."""
    allowed = {"phase", "last_bank", "replay_credit", "uop_cache"}
    unknown = preserved.difference(allowed)
    if unknown:
        raise ValueError(f"unknown soft-reset fields: {sorted(unknown)}")
    return MicroState(
        phase=state.phase if "phase" in preserved else 0,
        last_bank=state.last_bank if "last_bank" in preserved else None,
        replay_credit=state.replay_credit if "replay_credit" in preserved else 0,
        uop_cache_tag=state.uop_cache_tag if "uop_cache" in preserved else 0,
        uop_cache_valid=state.uop_cache_valid if "uop_cache" in preserved else False,
        pending_probe=None,
    )


def fault_delta(variant: FaultVariant, context: FaultContext | None) -> int:
    """Evaluate one known fault variant independently of state transition."""
    if context is None or variant is FaultVariant.OFF:
        return 0
    if variant is FaultVariant.REFERENCE:
        return int(context.collision and context.guard and not context.suppress)
    if variant is FaultVariant.WEAK:
        return int(context.collision and context.guard and context.replay_credit == 0)
    if context.collision and context.guard and not context.suppress:
        return 1
    if not context.collision and context.guard and context.replay_credit == 2:
        return -1
    return 0


def _bounded(value: int, minimum: int, maximum: int | None, role: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{role} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        rendered = str(maximum) if maximum is not None else "unbounded"
        raise ValueError(f"{role} is outside {minimum}..{rendered}")
