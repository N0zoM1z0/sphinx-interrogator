"""Relation-aware witness reduction over public relation families.

The reducer is deliberately conservative.  It never asks for target-private
state and never compares against a true challenge secret.  A candidate is
accepted only when it remains a typed/certified relation, lowers the declared
lexicographic cost, and preserves the configured consequence over a finite
public model committee.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from sphinx_interrogator.ast import Instruction, Op, Program
from sphinx_interrogator.relations import (
    AnchorSwitchTemplate,
    Cell,
    ContextLiftTemplate,
    EpochSwitchTemplate,
    HardReplayTemplate,
    IndependentSwapTemplate,
    PhaseShiftTemplate,
    RegisterRenameTemplate,
    RelationInstance,
    RepeatAmplifyTemplate,
    SoftHistoryContrastTemplate,
    TokenSwitchTemplate,
)
from sphinx_interrogator.target_model import (
    FaultVariant,
    MicroState,
    execute_experiment_program,
)

type _Signature = tuple[int, ...]
type _SignatureMap = tuple[tuple[str, _Signature], ...]


class ReductionMode(StrEnum):
    """Logical-consequence predicate used to accept reduced candidates."""

    EQUIVALENT = "equivalent"
    IMPLIES_CORE = "implies-core"
    SAME_PARTITION = "same-partition"


class SignatureKind(StrEnum):
    """Finite public signature abstraction used by the preservation predicate."""

    EXACT_RESIDUAL = "exact-residual"
    SIGN = "sign"
    ZERO_NONZERO = "zero-nonzero"


class ReductionKind(StrEnum):
    """Named reduction steps matching the documented reducer obligations."""

    SYMMETRIC_DELETION = "symmetric-deletion"
    REPEAT_SHRINK = "repeat-shrink"
    PADDING_SIMPLIFICATION = "padding-fence-simplification"
    TOKEN_ANCHOR_SIMPLIFICATION = "token-anchor-simplification"
    CONTEXT_HISTORY_SHORTENING = "context-history-shortening"
    RELATION_COMPOSITION_COLLAPSE = "relation-composition-collapse"


@dataclass(frozen=True, slots=True)
class PublicModel:
    """One public-family model used for finite consequence preservation."""

    model_id: str
    secret_by_lane: Mapping[int, int]
    variant: FaultVariant = FaultVariant.REFERENCE
    initial_state: MicroState | None = None
    salt_by_lane: Mapping[int, int] | None = None

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("public model ID must not be empty")
        object.__setattr__(self, "secret_by_lane", MappingProxyType(dict(self.secret_by_lane)))
        salts = None if self.salt_by_lane is None else MappingProxyType(dict(self.salt_by_lane))
        object.__setattr__(self, "salt_by_lane", salts)


@dataclass(frozen=True, order=True, slots=True)
class RelationCost:
    """Strict lexicographic cost used by the best-first reducer."""

    physical_executions: int
    static_cycles: int
    ast_nodes: int
    history_length: int
    lexical_key: str

    def to_data(self) -> dict[str, object]:
        """Return a stable report representation."""
        return {
            "physical_executions": self.physical_executions,
            "static_cycles": self.static_cycles,
            "ast_nodes": self.ast_nodes,
            "history_length": self.history_length,
            "lexical_key": self.lexical_key,
        }


@dataclass(frozen=True, slots=True)
class ReductionConfig:
    """Bounded public configuration for one reducer run."""

    mode: ReductionMode = ReductionMode.IMPLIES_CORE
    signature_kind: SignatureKind = SignatureKind.SIGN
    max_predicate_evaluations: int = 512
    max_generated_candidates: int = 2_048

    def __post_init__(self) -> None:
        if self.max_predicate_evaluations <= 0 or self.max_generated_candidates <= 0:
            raise ValueError("reducer budgets must be positive")


@dataclass(frozen=True, slots=True)
class ReductionStep:
    """One accepted cost-decreasing transformation."""

    kind: ReductionKind
    from_hash: str
    to_hash: str
    from_cost: RelationCost
    to_cost: RelationCost
    reason: str

    def to_data(self) -> dict[str, object]:
        """Return a stable report representation."""
        return {
            "kind": self.kind.value,
            "from_hash": self.from_hash,
            "to_hash": self.to_hash,
            "from_cost": self.from_cost.to_data(),
            "to_cost": self.to_cost.to_data(),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ReductionResult:
    """Complete result of minimizing one relation witness."""

    status: str
    original_relation: RelationInstance
    reduced_relation: RelationInstance
    mode: ReductionMode
    signature_kind: SignatureKind
    original_cost: RelationCost
    reduced_cost: RelationCost
    steps: tuple[ReductionStep, ...]
    predicate_evaluations: int
    cache_hits: int
    generated_candidates: int
    elapsed_ms: int
    model_count: int
    blocked_reasons: tuple[str, ...] = ()

    @property
    def improved(self) -> bool:
        """Return whether any accepted step reduced cost."""
        return self.reduced_cost < self.original_cost

    def to_data(self) -> dict[str, object]:
        """Return a stable machine-readable witness document."""
        return {
            "reducer_version": "1.0",
            "status": self.status,
            "preservation": {
                "mode": self.mode.value,
                "signature_kind": self.signature_kind.value,
                "model_scope": "finite-public-family-committee",
                "model_count": self.model_count,
                "uses_true_secret": False,
            },
            "original": {
                "relation": self.original_relation.to_data(),
                "cost": self.original_cost.to_data(),
                "programs": _programs_data(self.original_relation),
            },
            "reduced": {
                "relation": self.reduced_relation.to_data(),
                "cost": self.reduced_cost.to_data(),
                "programs": _programs_data(self.reduced_relation),
            },
            "steps": [step.to_data() for step in self.steps],
            "metrics": {
                "predicate_evaluations": self.predicate_evaluations,
                "cache_hits": self.cache_hits,
                "generated_candidates": self.generated_candidates,
                "elapsed_ms": self.elapsed_ms,
            },
            "blocked_reasons": list(self.blocked_reasons),
        }


class RelationReducer:
    """Best-first reducer for typed relation instances."""

    def __init__(
        self,
        *,
        models: Sequence[PublicModel],
        known_relations: Mapping[str, RelationInstance] | None = None,
        config: ReductionConfig | None = None,
    ) -> None:
        if not models:
            raise ValueError("reducer requires at least one public model")
        self.models = tuple(models)
        self.known_relations = {} if known_relations is None else dict(known_relations)
        self.config = ReductionConfig() if config is None else config
        self._signature_cache: dict[tuple[str, SignatureKind], _SignatureMap] = {}
        self._predicate_cache: dict[str, bool] = {}
        self.cache_hits = 0
        self.predicate_evaluations = 0
        self.generated_candidates = 0
        self.blocked_reasons: list[str] = []

    def reduce(self, relation: RelationInstance) -> ReductionResult:
        """Minimize a relation while preserving the configured consequence."""
        start = time.monotonic()
        self.cache_hits = 0
        self.predicate_evaluations = 0
        self.generated_candidates = 0
        self.blocked_reasons = []
        original_signature = self._signature(relation)
        original_cost = relation_cost(relation)
        best = relation
        best_cost = original_cost
        steps: list[ReductionStep] = []
        pending: deque[RelationInstance] = deque([relation])
        seen = {relation.instance_hash}

        while pending and self.generated_candidates < self.config.max_generated_candidates:
            current = pending.popleft()
            candidates = sorted(
                self._neighbors(current),
                key=lambda item: (relation_cost(item[1]), item[1].instance_hash),
            )
            for kind, candidate, reason in candidates:
                if self.generated_candidates >= self.config.max_generated_candidates:
                    break
                self.generated_candidates += 1
                if candidate.instance_hash in seen:
                    continue
                seen.add(candidate.instance_hash)
                candidate_cost = relation_cost(candidate)
                current_cost = relation_cost(current)
                if candidate_cost >= current_cost:
                    self.blocked_reasons.append(f"{kind.value}: rejected non-improving cost")
                    continue
                if not candidate.architectural_precheck() or not candidate.fault_free_precheck():
                    self.blocked_reasons.append(f"{kind.value}: certificate precheck failed")
                    continue
                if not self._preserves(relation, original_signature, candidate):
                    self.blocked_reasons.append(f"{kind.value}: consequence predicate failed")
                    continue
                steps.append(
                    ReductionStep(
                        kind=kind,
                        from_hash=current.instance_hash,
                        to_hash=candidate.instance_hash,
                        from_cost=current_cost,
                        to_cost=candidate_cost,
                        reason=reason,
                    )
                )
                pending.append(candidate)
                if candidate_cost < best_cost:
                    best = candidate
                    best_cost = candidate_cost
                if self.predicate_evaluations >= self.config.max_predicate_evaluations:
                    self.blocked_reasons.append("predicate evaluation budget exhausted")
                    pending.clear()
                    break

        elapsed_ms = int((time.monotonic() - start) * 1000)
        status = "minimized" if best_cost < original_cost else "unchanged"
        return ReductionResult(
            status=status,
            original_relation=relation,
            reduced_relation=best,
            mode=self.config.mode,
            signature_kind=self.config.signature_kind,
            original_cost=original_cost,
            reduced_cost=best_cost,
            steps=tuple(steps),
            predicate_evaluations=self.predicate_evaluations,
            cache_hits=self.cache_hits,
            generated_candidates=self.generated_candidates,
            elapsed_ms=elapsed_ms,
            model_count=len(self.models),
            blocked_reasons=tuple(dict.fromkeys(self.blocked_reasons)),
        )

    def _preserves(
        self,
        original: RelationInstance,
        original_signature: _SignatureMap,
        candidate: RelationInstance,
    ) -> bool:
        key = _predicate_key(original, candidate, self.config)
        cached = self._predicate_cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        if self.predicate_evaluations >= self.config.max_predicate_evaluations:
            return False
        self.predicate_evaluations += 1
        candidate_signature = self._signature(candidate)
        if self.config.mode in {ReductionMode.EQUIVALENT, ReductionMode.SAME_PARTITION}:
            result = candidate_signature == original_signature
        else:
            result = _partition_refines(candidate_signature, original_signature)
        self._predicate_cache[key] = result
        return result

    def _signature(self, relation: RelationInstance) -> _SignatureMap:
        key = (relation.instance_hash, self.config.signature_kind)
        cached = self._signature_cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        signatures: list[tuple[str, _Signature]] = []
        for model in self.models:
            source = execute_experiment_program(
                relation.source_program,
                model.secret_by_lane,
                initial_state=model.initial_state,
                variant=model.variant,
                salt_by_lane=model.salt_by_lane,
            )
            deltas: list[int] = []
            for follow_up in relation.follow_up_programs:
                observed = execute_experiment_program(
                    follow_up,
                    model.secret_by_lane,
                    initial_state=model.initial_state,
                    variant=model.variant,
                    salt_by_lane=model.salt_by_lane,
                )
                deltas.append(observed.fault_cycles - source.fault_cycles)
            signatures.append(
                (model.model_id, _abstract_signature(deltas, self.config.signature_kind))
            )
        value = tuple(signatures)
        self._signature_cache[key] = value
        return value

    def _neighbors(
        self, relation: RelationInstance
    ) -> tuple[tuple[ReductionKind, RelationInstance, str], ...]:
        try:
            return tuple(_candidate for _candidate in self._iter_neighbors(relation))
        except (TypeError, ValueError) as error:
            self.blocked_reasons.append(
                f"{relation.relation_id}: candidate generation failed: {error}"
            )
            return ()

    def _iter_neighbors(
        self, relation: RelationInstance
    ) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
        relation_id = relation.relation_id
        if relation_id == AnchorSwitchTemplate.relation_id:
            yield from _anchor_neighbors(relation)
        elif relation_id == TokenSwitchTemplate.relation_id:
            yield from _token_neighbors(relation)
        elif relation_id == EpochSwitchTemplate.relation_id:
            yield from _epoch_neighbors(relation)
        elif relation_id == PhaseShiftTemplate.relation_id:
            yield from _phase_neighbors(relation)
        elif relation_id == RepeatAmplifyTemplate.relation_id:
            yield from _repeat_neighbors(relation)
        elif relation_id == IndependentSwapTemplate.relation_id:
            yield from _swap_neighbors(relation)
        elif relation_id == ContextLiftTemplate.relation_id:
            yield from _context_neighbors(relation, self.known_relations)
        elif relation_id == RegisterRenameTemplate.relation_id:
            yield from _register_neighbors(relation)
        elif relation_id == HardReplayTemplate.relation_id:
            yield from _hard_replay_neighbors(relation)
        elif relation_id == SoftHistoryContrastTemplate.relation_id:
            yield from _soft_history_neighbors(relation, self.known_relations)
        else:
            self.blocked_reasons.append(f"{relation_id}: no reducer rules registered")


def default_model_committee(
    lanes: Sequence[int],
    *,
    fault_variants: Sequence[FaultVariant] = (
        FaultVariant.OFF,
        FaultVariant.REFERENCE,
        FaultVariant.WEAK,
        FaultVariant.SIGNED,
    ),
    secrets: Sequence[int] = tuple(range(16)),
) -> tuple[PublicModel, ...]:
    """Build a deterministic public finite committee for the declared lanes."""
    unique_lanes = tuple(sorted(set(lanes)))
    if not unique_lanes:
        return tuple(
            PublicModel(f"variant={variant.value}", {}, variant=variant)
            for variant in fault_variants
        )
    assignments = _lane_assignments(unique_lanes, tuple(secrets))
    models: list[PublicModel] = []
    for variant in fault_variants:
        for assignment in assignments:
            name = ",".join(f"l{lane}={secret:x}" for lane, secret in assignment.items())
            models.append(
                PublicModel(
                    f"{name};variant={variant.value}",
                    assignment,
                    variant=variant,
                )
            )
    return tuple(models)


def relation_cost(relation: RelationInstance) -> RelationCost:
    """Compute the documented lexicographic relation cost."""
    programs = relation.programs
    return RelationCost(
        physical_executions=len(programs),
        static_cycles=sum(program.static_cycles() for program in programs),
        ast_nodes=sum(len(program.instructions) for program in programs),
        history_length=_history_length(relation),
        lexical_key="|".join(program.render() for program in programs),
    )


def report_digest(data: Mapping[str, object]) -> str:
    """Hash a reducer report using canonical JSON."""
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _anchor_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    repeats = _int_hole(holes, "repeats")
    pad = _int_hole(holes, "pad")
    if repeats > 1:
        yield (
            ReductionKind.REPEAT_SHRINK,
            AnchorSwitchTemplate().instantiate(
                instance_id=_child_id(relation, "repeat", repeats - 1),
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch=_int_hole(holes, "epoch"),
                bank_a=_int_hole(holes, "bank_a"),
                bank_b=_int_hole(holes, "bank_b"),
                pad=pad,
                repeats=repeats - 1,
            ),
            "lower repeated source/follow-up cells by one",
        )
    if (reduced_pad := pad % 4) != pad:
        yield (
            ReductionKind.PADDING_SIMPLIFICATION,
            AnchorSwitchTemplate().instantiate(
                instance_id=_child_id(relation, "pad", reduced_pad),
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch=_int_hole(holes, "epoch"),
                bank_a=_int_hole(holes, "bank_a"),
                bank_b=_int_hole(holes, "bank_b"),
                pad=reduced_pad,
                repeats=repeats,
            ),
            "reduce public padding modulo the four-phase scheduler",
        )
    yield from _anchor_bank_simplifications(relation)


def _token_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    pad = _int_hole(holes, "pad")
    token_a = _int_hole(holes, "token_a")
    token_b = _int_hole(holes, "token_b")
    if (reduced_pad := pad % 4) != pad:
        yield (
            ReductionKind.PADDING_SIMPLIFICATION,
            TokenSwitchTemplate().instantiate(
                instance_id=_child_id(relation, "pad", reduced_pad),
                lane=_int_hole(holes, "lane"),
                token_a=token_a,
                token_b=token_b,
                epoch=_int_hole(holes, "epoch"),
                anchor=_int_hole(holes, "anchor"),
                pad=reduced_pad,
            ),
            "reduce public padding modulo the four-phase scheduler",
        )
    if token_a != 0:
        normalized_b = token_a ^ token_b
        if normalized_b != 0:
            yield (
                ReductionKind.TOKEN_ANCHOR_SIMPLIFICATION,
                TokenSwitchTemplate().instantiate(
                    instance_id=_child_id(relation, "token", normalized_b),
                    lane=_int_hole(holes, "lane"),
                    token_a=0,
                    token_b=normalized_b,
                    epoch=_int_hole(holes, "epoch"),
                    anchor=_int_hole(holes, "anchor"),
                    pad=pad,
                ),
                "xor-normalize token_a to zero",
            )


def _epoch_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    for name in ("pad_a", "pad_b"):
        pad_a = _int_hole(holes, "pad_a")
        pad_b = _int_hole(holes, "pad_b")
        original = pad_a if name == "pad_a" else pad_b
        reduced = original % 4
        if reduced == original:
            continue
        if name == "pad_a":
            pad_a = reduced
        else:
            pad_b = reduced
        yield (
            ReductionKind.PADDING_SIMPLIFICATION,
            EpochSwitchTemplate().instantiate(
                instance_id=_child_id(relation, name, reduced),
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch_a=_int_hole(holes, "epoch_a"),
                epoch_b=_int_hole(holes, "epoch_b"),
                anchor=_int_hole(holes, "anchor"),
                pad_a=pad_a,
                pad_b=pad_b,
            ),
            f"reduce {name} modulo the four-phase scheduler",
        )


def _phase_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    for name in ("pad_a", "pad_b"):
        pad_a = _int_hole(holes, "pad_a")
        pad_b = _int_hole(holes, "pad_b")
        original = pad_a if name == "pad_a" else pad_b
        reduced = original % 4
        if reduced == original:
            continue
        if name == "pad_a":
            pad_a = reduced
        else:
            pad_b = reduced
        yield (
            ReductionKind.PADDING_SIMPLIFICATION,
            PhaseShiftTemplate().instantiate(
                instance_id=_child_id(relation, name, reduced),
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch=_int_hole(holes, "epoch"),
                anchor=_int_hole(holes, "anchor"),
                pad_a=pad_a,
                pad_b=pad_b,
            ),
            f"reduce {name} modulo the four-phase scheduler",
        )


def _repeat_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    repeats = _int_hole(holes, "repeats")
    pad = _int_hole(holes, "pad")
    if repeats > 2:
        yield (
            ReductionKind.REPEAT_SHRINK,
            RepeatAmplifyTemplate().instantiate(
                instance_id=_child_id(relation, "repeat", repeats - 1),
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch=_int_hole(holes, "epoch"),
                anchor=_int_hole(holes, "anchor"),
                pad=pad,
                repeats=repeats - 1,
                drain_between=bool(_int_hole(holes, "drain_between")),
            ),
            "lower amplification repeat count by one",
        )
    if (reduced_pad := pad % 4) != pad:
        yield (
            ReductionKind.PADDING_SIMPLIFICATION,
            RepeatAmplifyTemplate().instantiate(
                instance_id=_child_id(relation, "pad", reduced_pad),
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch=_int_hole(holes, "epoch"),
                anchor=_int_hole(holes, "anchor"),
                pad=reduced_pad,
                repeats=repeats,
                drain_between=bool(_int_hole(holes, "drain_between")),
            ),
            "reduce public padding modulo the four-phase scheduler",
        )


def _swap_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    first = Cell(
        _int_hole(holes, "first_lane"),
        _int_hole(holes, "first_token"),
        _int_hole(holes, "first_epoch"),
        _int_hole(holes, "first_anchor"),
        _int_hole(holes, "first_pad"),
    )
    second = Cell(
        _int_hole(holes, "second_lane"),
        _int_hole(holes, "second_token"),
        _int_hole(holes, "second_epoch"),
        _int_hole(holes, "second_anchor"),
        _int_hole(holes, "second_pad"),
    )
    for field in ("first_pad", "second_pad"):
        reduced_first = first
        reduced_second = second
        original = first.pad if field == "first_pad" else second.pad
        reduced = original % 4
        if reduced == original:
            continue
        if field == "first_pad":
            reduced_first = Cell(first.lane, first.token, first.epoch, first.anchor, reduced)
        else:
            reduced_second = Cell(second.lane, second.token, second.epoch, second.anchor, reduced)
        yield (
            ReductionKind.PADDING_SIMPLIFICATION,
            IndependentSwapTemplate().instantiate(
                instance_id=_child_id(relation, field, reduced),
                first=reduced_first,
                second=reduced_second,
            ),
            f"reduce {field} modulo the four-phase scheduler",
        )


def _context_neighbors(
    relation: RelationInstance,
    known_relations: Mapping[str, RelationInstance],
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    base_hash = _str_hole(holes, "base_instance_hash")
    base = known_relations.get(base_hash)
    prefix_pad = _int_hole(holes, "prefix_pad")
    suffix_fence = bool(_int_hole(holes, "suffix_fence"))
    if base is not None:
        if (reduced_prefix := prefix_pad % 4) != prefix_pad:
            yield (
                ReductionKind.CONTEXT_HISTORY_SHORTENING,
                ContextLiftTemplate().instantiate(
                    instance_id=_child_id(relation, "prefix", reduced_prefix),
                    base=base,
                    prefix_pad=reduced_prefix,
                    suffix_fence=suffix_fence,
                ),
                "reduce common context padding modulo the four-phase scheduler",
            )
        if suffix_fence:
            yield (
                ReductionKind.PADDING_SIMPLIFICATION,
                ContextLiftTemplate().instantiate(
                    instance_id=_child_id(relation, "suffix-fence", 0),
                    base=base,
                    prefix_pad=prefix_pad,
                    suffix_fence=False,
                ),
                "remove common trailing fence when it is not needed",
            )
        yield (
            ReductionKind.RELATION_COMPOSITION_COLLAPSE,
            _with_child_id(base, _child_id(relation, "collapse", 0)),
            "collapse context-lift to its certified primitive base relation",
        )


def _register_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    permutation = tuple(_int_hole(relation.holes, f"r{index}") for index in range(8))
    body = relation.source_program.instructions[:-1]
    if body:
        for index in range(len(body)):
            candidate_body = body[:index] + body[index + 1 :]
            candidate_program = Program((*candidate_body, Instruction.halt()))
            yield (
                ReductionKind.SYMMETRIC_DELETION,
                RegisterRenameTemplate().instantiate(
                    instance_id=_child_id(relation, "delete", index),
                    source=candidate_program,
                    permutation=permutation,
                ),
                f"delete matched ordinary instruction {index}",
            )


def _hard_replay_neighbors(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    repetitions = _int_hole(relation.holes, "repetitions")
    program = relation.source_program
    if repetitions > 2:
        yield (
            ReductionKind.REPEAT_SHRINK,
            HardReplayTemplate().instantiate(
                instance_id=_child_id(relation, "repetitions", repetitions - 1),
                program=program,
                repetitions=repetitions - 1,
                deterministic_observation=bool(
                    _int_hole(relation.holes, "deterministic_observation")
                ),
            ),
            "lower hard replay arms by one",
        )
    body = program.instructions[:-1]
    if body:
        for index in range(len(body)):
            candidate_body = body[:index] + body[index + 1 :]
            candidate_program = Program((*candidate_body, Instruction.halt()))
            yield (
                ReductionKind.SYMMETRIC_DELETION,
                HardReplayTemplate().instantiate(
                    instance_id=_child_id(relation, "delete", index),
                    program=candidate_program,
                    repetitions=repetitions,
                    deterministic_observation=bool(
                        _int_hole(relation.holes, "deterministic_observation")
                    ),
                ),
                f"delete matched replay instruction {index}",
            )


def _soft_history_neighbors(
    relation: RelationInstance,
    known_relations: Mapping[str, RelationInstance],
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    measurement_hash = _str_hole(relation.holes, "measurement_hash")
    measurement = known_relations.get(measurement_hash)
    if measurement is None:
        return
    source_history, follow_history = _split_soft_histories(relation, measurement)
    for side, history in (("source", source_history), ("follow-up", follow_history)):
        body = history.instructions[:-1]
        for index, instruction in enumerate(body):
            if instruction.op is Op.PAD and instruction.operands[0] >= 4:
                reduced_amount = instruction.operands[0] % 4
                new_instruction = () if reduced_amount == 0 else (Instruction.pad(reduced_amount),)
                new_body = body[:index] + new_instruction + body[index + 1 :]
            else:
                new_body = body[:index] + body[index + 1 :]
            new_history = Program((*new_body, Instruction.halt()))
            if side == "source":
                history_a, history_b = new_history, follow_history
            else:
                history_a, history_b = source_history, new_history
            yield (
                ReductionKind.CONTEXT_HISTORY_SHORTENING,
                SoftHistoryContrastTemplate().instantiate(
                    instance_id=_child_id(relation, f"history-{side}", index),
                    history_a=history_a,
                    history_b=history_b,
                    measurement=measurement,
                    state_model_id=_str_hole(relation.holes, "state_model_id"),
                    source_state=_str_hole(relation.holes, "source_state"),
                    follow_up_state=_str_hole(relation.holes, "follow_up_state"),
                ),
                f"shorten {side} history instruction {index}",
            )


def _anchor_bank_simplifications(
    relation: RelationInstance,
) -> Iterable[tuple[ReductionKind, RelationInstance, str]]:
    holes = relation.holes
    bank_a = _int_hole(holes, "bank_a")
    bank_b = _int_hole(holes, "bank_b")
    if (bank_a, bank_b) == (0, 1):
        return
    if bank_a != bank_b:
        yield (
            ReductionKind.TOKEN_ANCHOR_SIMPLIFICATION,
            AnchorSwitchTemplate().instantiate(
                instance_id=_child_id(relation, "banks", 1),
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch=_int_hole(holes, "epoch"),
                bank_a=0,
                bank_b=1,
                pad=_int_hole(holes, "pad"),
                repeats=_int_hole(holes, "repeats"),
            ),
            "try canonical distinct anchor banks 0 and 1",
        )


def _split_soft_histories(
    relation: RelationInstance, measurement: RelationInstance
) -> tuple[Program, Program]:
    suffix = measurement.source_program.instructions

    def split(program: Program) -> Program:
        if (
            len(program.instructions) < len(suffix)
            or program.instructions[-len(suffix) :] != suffix
        ):
            raise ValueError("soft-history program does not end in the measurement suffix")
        prefix = program.instructions[: -len(suffix)]
        return Program((*prefix, Instruction.halt()))

    return split(relation.source_program), split(relation.follow_up_programs[0])


def _with_child_id(relation: RelationInstance, instance_id: str) -> RelationInstance:
    relation_id = relation.relation_id
    holes = relation.holes
    if relation_id == AnchorSwitchTemplate.relation_id:
        return AnchorSwitchTemplate().instantiate(
            instance_id=instance_id,
            lane=_int_hole(holes, "lane"),
            token=_int_hole(holes, "token"),
            epoch=_int_hole(holes, "epoch"),
            bank_a=_int_hole(holes, "bank_a"),
            bank_b=_int_hole(holes, "bank_b"),
            pad=_int_hole(holes, "pad"),
            repeats=_int_hole(holes, "repeats"),
        )
    return relation


def _history_length(relation: RelationInstance) -> int:
    if relation.relation_id == ContextLiftTemplate.relation_id:
        return _int_hole(relation.holes, "prefix_pad") + int(
            _int_hole(relation.holes, "suffix_fence")
        )
    if relation.relation_id == SoftHistoryContrastTemplate.relation_id:
        return sum(
            1
            for program in relation.programs
            for instruction in program.instructions
            if instruction.op in {Op.PAD, Op.FENCE}
        )
    return 0


def _abstract_signature(deltas: Sequence[int], kind: SignatureKind) -> _Signature:
    if kind is SignatureKind.EXACT_RESIDUAL:
        return tuple(deltas)
    if kind is SignatureKind.SIGN:
        return tuple((value > 0) - (value < 0) for value in deltas)
    return tuple(int(value != 0) for value in deltas)


def _partition_refines(candidate: _SignatureMap, original: _SignatureMap) -> bool:
    original_by_model = dict(original)
    seen: dict[_Signature, _Signature] = {}
    for model_id, candidate_signature in candidate:
        original_signature = original_by_model[model_id]
        existing = seen.setdefault(candidate_signature, original_signature)
        if existing != original_signature:
            return False
    return True


def _lane_assignments(
    lanes: tuple[int, ...], secrets: tuple[int, ...]
) -> tuple[dict[int, int], ...]:
    if len(lanes) > 2:
        assignments = []
        for secret in secrets:
            assignments.append({lane: secret for lane in lanes})
        return tuple(assignments)
    if len(lanes) == 1:
        return tuple({lanes[0]: secret} for secret in secrets)
    first, second = lanes
    return tuple({first: left, second: right} for left in secrets for right in secrets)


def _programs_data(relation: RelationInstance) -> dict[str, object]:
    return {
        "source": relation.source_program.render(),
        "follow_ups": [program.render() for program in relation.follow_up_programs],
        "source_sha256": relation.source_program.canonical_sha256(),
        "follow_up_sha256": [program.canonical_sha256() for program in relation.follow_up_programs],
    }


def _predicate_key(
    original: RelationInstance, candidate: RelationInstance, config: ReductionConfig
) -> str:
    data = {
        "original": original.instance_hash,
        "candidate": candidate.instance_hash,
        "mode": config.mode.value,
        "signature_kind": config.signature_kind.value,
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _child_id(relation: RelationInstance, name: str, value: int) -> str:
    return f"{relation.instance_id}~{name}-{value}"


def _int_hole(holes: Mapping[str, int | str], name: str) -> int:
    value = holes[name]
    if not isinstance(value, int):
        raise TypeError(f"relation hole {name} is not an integer")
    return value


def _str_hole(holes: Mapping[str, int | str], name: str) -> str:
    value = holes[name]
    if not isinstance(value, str):
        raise TypeError(f"relation hole {name} is not a string")
    return value
