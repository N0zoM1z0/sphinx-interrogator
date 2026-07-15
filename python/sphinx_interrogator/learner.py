"""Interfaces for exact-history and active finite-state abstractions."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ResetCapability(StrEnum):
    """Reset capabilities relevant to active automata learning."""

    HARD = "hard"
    SOFT = "soft"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class HistorySymbol:
    """Finite abstraction of one public query/response interaction."""

    relation_id: str
    hole_signature: str
    outcome_class: str


@dataclass(frozen=True, slots=True)
class HistoryState:
    """Exact bounded-history state used before a learned quotient is trusted."""

    suffix: tuple[HistorySymbol, ...]


class ExactHistoryTracker:
    """Track a bounded public interaction suffix as a sound state key."""

    def __init__(self, maximum_depth: int) -> None:
        """Create an empty tracker with a positive suffix bound."""
        if maximum_depth < 1:
            raise ValueError("maximum_depth must be positive")
        self._maximum_depth = maximum_depth
        self._history: list[HistorySymbol] = []

    def observe(self, symbol: HistorySymbol) -> HistoryState:
        """Append a symbol and return the resulting exact bounded state."""
        self._history.append(symbol)
        if len(self._history) > self._maximum_depth:
            self._history = self._history[-self._maximum_depth :]
        return self.state()

    def reset(self, capability: ResetCapability) -> None:
        """Clear exact history only when the public reset contract justifies it."""
        if capability is ResetCapability.HARD:
            self._history.clear()

    def state(self) -> HistoryState:
        """Return the current immutable bounded-history key."""
        return HistoryState(tuple(self._history))


class AalpyIntegration:
    """Dependency boundary for the M8 active-automata-learning milestone."""

    @staticmethod
    def available() -> bool:
        """Return whether AALpy is installed in the active Python environment."""
        return importlib.util.find_spec("aalpy") is not None

    @staticmethod
    def alphabet(symbols: Iterable[HistorySymbol]) -> tuple[str, ...]:
        """Canonicalize public query classes into a deterministic learner alphabet."""
        return tuple(
            sorted(
                {
                    f"{symbol.relation_id}|{symbol.hole_signature}|{symbol.outcome_class}"
                    for symbol in symbols
                }
            )
        )
