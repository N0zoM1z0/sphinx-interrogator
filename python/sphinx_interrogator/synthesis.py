"""Typed grammar, SMT hole filling, and CEGIS experiment synthesis."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from itertools import combinations, product
from typing import Protocol

import z3  # type: ignore[import-untyped]

from sphinx_interrogator.frontier import FrontierCandidate
from sphinx_interrogator.relations import (
    AnchorSwitchTemplate,
    RelationInstance,
    RepeatAmplifyTemplate,
)
from sphinx_interrogator.solver import (
    HypothesisStore,
    ModelAssignment,
    SecretDomain,
    bank_of,
)
from sphinx_interrogator.target_model import (
    FaultVariant,
    MicroState,
    execute_experiment_program,
)

_GRAMMAR_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class QueryCandidate:
    """Concrete typed holes for an ``anchor-switch/v1`` skeleton."""

    lane: int
    token: int
    epoch: int
    bank_a: int
    bank_b: int
    pad: int
    repeats: int = 1

    def __post_init__(self) -> None:
        _bounded(self.lane, 0, None, "lane")
        _bounded(self.token, 0, 15, "token")
        _bounded(self.epoch, 0, 1, "epoch")
        _bounded(self.bank_a, 0, 3, "bank_a")
        _bounded(self.bank_b, 0, 3, "bank_b")
        _bounded(self.pad, 0, 65_535, "pad")
        if self.bank_a >= self.bank_b:
            raise ValueError("anchor-switch banks must be in canonical increasing order")
        if self.repeats != 1:
            raise ValueError("M6 anchor-switch skeleton uses one certified cell per arm")

    @property
    def skeleton_kind(self) -> SkeletonKind:
        """Return the grammar production lowered by this assignment."""
        return SkeletonKind.ANCHOR_SWITCH

    def canonical_key(self) -> str:
        """Return the deterministic grammar-assignment key."""
        return (
            f"anchor:l{self.lane}:t{self.token}:e{self.epoch}:"
            f"b{self.bank_a}-{self.bank_b}:p{self.pad}"
        )

    def hole_values(self) -> Mapping[str, int]:
        """Return the finite typed-hole assignment."""
        return {
            "lane": self.lane,
            "token": self.token,
            "epoch": self.epoch,
            "bank_a": self.bank_a,
            "bank_b": self.bank_b,
            "pad": self.pad,
        }

    def lower(self, instance_id: str) -> RelationInstance:
        """Lower only through the certified typed relation constructor."""
        return AnchorSwitchTemplate().instantiate(
            instance_id=instance_id,
            lane=self.lane,
            token=self.token,
            epoch=self.epoch,
            bank_a=self.bank_a,
            bank_b=self.bank_b,
            pad=self.pad,
            repeats=1,
        )


@dataclass(frozen=True, slots=True)
class RepeatAmplifyCandidate:
    """Concrete typed holes for a drained ``repeat-amplify/v1`` skeleton."""

    lane: int
    token: int
    epoch: int
    anchor: int
    pad: int
    repeats: int

    def __post_init__(self) -> None:
        _bounded(self.lane, 0, None, "lane")
        _bounded(self.token, 0, 15, "token")
        _bounded(self.epoch, 0, 1, "epoch")
        _bounded(self.anchor, 0, 3, "anchor")
        _bounded(self.pad, 0, 65_535, "pad")
        _bounded(self.repeats, 2, 16, "repeats")

    @property
    def skeleton_kind(self) -> SkeletonKind:
        """Return the grammar production lowered by this assignment."""
        return SkeletonKind.REPEAT_AMPLIFY

    def canonical_key(self) -> str:
        """Return the deterministic grammar-assignment key."""
        return (
            f"repeat:l{self.lane}:t{self.token}:e{self.epoch}:"
            f"b{self.anchor}:p{self.pad}:r{self.repeats}"
        )

    def hole_values(self) -> Mapping[str, int]:
        """Return the finite typed-hole assignment."""
        return {
            "lane": self.lane,
            "token": self.token,
            "epoch": self.epoch,
            "anchor": self.anchor,
            "pad": self.pad,
            "repeats": self.repeats,
        }

    def lower(self, instance_id: str) -> RelationInstance:
        """Lower only through the certified typed relation constructor."""
        return RepeatAmplifyTemplate().instantiate(
            instance_id=instance_id,
            lane=self.lane,
            token=self.token,
            epoch=self.epoch,
            anchor=self.anchor,
            pad=self.pad,
            repeats=self.repeats,
            drain_between=True,
        )


type TypedCandidate = QueryCandidate | RepeatAmplifyCandidate


@dataclass(frozen=True, slots=True)
class ScoredQuery:
    """Compatibility score used by the deterministic tutorial reference loop."""

    query: QueryCandidate
    outcome_partition: tuple[int, int, int]
    information_gain_bits: float
    static_cycles: int
    score: float


class GrammarGuidedSelector:
    """Finite exact selector retained as the deterministic M5 compatibility API."""

    def __init__(
        self,
        *,
        tokens: Iterable[int] = range(16),
        epochs: Iterable[int] = (0, 1),
        pads: Iterable[int] = range(4),
        repeats: Sequence[int] = (1,),
        cycle_penalty: float = 0.002,
    ) -> None:
        self._tokens = tuple(tokens)
        self._epochs = tuple(epochs)
        self._pads = tuple(pads)
        self._repeats = tuple(repeats)
        if self._repeats != (1,):
            raise ValueError("compatibility selector supports the certified one-cell skeleton")
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
            )
            for token in self._tokens
            for epoch in self._epochs
            for bank_a, bank_b in combinations(range(4), 2)
            for pad in self._pads
        )

    def score(self, candidate: QueryCandidate, domain: frozenset[int]) -> ScoredQuery:
        """Predict the exact three-way tutorial partition on a nibble domain."""
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
        static_cycles = candidate.pad + 12
        score = gain - self._cycle_penalty * static_cycles
        return ScoredQuery(candidate, partition, gain, static_cycles, score)

    def choose(
        self,
        domain: SecretDomain,
        *,
        used: Iterable[QueryCandidate] = (),
    ) -> ScoredQuery | None:
        """Choose the highest-scoring novel assignment with a stable tie-break."""
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
                if best is None or (scored.score, _reverse_key(candidate.canonical_key())) > (
                    best.score,
                    _reverse_key(best.query.canonical_key()),
                ):
                    best = scored
        return best


class SkeletonKind(StrEnum):
    """Version-1 bounded high-level relation productions."""

    ANCHOR_SWITCH = "anchor-switch"
    REPEAT_AMPLIFY = "repeat-amplify"


class HoleSort(StrEnum):
    """Finite semantic sorts used by grammar holes."""

    LANE = "lane"
    NIBBLE = "nibble"
    EPOCH = "epoch"
    BANK = "bank"
    PAD = "pad"
    COUNT = "count"


@dataclass(frozen=True, slots=True)
class TypedHole:
    """One finite, named, typed grammar hole."""

    name: str
    sort: HoleSort
    values: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.values:
            raise ValueError("typed holes require a name and finite domain")
        if tuple(sorted(set(self.values))) != self.values:
            raise ValueError("typed-hole values must be sorted and unique")


@dataclass(frozen=True, slots=True)
class RelationSkeleton:
    """One bounded high-level production whose holes are filled by SMT."""

    kind: SkeletonKind
    version: str
    holes: tuple[TypedHole, ...]

    def __post_init__(self) -> None:
        if self.version != _GRAMMAR_VERSION:
            raise ValueError("unknown relation skeleton version")
        names = tuple(hole.name for hole in self.holes)
        if len(set(names)) != len(names):
            raise ValueError("relation skeleton contains duplicate hole names")


@dataclass(frozen=True, slots=True)
class ResourceBounds:
    """Hard public candidate limits applied before solver scoring."""

    combined_static_cycles: int = 512
    combined_instructions: int = 128
    physical_executions: int = 2
    hard_resets: int = 2

    def __post_init__(self) -> None:
        if (
            min(
                self.combined_static_cycles,
                self.combined_instructions,
                self.physical_executions,
                self.hard_resets,
            )
            < 1
        ):
            raise ValueError("synthesis resource bounds must be positive")


@dataclass(frozen=True, slots=True)
class CandidateResources:
    """Exact public resources of both arms of one candidate relation."""

    combined_static_cycles: int
    combined_instructions: int
    physical_executions: int = 2
    hard_resets: int = 2


class BoundedRelationGrammar:
    """Deterministically enumerate typed skeletons and resource-safe assignments."""

    def __init__(
        self,
        *,
        lanes: Iterable[int] = range(4),
        tokens: Iterable[int] = range(16),
        epochs: Iterable[int] = (0, 1),
        pads: Iterable[int] = range(4),
        repeat_counts: Iterable[int] = (2, 4, 8, 16),
        include_anchor_switch: bool = True,
        include_repeat_amplify: bool = True,
        resources: ResourceBounds | None = None,
        version: str = _GRAMMAR_VERSION,
    ) -> None:
        self.lanes = _finite_values(lanes, 0, None, "lanes")
        self.tokens = _finite_values(tokens, 0, 15, "tokens")
        self.epochs = _finite_values(epochs, 0, 1, "epochs")
        self.pads = _finite_values(pads, 0, 65_535, "pads")
        self.repeat_counts = _finite_values(repeat_counts, 2, 16, "repeat_counts")
        if not include_anchor_switch and not include_repeat_amplify:
            raise ValueError("grammar must enable at least one relation skeleton")
        self.include_anchor_switch = include_anchor_switch
        self.include_repeat_amplify = include_repeat_amplify
        self.resources = ResourceBounds() if resources is None else resources
        self.version = version
        if version != _GRAMMAR_VERSION:
            raise ValueError("unknown grammar version")

    def skeletons(self) -> tuple[RelationSkeleton, ...]:
        """Return enabled bounded productions in stable grammar order."""
        shared = (
            TypedHole("lane", HoleSort.LANE, self.lanes),
            TypedHole("token", HoleSort.NIBBLE, self.tokens),
            TypedHole("epoch", HoleSort.EPOCH, self.epochs),
        )
        skeletons: list[RelationSkeleton] = []
        if self.include_anchor_switch:
            skeletons.append(
                RelationSkeleton(
                    SkeletonKind.ANCHOR_SWITCH,
                    self.version,
                    (
                        *shared,
                        TypedHole("bank_a", HoleSort.BANK, (0, 1, 2, 3)),
                        TypedHole("bank_b", HoleSort.BANK, (0, 1, 2, 3)),
                        TypedHole("pad", HoleSort.PAD, self.pads),
                    ),
                )
            )
        if self.include_repeat_amplify:
            skeletons.append(
                RelationSkeleton(
                    SkeletonKind.REPEAT_AMPLIFY,
                    self.version,
                    (
                        *shared,
                        TypedHole("anchor", HoleSort.BANK, (0, 1, 2, 3)),
                        TypedHole("pad", HoleSort.PAD, self.pads),
                        TypedHole("repeats", HoleSort.COUNT, self.repeat_counts),
                    ),
                )
            )
        return tuple(skeletons)

    def enumerate(self, skeleton: RelationSkeleton) -> tuple[TypedCandidate, ...]:
        """Boundedly enumerate assignments, lowering each through typed constructors."""
        if skeleton not in self.skeletons():
            raise ValueError("skeleton does not belong to this grammar")
        domains = {hole.name: hole.values for hole in skeleton.holes}
        candidates: list[TypedCandidate] = []
        if skeleton.kind is SkeletonKind.ANCHOR_SWITCH:
            for lane, token, epoch, bank_a, bank_b, pad in product(
                domains["lane"],
                domains["token"],
                domains["epoch"],
                domains["bank_a"],
                domains["bank_b"],
                domains["pad"],
            ):
                if bank_a >= bank_b:
                    continue
                candidates.append(QueryCandidate(lane, token, epoch, bank_a, bank_b, pad))
        else:
            for lane, token, epoch, anchor, pad, repeats in product(
                domains["lane"],
                domains["token"],
                domains["epoch"],
                domains["anchor"],
                domains["pad"],
                domains["repeats"],
            ):
                candidates.append(RepeatAmplifyCandidate(lane, token, epoch, anchor, pad, repeats))
        return tuple(
            candidate
            for candidate in candidates
            if _within_resources(candidate_resources(candidate), self.resources)
        )

    def all_candidates(self) -> tuple[TypedCandidate, ...]:
        """Enumerate the complete bounded grammar with canonical de-duplication."""
        candidates = {
            candidate.canonical_key(): candidate
            for skeleton in self.skeletons()
            for candidate in self.enumerate(skeleton)
        }
        return tuple(candidates[key] for key in sorted(candidates))


@dataclass(frozen=True, slots=True)
class SynthesisModel:
    """One public-family secret/fault/state hypothesis used by synthesis."""

    model_id: str
    secret: tuple[int, ...]
    fault_variant: FaultVariant = FaultVariant.REFERENCE
    state: MicroState = field(default_factory=MicroState)

    def __post_init__(self) -> None:
        if not self.model_id or not self.secret:
            raise ValueError("synthesis models require an ID and ordered secret cells")
        for value in self.secret:
            _bounded(value, 0, 15, "secret cell")

    @classmethod
    def from_assignment(
        cls,
        assignment: ModelAssignment,
        *,
        secret_cells: int,
        model_id: str,
        default_fault: FaultVariant = FaultVariant.REFERENCE,
    ) -> SynthesisModel:
        """Decode a solver-independent model without reading target-private state."""
        values = []
        for lane in range(secret_cells):
            value = assignment.get(f"secret_{lane}")
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("solver secret assignment is not an integer nibble")
            values.append(value)
        try:
            raw_fault = assignment.get("fault_variant")
        except KeyError:
            fault = default_fault
        else:
            if not isinstance(raw_fault, str):
                raise ValueError("solver fault assignment is not a finite-domain string")
            fault = FaultVariant(raw_fault)
        return cls(model_id, tuple(values), fault)


@dataclass(frozen=True, slots=True)
class DiverseCommittee:
    """Deterministic diverse models with an explicit completeness label."""

    models: tuple[SynthesisModel, ...]
    complete: bool
    source: str

    def __post_init__(self) -> None:
        if len(self.models) < 2:
            raise ValueError("a synthesis committee requires at least two models")
        identifiers = tuple(model.model_id for model in self.models)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("committee model IDs must be unique")
        widths = {len(model.secret) for model in self.models}
        if len(widths) != 1:
            raise ValueError("committee models disagree on secret width")

    @classmethod
    def select(
        cls,
        models: Iterable[SynthesisModel],
        *,
        limit: int,
        complete: bool,
        source: str = "explicit-models",
    ) -> DiverseCommittee:
        """Greedily maximize secret/fault/state Hamming distance with stable ties."""
        pool = sorted(set(models), key=lambda model: model.model_id)
        if limit < 2 or len(pool) < 2:
            raise ValueError("committee limit and model pool must contain at least two models")
        selected = [pool.pop(0)]
        while pool and len(selected) < limit:
            chosen = max(
                pool,
                key=lambda model: (
                    min(_model_distance(model, prior) for prior in selected),
                    _reverse_key(model.model_id),
                ),
            )
            selected.append(chosen)
            pool.remove(chosen)
        return cls(tuple(selected), complete and not pool, source)

    @classmethod
    def from_store(
        cls,
        store: HypothesisStore,
        *,
        secret_cells: int,
        limit: int,
        pool_limit: int = 256,
    ) -> DiverseCommittee:
        """Use the exact solver's bounded diverse-model API as committee input."""
        enumerated = store.diverse_models(limit=limit, pool_limit=pool_limit)
        if len(enumerated.models) < 2:
            raise ValueError("hypothesis store contains fewer than two synthesis models")
        models = tuple(
            SynthesisModel.from_assignment(
                assignment,
                secret_cells=secret_cells,
                model_id=f"solver-{index:04d}",
            )
            for index, assignment in enumerate(enumerated.models)
        )
        return cls(models, enumerated.complete, "hypothesis-store-diverse-models")

    def fingerprint(self) -> str:
        """Hash only public hypothesis values and the sampling/completeness label."""
        data = {
            "complete": self.complete,
            "source": self.source,
            "models": [
                {
                    "id": model.model_id,
                    "secret": list(model.secret),
                    "fault": model.fault_variant.value,
                    "state": _state_data(model.state),
                }
                for model in self.models
            ],
        }
        return _digest(data)


@dataclass(frozen=True, slots=True)
class SignatureInterval:
    """Predicted normalized relation signature and conservative nuisance interval."""

    center: int
    lower: int
    upper: int

    def __post_init__(self) -> None:
        if self.lower > self.center or self.center > self.upper:
            raise ValueError("signature center must lie inside its interval")


@dataclass(frozen=True, slots=True)
class SynthesisContext:
    """Versioned profile/hypothesis/objective inputs that define one cache key."""

    hypothesis_fingerprint: str
    profile_name: str = "tutorial"
    semantic_version: str = "0.1.0"
    state_model_version: str = "hard-reset/v1"
    certificate_policy: str = "exhaustive-enumeration"
    bucket_width: int = 1
    noise_bound: int = 0
    minimum_pair_margin: int = 0
    maximum_bucket_size: int | None = None
    max_cegis_iterations: int = 16
    solver_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if not self.hypothesis_fingerprint:
            raise ValueError("synthesis context requires a hypothesis fingerprint")
        if not self.profile_name or not self.semantic_version or not self.state_model_version:
            raise ValueError("synthesis context versions must not be empty")
        if self.bucket_width < 1 or self.noise_bound < 0 or self.minimum_pair_margin < 0:
            raise ValueError("invalid observation interval configuration")
        if self.maximum_bucket_size is not None and self.maximum_bucket_size < 1:
            raise ValueError("maximum bucket size must be positive")
        if self.max_cegis_iterations < 1 or self.solver_timeout_ms < 1:
            raise ValueError("synthesis bounds/timeouts must be positive")


@dataclass(frozen=True, slots=True)
class CounterexamplePair:
    """Two surviving models that a refined hole assignment must separate."""

    left_model_id: str
    right_model_id: str
    source_bucket_size: int

    def __post_init__(self) -> None:
        if not self.left_model_id or not self.right_model_id:
            raise ValueError("counterexample model IDs must not be empty")
        if self.left_model_id >= self.right_model_id:
            raise ValueError("counterexample model IDs must be canonical and distinct")
        if self.source_bucket_size < 2:
            raise ValueError("counterexamples require an oversized/unseparated bucket")


@dataclass(frozen=True, slots=True)
class SynthesisScore:
    """Auditable lexicographic committee partition proxy and public resources."""

    candidate: TypedCandidate
    partition_sizes: tuple[int, ...]
    worst_bucket_size: int
    minimum_margin: int
    partition_score_bits: float
    partition_score_kind: str
    committee_size: int
    resources: CandidateResources
    canonical_tie_break: str

    def __post_init__(self) -> None:
        if self.partition_score_kind not in {"exact-information", "committee-proxy"}:
            raise ValueError("partition score must state whether it is exact or a proxy")
        if sum(self.partition_sizes) != self.committee_size:
            raise ValueError("partition sizes do not cover the committee")

    def objective_key(self) -> tuple[int, int, int, int, int, int, str]:
        """Return the documented deterministic lexicographic minimization key."""
        return (
            self.worst_bucket_size,
            -self.minimum_margin,
            self.resources.physical_executions,
            self.resources.hard_resets,
            self.resources.combined_static_cycles,
            self.resources.combined_instructions,
            self.canonical_tie_break,
        )

    def to_data(self) -> dict[str, object]:
        """Return persistence-safe logged score components."""
        return {
            "partition_sizes": list(self.partition_sizes),
            "worst_bucket_size": self.worst_bucket_size,
            "minimum_margin": self.minimum_margin,
            "partition_score_bits": self.partition_score_bits,
            "partition_score_kind": self.partition_score_kind,
            "committee_size": self.committee_size,
            "physical_executions": self.resources.physical_executions,
            "hard_resets": self.resources.hard_resets,
            "combined_static_cycles": self.resources.combined_static_cycles,
            "combined_instructions": self.resources.combined_instructions,
            "canonical_tie_break": self.canonical_tie_break,
        }


class SynthesisStatus(StrEnum):
    """Honest bounded synthesis outcomes."""

    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HoleFillResult:
    """One bounded SMT hole-filling check."""

    status: SynthesisStatus
    candidate: TypedCandidate | None
    reason: str | None = None


class HoleFiller(Protocol):
    """Injectable bounded hole solver used by the CEGIS driver."""

    def fill(
        self,
        skeleton: RelationSkeleton,
        candidates: Sequence[TypedCandidate],
        requirements: Sequence[CounterexamplePair],
        models: Mapping[str, SynthesisModel],
        context: SynthesisContext,
    ) -> HoleFillResult:
        """Return one resource-minimal assignment satisfying all current pairs."""
        ...


class SmtHoleFiller:
    """Fill named finite holes in Z3 using a concrete public signature truth table."""

    def fill(
        self,
        skeleton: RelationSkeleton,
        candidates: Sequence[TypedCandidate],
        requirements: Sequence[CounterexamplePair],
        models: Mapping[str, SynthesisModel],
        context: SynthesisContext,
    ) -> HoleFillResult:
        """Solve finite typed holes with lexicographic resource objectives."""
        if not candidates:
            return HoleFillResult(SynthesisStatus.UNSAT, None, "skeleton has no bounded candidates")
        admissible = [
            candidate
            for candidate in candidates
            if all(
                _separates(
                    candidate,
                    models[requirement.left_model_id],
                    models[requirement.right_model_id],
                    context,
                )
                for requirement in requirements
            )
        ]
        if not admissible:
            return HoleFillResult(
                SynthesisStatus.UNSAT,
                None,
                "no bounded hole assignment separates every required model pair",
            )

        optimizer = z3.Optimize()
        optimizer.set(timeout=context.solver_timeout_ms, priority="lex")
        variables = {
            hole.name: z3.Int(f"{skeleton.kind.value}_{hole.name}") for hole in skeleton.holes
        }
        for hole in skeleton.holes:
            optimizer.add(z3.Or(*(variables[hole.name] == value for value in hole.values)))
        patterns = tuple(_assignment_pattern(candidate, variables) for candidate in admissible)
        optimizer.add(z3.Or(*patterns))
        resources = tuple(candidate_resources(candidate) for candidate in admissible)
        optimizer.minimize(
            z3.Sum(
                *(
                    z3.If(pattern, resource.combined_static_cycles, 0)
                    for pattern, resource in zip(patterns, resources, strict=True)
                )
            )
        )
        optimizer.minimize(
            z3.Sum(
                *(
                    z3.If(pattern, resource.combined_instructions, 0)
                    for pattern, resource in zip(patterns, resources, strict=True)
                )
            )
        )
        ranked = sorted(admissible, key=lambda candidate: candidate.canonical_key())
        rank_by_key = {candidate.canonical_key(): rank for rank, candidate in enumerate(ranked)}
        optimizer.minimize(
            z3.Sum(
                *(
                    z3.If(pattern, rank_by_key[candidate.canonical_key()], 0)
                    for pattern, candidate in zip(patterns, admissible, strict=True)
                )
            )
        )
        checked = optimizer.check()
        if checked == z3.unknown:
            return HoleFillResult(SynthesisStatus.UNKNOWN, None, optimizer.reason_unknown())
        if checked == z3.unsat:
            return HoleFillResult(SynthesisStatus.UNSAT, None, "SMT hole constraints are unsat")
        model = optimizer.model()
        assignment = {
            name: model.eval(variable, model_completion=True).as_long()
            for name, variable in variables.items()
        }
        matches = [
            candidate for candidate in admissible if dict(candidate.hole_values()) == assignment
        ]
        if len(matches) != 1:
            raise RuntimeError("SMT hole assignment did not lower to exactly one candidate")
        return HoleFillResult(SynthesisStatus.SAT, matches[0])


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """Complete bounded CEGIS outcome, cache label, and verification trace."""

    status: SynthesisStatus
    score: SynthesisScore | None
    iterations: int
    counterexamples: tuple[CounterexamplePair, ...]
    verification_complete: bool
    cache_hit: bool
    reason: str
    context: SynthesisContext
    committee_fingerprint: str
    grammar_version: str = _GRAMMAR_VERSION

    def to_data(self) -> dict[str, object]:
        """Return an auditable representation suitable for frontier persistence."""
        return {
            "status": self.status.value,
            "iterations": self.iterations,
            "counterexamples": [
                {
                    "left_model_id": item.left_model_id,
                    "right_model_id": item.right_model_id,
                    "source_bucket_size": item.source_bucket_size,
                }
                for item in self.counterexamples
            ],
            "verification_complete": self.verification_complete,
            "cache_hit": self.cache_hit,
            "reason": self.reason,
            "committee_fingerprint": self.committee_fingerprint,
            "grammar_version": self.grammar_version,
            "score": None if self.score is None else self.score.to_data(),
        }

    def frontier_candidate(
        self,
        *,
        candidate_id: str | None = None,
        expires_after: int | None = None,
    ) -> FrontierCandidate:
        """Adapt a successful synthesis result to the persistent M4 frontier."""
        if self.status is not SynthesisStatus.SAT or self.score is None:
            raise ValueError("only successful synthesis results can enter the frontier")
        relation = self.score.candidate.lower("synthesis-frontier")
        canonical = self.score.canonical_tie_break
        resolved_id = candidate_id or f"synth-{hashlib.sha256(canonical.encode()).hexdigest()[:20]}"
        partition_key = _digest(
            {
                "committee": self.committee_fingerprint,
                "sizes": list(self.score.partition_sizes),
                "kind": self.score.partition_score_kind,
            }
        )
        frontier_score = (
            self.score.partition_score_bits
            + self.score.minimum_margin * 0.01
            - self.score.worst_bucket_size
            - self.score.resources.combined_static_cycles * 0.000_001
        )
        return FrontierCandidate(
            candidate_id=resolved_id,
            structural_key=relation.instance_hash,
            relation_key=relation.relation_id,
            state_key=self.context.state_model_version,
            observation_key=(
                f"bucket:{self.context.bucket_width}:noise:{self.context.noise_bound}:"
                f"margin:{self.context.minimum_pair_margin}"
            ),
            partition_key=partition_key,
            semantic_key=canonical,
            score=frontier_score,
            data={
                "candidate": dict(self.score.candidate.hole_values()),
                "candidate_kind": self.score.candidate.skeleton_kind.value,
                "relation": relation.to_data(),
                "synthesis": self.to_data(),
            },
            expires_after=expires_after,
        )


class CegisSynthesizer:
    """Synthesize, verify on a committee, refine by pairs, and cache the result."""

    def __init__(
        self,
        grammar: BoundedRelationGrammar | None = None,
        *,
        hole_filler: HoleFiller | None = None,
    ) -> None:
        self.grammar = BoundedRelationGrammar() if grammar is None else grammar
        self.hole_filler = SmtHoleFiller() if hole_filler is None else hole_filler
        self._cache: dict[str, SynthesisResult] = {}

    def synthesize(
        self,
        committee: DiverseCommittee,
        context: SynthesisContext,
    ) -> SynthesisResult:
        """Run bounded pair-separating CEGIS with deterministic committee checks."""
        cache_key = _digest(
            {
                "hypothesis": context.hypothesis_fingerprint,
                "profile": context.profile_name,
                "semantic": context.semantic_version,
                "state_model": context.state_model_version,
                "grammar": self.grammar.version,
                "certificate_policy": context.certificate_policy,
                "bucket_width": context.bucket_width,
                "noise_bound": context.noise_bound,
                "minimum_pair_margin": context.minimum_pair_margin,
                "maximum_bucket_size": context.maximum_bucket_size,
                "committee": committee.fingerprint(),
                "resources": self.grammar.resources.__dict__
                if hasattr(self.grammar.resources, "__dict__")
                else {
                    "combined_static_cycles": self.grammar.resources.combined_static_cycles,
                    "combined_instructions": self.grammar.resources.combined_instructions,
                    "physical_executions": self.grammar.resources.physical_executions,
                    "hard_resets": self.grammar.resources.hard_resets,
                },
            }
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return replace(cached, cache_hit=True)

        models = {model.model_id: model for model in committee.models}
        initial_left, initial_right = _farthest_pair(committee.models)
        requirements = [_counterexample(initial_left, initial_right, len(committee.models))]
        proposals: list[SynthesisScore] = []
        last_reason = "bounded grammar was not attempted"
        saw_unknown = False
        limit = context.maximum_bucket_size
        if limit is None:
            limit = max(1, math.ceil(len(committee.models) / 2))

        for iteration in range(1, context.max_cegis_iterations + 1):
            fills: list[HoleFillResult] = []
            candidate_sets: list[tuple[TypedCandidate, ...]] = []
            for skeleton in self.grammar.skeletons():
                bounded_candidates = self.grammar.enumerate(skeleton)
                fill = self.hole_filler.fill(
                    skeleton,
                    bounded_candidates,
                    requirements,
                    models,
                    context,
                )
                fills.append(fill)
                candidate_sets.append(bounded_candidates)
            candidates = [
                candidate
                for fill, bounded_candidates in zip(fills, candidate_sets, strict=True)
                if fill.status is SynthesisStatus.SAT
                for candidate in bounded_candidates
                if all(
                    _separates(
                        candidate,
                        models[requirement.left_model_id],
                        models[requirement.right_model_id],
                        context,
                    )
                    for requirement in requirements
                )
            ]
            saw_unknown = saw_unknown or any(
                fill.status is SynthesisStatus.UNKNOWN for fill in fills
            )
            if not candidates:
                if proposals:
                    result = SynthesisResult(
                        SynthesisStatus.UNKNOWN if saw_unknown else SynthesisStatus.SAT,
                        min(proposals, key=lambda item: item.objective_key()),
                        iteration,
                        tuple(requirements[1:]),
                        False,
                        False,
                        "no further bounded assignment satisfies all refinements; "
                        "best verified proxy retained",
                        context,
                        committee.fingerprint(),
                    )
                else:
                    reasons = "; ".join(fill.reason for fill in fills if fill.reason is not None)
                    result = SynthesisResult(
                        SynthesisStatus.UNKNOWN if saw_unknown else SynthesisStatus.UNSAT,
                        None,
                        iteration,
                        (),
                        False,
                        False,
                        reasons or "no grammar discriminator exists",
                        context,
                        committee.fingerprint(),
                    )
                self._cache[cache_key] = result
                return result

            scored = [score_candidate(candidate, committee, context) for candidate in candidates]
            proposed = min(scored, key=lambda item: item.objective_key())
            proposals.append(proposed)
            buckets = _partition_models(proposed.candidate, committee.models, context)
            largest = min(
                (
                    bucket
                    for bucket in buckets.values()
                    if len(bucket) == proposed.worst_bucket_size
                ),
                key=lambda bucket: tuple(model.model_id for model in bucket),
            )
            if proposed.worst_bucket_size <= limit:
                result = SynthesisResult(
                    SynthesisStatus.SAT,
                    min(proposals, key=lambda item: item.objective_key()),
                    iteration,
                    tuple(requirements[1:]),
                    True,
                    False,
                    "committee partition meets the configured worst-bucket bound",
                    context,
                    committee.fingerprint(),
                )
                self._cache[cache_key] = result
                return result

            pair = _new_counterexample(largest, requirements)
            if pair is None:
                last_reason = "largest bucket contains no new counterexample pair"
                break
            requirements.append(pair)
            last_reason = "CEGIS added an unseparated pair from the largest bucket"

        result = SynthesisResult(
            SynthesisStatus.SAT if proposals else SynthesisStatus.UNKNOWN,
            None if not proposals else min(proposals, key=lambda item: item.objective_key()),
            min(context.max_cegis_iterations, max(1, len(proposals))),
            tuple(requirements[1:]),
            False,
            False,
            last_reason,
            context,
            committee.fingerprint(),
        )
        self._cache[cache_key] = result
        return result


def symbolic_signature(
    candidate: TypedCandidate,
    model: SynthesisModel,
    *,
    noise_bound: int,
    bucket_width: int,
) -> SignatureInterval:
    """Predict a normalized signature from the public hard-reset fault equations."""
    if candidate.lane >= len(model.secret):
        raise ValueError("candidate lane is absent from synthesis model")
    secret_bank = bank_of(model.secret[candidate.lane], candidate.token, candidate.epoch)
    active = candidate.pad % 4 == (candidate.lane ^ candidate.token ^ candidate.epoch) & 3
    enabled = model.fault_variant is not FaultVariant.OFF and active
    if isinstance(candidate, QueryCandidate):
        source = int(enabled and secret_bank == candidate.bank_a)
        follow_up = int(enabled and secret_bank == candidate.bank_b)
        center = source - follow_up
    else:
        collision = int(enabled and secret_bank == candidate.anchor)
        center = collision * (1 - candidate.repeats)
    radius = 2 * noise_bound + 2 * (bucket_width - 1)
    return SignatureInterval(center, center - radius, center + radius)


def concrete_signature(
    candidate: TypedCandidate,
    model: SynthesisModel,
    *,
    noise_bound: int,
    bucket_width: int,
) -> SignatureInterval:
    """Evaluate the lowered typed programs through the independent concrete model."""
    relation = candidate.lower("concrete-signature")
    secrets = dict(enumerate(model.secret))
    source = execute_experiment_program(
        relation.source_program,
        secrets,
        initial_state=MicroState(),
        variant=model.fault_variant,
    )
    follow_up = execute_experiment_program(
        relation.follow_up_programs[0],
        secrets,
        initial_state=MicroState(),
        variant=model.fault_variant,
    )
    center = source.fault_cycles - follow_up.fault_cycles
    radius = 2 * noise_bound + 2 * (bucket_width - 1)
    return SignatureInterval(center, center - radius, center + radius)


def score_candidate(
    candidate: TypedCandidate,
    committee: DiverseCommittee,
    context: SynthesisContext,
) -> SynthesisScore:
    """Score one typed candidate; sampled committees are labeled only as proxies."""
    buckets = _partition_models(candidate, committee.models, context)
    partition_sizes = tuple(sorted((len(bucket) for bucket in buckets.values()), reverse=True))
    signatures = {
        model.model_id: symbolic_signature(
            candidate,
            model,
            noise_bound=context.noise_bound,
            bucket_width=context.bucket_width,
        )
        for model in committee.models
    }
    separated_margins = [
        interval_distance(signatures[left.model_id], signatures[right.model_id])
        for left, right in combinations(committee.models, 2)
        if signatures[left.model_id].center != signatures[right.model_id].center
    ]
    minimum_margin = min(separated_margins, default=0)
    return SynthesisScore(
        candidate,
        partition_sizes,
        max(partition_sizes),
        minimum_margin,
        entropy_of_partition(partition_sizes),
        "exact-information" if committee.complete else "committee-proxy",
        len(committee.models),
        candidate_resources(candidate),
        candidate.canonical_key(),
    )


def candidate_resources(candidate: TypedCandidate) -> CandidateResources:
    """Compute exact public resources from the lowered typed AST pair."""
    relation = candidate.lower("synthesis-resource")
    programs = relation.programs
    return CandidateResources(
        combined_static_cycles=sum(program.resources().static_cycles for program in programs),
        combined_instructions=sum(program.resources().instructions for program in programs),
    )


def interval_distance(left: SignatureInterval, right: SignatureInterval) -> int:
    """Return zero for overlap, otherwise the exact closed-interval gap."""
    if left.upper < right.lower:
        return right.lower - left.upper
    if right.upper < left.lower:
        return left.lower - right.upper
    return 0


def entropy_of_partition(parts: Sequence[int]) -> float:
    """Return Shannon entropy of a finite exact/proxy outcome partition in bits."""
    total = sum(parts)
    if total <= 0:
        raise ValueError("partition must contain at least one hypothesis")
    entropy = 0.0
    for part in parts:
        if part:
            probability = part / total
            entropy -= probability * math.log2(probability)
    return entropy


def _partition_models(
    candidate: TypedCandidate,
    models: Sequence[SynthesisModel],
    context: SynthesisContext,
) -> dict[int, tuple[SynthesisModel, ...]]:
    grouped: dict[int, list[SynthesisModel]] = defaultdict(list)
    for model in models:
        signature = symbolic_signature(
            candidate,
            model,
            noise_bound=context.noise_bound,
            bucket_width=context.bucket_width,
        )
        grouped[signature.center].append(model)
    return {
        key: tuple(sorted(bucket, key=lambda model: model.model_id))
        for key, bucket in sorted(grouped.items())
    }


def _separates(
    candidate: TypedCandidate,
    left: SynthesisModel,
    right: SynthesisModel,
    context: SynthesisContext,
) -> bool:
    left_signature = symbolic_signature(
        candidate,
        left,
        noise_bound=context.noise_bound,
        bucket_width=context.bucket_width,
    )
    right_signature = symbolic_signature(
        candidate,
        right,
        noise_bound=context.noise_bound,
        bucket_width=context.bucket_width,
    )
    return (
        left_signature.center != right_signature.center
        and interval_distance(left_signature, right_signature) >= context.minimum_pair_margin
    )


def _assignment_pattern(
    candidate: TypedCandidate,
    variables: Mapping[str, z3.IntNumRef | z3.ArithRef],
) -> z3.BoolRef:
    values = candidate.hole_values()
    return z3.And(*(variables[name] == value for name, value in values.items()))


def _new_counterexample(
    bucket: Sequence[SynthesisModel],
    requirements: Sequence[CounterexamplePair],
) -> CounterexamplePair | None:
    used = {(requirement.left_model_id, requirement.right_model_id) for requirement in requirements}
    pairs = sorted(
        combinations(bucket, 2),
        key=lambda pair: (-_model_distance(*pair), pair[0].model_id, pair[1].model_id),
    )
    for left, right in pairs:
        identifiers = tuple(sorted((left.model_id, right.model_id)))
        if identifiers not in used:
            return CounterexamplePair(identifiers[0], identifiers[1], len(bucket))
    return None


def _counterexample(
    left: SynthesisModel,
    right: SynthesisModel,
    bucket_size: int,
) -> CounterexamplePair:
    identifiers = tuple(sorted((left.model_id, right.model_id)))
    return CounterexamplePair(identifiers[0], identifiers[1], bucket_size)


def _farthest_pair(models: Sequence[SynthesisModel]) -> tuple[SynthesisModel, SynthesisModel]:
    return min(
        combinations(models, 2),
        key=lambda pair: (-_model_distance(*pair), pair[0].model_id, pair[1].model_id),
    )


def _model_distance(left: SynthesisModel, right: SynthesisModel) -> int:
    secret = sum(a != b for a, b in zip(left.secret, right.secret, strict=True))
    fault = int(left.fault_variant is not right.fault_variant)
    state_left = tuple(_state_data(left.state).values())
    state_right = tuple(_state_data(right.state).values())
    return secret + fault + sum(a != b for a, b in zip(state_left, state_right, strict=True))


def _state_data(state: MicroState) -> dict[str, object]:
    return {
        "phase": state.phase,
        "last_bank": state.last_bank,
        "replay_credit": state.replay_credit,
        "uop_cache_tag": state.uop_cache_tag,
        "uop_cache_valid": state.uop_cache_valid,
        "pending_probe": None
        if state.pending_probe is None
        else {
            "bank": state.pending_probe.bank,
            "epoch": state.pending_probe.epoch,
            "guard": state.pending_probe.guard,
        },
    }


def _within_resources(actual: CandidateResources, bounds: ResourceBounds) -> bool:
    return (
        actual.combined_static_cycles <= bounds.combined_static_cycles
        and actual.combined_instructions <= bounds.combined_instructions
        and actual.physical_executions <= bounds.physical_executions
        and actual.hard_resets <= bounds.hard_resets
    )


def _finite_values(
    values: Iterable[int], minimum: int, maximum: int | None, role: str
) -> tuple[int, ...]:
    resolved = tuple(sorted(set(values)))
    if not resolved:
        raise ValueError(f"{role} must be a nonempty finite domain")
    for value in resolved:
        _bounded(value, minimum, maximum, role)
    return resolved


def _bounded(value: int, minimum: int, maximum: int | None, role: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{role} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        rendered = "unbounded" if maximum is None else str(maximum)
        raise ValueError(f"{role} is outside {minimum}..{rendered}")


def _digest(data: object) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _reverse_key(value: str) -> tuple[int, ...]:
    return tuple(-ord(character) for character in value)
