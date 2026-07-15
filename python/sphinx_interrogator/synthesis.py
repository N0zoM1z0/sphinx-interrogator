"""Grammar-guided query selection over finite secret hypotheses."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations

from sphinx_interrogator.solver import SecretDomain, bank_of


@dataclass(frozen=True, slots=True)
class QueryCandidate:
    """Concrete holes for an anchor-switch relation template."""

    lane: int
    token: int
    epoch: int
    bank_a: int
    bank_b: int
    pad: int
    repeats: int = 1


@dataclass(frozen=True, slots=True)
class ScoredQuery:
    """Candidate plus its expected partition utility and public cost."""

    query: QueryCandidate
    outcome_partition: tuple[int, int, int]
    information_gain_bits: float
    static_cycles: int
    score: float


class GrammarGuidedSelector:
    """Small CEGIS-style selector for the executable tutorial scaffold.

    Candidate programs come from a typed finite grammar. Counterexamples are the
    surviving secret values not separated by earlier choices; the selector searches
    for the next grammar assignment with maximal predicted partition entropy.
    """

    def __init__(
        self,
        *,
        tokens: Iterable[int] = range(16),
        epochs: Iterable[int] = (0, 1),
        pads: Iterable[int] = range(4),
        repeats: Sequence[int] = (1,),
        cycle_penalty: float = 0.002,
    ) -> None:
        """Configure the finite syntax-guided search space."""
        self._tokens = tuple(tokens)
        self._epochs = tuple(epochs)
        self._pads = tuple(pads)
        self._repeats = tuple(repeats)
        self._cycle_penalty = cycle_penalty

    def enumerate(self, lane: int) -> tuple[QueryCandidate, ...]:
        """Enumerate well-typed anchor-switch assignments for one lane."""
        return tuple(
            QueryCandidate(
                lane=lane,
                token=token,
                epoch=epoch,
                bank_a=bank_a,
                bank_b=bank_b,
                pad=pad,
                repeats=repeats,
            )
            for token in self._tokens
            for epoch in self._epochs
            for bank_a, bank_b in combinations(range(4), 2)
            for pad in self._pads
            for repeats in self._repeats
        )

    def score(self, candidate: QueryCandidate, domain: frozenset[int]) -> ScoredQuery:
        """Predict the three-way relation response partition on a nibble domain."""
        if not domain:
            raise ValueError("cannot score an empty domain")
        count_a = 0
        count_b = 0
        count_other = 0
        for secret in domain:
            bank = bank_of(secret, candidate.token, candidate.epoch)
            if bank == candidate.bank_a:
                count_a += 1
            elif bank == candidate.bank_b:
                count_b += 1
            else:
                count_other += 1
        partition = (count_a, count_b, count_other)
        gain = entropy_of_partition(partition)
        static_cycles = candidate.pad + candidate.repeats * 9 + 3
        score = gain - self._cycle_penalty * static_cycles
        return ScoredQuery(
            query=candidate,
            outcome_partition=partition,
            information_gain_bits=gain,
            static_cycles=static_cycles,
            score=score,
        )

    def choose(
        self,
        domain: SecretDomain,
        *,
        used: Iterable[QueryCandidate] = (),
    ) -> ScoredQuery | None:
        """Choose the highest-scoring novel grammar assignment across unresolved lanes."""
        used_set = set(used)
        best: ScoredQuery | None = None
        for lane in range(domain.cells):
            lane_domain = domain.domain(lane)
            if len(lane_domain) <= 1:
                continue
            for candidate in self.enumerate(lane):
                if candidate in used_set:
                    continue
                scored = self.score(candidate, lane_domain)
                if best is None or scored.score > best.score:
                    best = scored
        return best


def entropy_of_partition(parts: Sequence[int]) -> float:
    """Return Shannon entropy of a finite outcome partition in bits."""
    total = sum(parts)
    if total <= 0:
        raise ValueError("partition must contain at least one hypothesis")
    entropy = 0.0
    for part in parts:
        if part:
            probability = part / total
            entropy -= probability * math.log2(probability)
    return entropy
