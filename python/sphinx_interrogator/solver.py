"""Sound finite-domain constraint layer for the identity-mapping profiles."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import prod

from sphinx_interrogator.model import CandidateSummary
from sphinx_interrogator.relations import BankFact
from sphinx_interrogator.target_model import SBOX4


class InconsistentModelError(RuntimeError):
    """Raised when hard evidence eliminates every value for a secret cell."""


@dataclass(frozen=True, slots=True)
class BankEqualityConstraint:
    """Constraint on a two-bit projection of `SBOX4[secret XOR token]`."""

    lane: int
    token: int
    epoch: int
    bank: int
    equal: bool
    source_relation_instance_id: str
    confidence: float = 1.0

    @classmethod
    def from_fact(cls, fact: BankFact) -> BankEqualityConstraint:
        """Convert a relation extractor fact into the solver IR."""
        return cls(
            lane=fact.lane,
            token=fact.token,
            epoch=fact.epoch,
            bank=fact.bank,
            equal=fact.equal,
            source_relation_instance_id=fact.source_relation_instance_id,
            confidence=fact.confidence,
        )

    def accepts(self, secret_nibble: int) -> bool:
        """Evaluate this identity-profile constraint on one candidate nibble."""
        mapped = bank_of(secret_nibble, self.token, self.epoch)
        return (mapped == self.bank) is self.equal


@dataclass(frozen=True, slots=True)
class AppliedConstraint:
    """Audit record describing one domain update."""

    constraint: BankEqualityConstraint
    domain_before: frozenset[int]
    domain_after: frozenset[int]


class SecretDomain:
    """Factorized exact domains for tutorial and standard identity profiles.

    This is not a replacement for the required Z3/MaxSMT milestone. It is an
    executable reference model for the constraint semantics and supports exact
    uniqueness checks when lane mapping and salts are public identities.
    """

    def __init__(self, cells: int) -> None:
        """Initialize every four-bit cell to all sixteen possible values."""
        if cells < 1:
            raise ValueError("cells must be positive")
        self._domains: list[frozenset[int]] = [frozenset(range(16)) for _ in range(cells)]
        self._history: list[AppliedConstraint] = []

    @property
    def cells(self) -> int:
        """Return the number of ordered secret cells."""
        return len(self._domains)

    @property
    def history(self) -> tuple[AppliedConstraint, ...]:
        """Return the immutable constraint-application trace."""
        return tuple(self._history)

    def domain(self, lane: int) -> frozenset[int]:
        """Return the current exact nibble domain for one identity-mapped lane."""
        return self._domains[lane]

    def apply(self, constraint: BankEqualityConstraint) -> AppliedConstraint:
        """Intersect one lane domain with a hard bank constraint."""
        if not 0 <= constraint.lane < self.cells:
            raise ValueError(f"lane {constraint.lane} is outside the secret domain")
        before = self._domains[constraint.lane]
        after = frozenset(value for value in before if constraint.accepts(value))
        if not after:
            raise InconsistentModelError(
                "constraint from "
                f"{constraint.source_relation_instance_id} empties lane {constraint.lane}"
            )
        self._domains[constraint.lane] = after
        record = AppliedConstraint(constraint=constraint, domain_before=before, domain_after=after)
        self._history.append(record)
        return record

    def apply_all(
        self, constraints: Iterable[BankEqualityConstraint]
    ) -> tuple[AppliedConstraint, ...]:
        """Apply constraints in order and return their audit records."""
        return tuple(self.apply(constraint) for constraint in constraints)

    def candidate_count(self) -> int:
        """Return the exact Cartesian-product candidate count."""
        return prod(len(domain) for domain in self._domains)

    def unique_secret(self) -> tuple[int, ...] | None:
        """Return the ordered secret exactly when every lane has one candidate."""
        if any(len(domain) != 1 for domain in self._domains):
            return None
        return tuple(next(iter(domain)) for domain in self._domains)

    def alternative_model_exists(self, proposed: tuple[int, ...]) -> bool:
        """Perform the factorized equivalent of an SMT alternative-model query."""
        if len(proposed) != self.cells:
            raise ValueError("proposed secret has the wrong number of cells")
        for lane, domain in enumerate(self._domains):
            if proposed[lane] not in domain:
                raise ValueError("proposed secret does not satisfy the current hard constraints")
        return self.candidate_count() > 1

    def summary(self) -> CandidateSummary:
        """Build a public campaign summary without enumerating the Cartesian product."""
        unique = self.unique_secret()
        return CandidateSummary(
            exact_count=self.candidate_count(),
            lane_domains=tuple(self._domains),
            unique_secret_hex=None
            if unique is None
            else "".join(format(value, "x") for value in unique),
        )


def bank_of(secret_nibble: int, token: int, epoch: int) -> int:
    """Evaluate the public version-1 bank mapping for identity profiles."""
    if not 0 <= secret_nibble <= 15:
        raise ValueError("secret_nibble must fit in four bits")
    if not 0 <= token <= 15:
        raise ValueError("token must fit in four bits")
    if epoch not in (0, 1):
        raise ValueError("epoch must be zero or one")
    value = SBOX4[secret_nibble ^ token]
    return (value >> (2 * epoch)) & 0b11
