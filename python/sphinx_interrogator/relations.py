"""Certified relation templates over immutable public probe programs."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from sphinx_interrogator.ast import Instruction, Op, Program
from sphinx_interrogator.certificates import (
    DEFAULT_CERTIFICATE_REGISTRY,
    ProofMethod,
    RelationCertificate,
)
from sphinx_interrogator.constraints import ConstraintExtraction
from sphinx_interrogator.model import ExecutionResult, OutcomeClass, RelationEvidence
from sphinx_interrogator.normalization import (
    NormalizedObservation,
    PairDecision,
    decide_pair,
    normalize_execution,
)

if TYPE_CHECKING:
    from sphinx_interrogator.target_model import FaultVariant, MicroState

_SEMANTIC_VERSION = "0.1.0"
_IDENTITY_PROFILE_SCOPE = ("tutorial@0.1.0", "standard@0.1.0")
_ALL_PROFILE_SCOPE = (*_IDENTITY_PROFILE_SCOPE, "research@0.1.0")


@dataclass(frozen=True, slots=True)
class Applicability:
    """Structured proof-precondition result returned before instantiation."""

    accepted: bool
    reasons: tuple[str, ...]
    certified_preconditions: tuple[str, ...] = ()

    @classmethod
    def accept(cls, *preconditions: str) -> Applicability:
        """Construct an accepted applicability result."""
        return cls(True, (), tuple(preconditions))

    @classmethod
    def reject(cls, *reasons: str) -> Applicability:
        """Construct a rejected applicability result."""
        return cls(False, tuple(reasons), ())

    def require(self) -> None:
        """Raise a stable construction error if a precondition was rejected."""
        if not self.accepted:
            raise ValueError("; ".join(self.reasons))


@dataclass(frozen=True, slots=True)
class BankFact:
    """Compatibility equality/disequality fact for the tutorial lane solver."""

    lane: int
    token: int
    epoch: int
    bank: int
    equal: bool
    confidence: float
    source_relation_instance_id: str


@dataclass(frozen=True, slots=True)
class Cell:
    """One typed experiment cell used by several relation grammars."""

    lane: int
    token: int
    epoch: int
    anchor: int
    pad: int = 0

    def __post_init__(self) -> None:
        Instruction.probe(self.lane, self.token, self.epoch)
        Instruction.anchor(self.anchor, self.epoch)
        Instruction.pad(self.pad)

    def instructions(self) -> tuple[Instruction, ...]:
        """Build the typed padding/probe/anchor sequence."""
        prefix = () if self.pad == 0 else (Instruction.pad(self.pad),)
        return (
            *prefix,
            Instruction.probe(self.lane, self.token, self.epoch),
            Instruction.anchor(self.anchor, self.epoch),
        )


@dataclass(frozen=True, slots=True)
class RelationInstance:
    """Canonical program family, preconditions, certificate, and extractor scope."""

    relation_id: str
    instance_id: str
    instance_hash: str
    source_query_id: str
    follow_up_query_ids: tuple[str, ...]
    source_program: Program
    follow_up_programs: tuple[Program, ...]
    holes: Mapping[str, int | str]
    expected_observation_relation: str
    reset_policy: str
    involved_lanes: tuple[int, ...]
    emits_secret_constraints: bool
    reducer_rules: tuple[str, ...]
    certificate: RelationCertificate

    def __post_init__(self) -> None:
        if self.relation_id.count("/v") != 1:
            raise ValueError("relation_id must be versioned")
        if not self.instance_id or not self.follow_up_programs:
            raise ValueError("relation instance IDs and follow-ups must not be empty")
        if len(self.follow_up_query_ids) != len(self.follow_up_programs):
            raise ValueError("follow-up query IDs do not match programs")
        if self.reset_policy not in {"hard", "soft", "none"}:
            raise ValueError("unknown relation reset policy")
        if tuple(sorted(set(self.involved_lanes))) != self.involved_lanes:
            raise ValueError("involved_lanes must be sorted and unique")
        if self.certificate.relation_instance_hash != self.instance_hash:
            raise ValueError("certificate is not bound to the relation instance")

    def architectural_precheck(self) -> bool:
        """Check the construction theorem associated with this template family."""
        if not self.instance_binding_valid():
            return False
        if all(program_has_silent_architecture(program) for program in self.programs):
            return True
        if self.relation_id == RegisterRenameTemplate.relation_id:
            try:
                permutation = tuple(_int_hole(self.holes, f"r{index}") for index in range(8))
            except (KeyError, TypeError):
                return False
            expected = Program(
                tuple(
                    _rename_instruction(instruction, permutation)
                    for instruction in self.source_program.instructions
                )
            )
            return self.holes.get(
                "zero_initialized_registers"
            ) == 1 and self.follow_up_programs == (expected,)
        if self.relation_id == HardReplayTemplate.relation_id:
            return all(program == self.source_program for program in self.follow_up_programs)
        return False

    def fault_free_precheck(self) -> bool:
        """Exhaustively check zero fault residual over the bounded public model."""
        if not self.instance_binding_valid():
            return False
        return _fault_free_model_precheck(
            self.programs,
            self.involved_lanes,
            self.reset_policy,
        )

    def instance_binding_valid(self) -> bool:
        """Recompute the canonical hash bound into the certificate."""
        recomputed = _instance_hash(
            self.relation_id,
            self.source_program,
            self.follow_up_programs,
            self.holes,
            self.reset_policy,
            self.involved_lanes,
        )
        return (
            recomputed == self.instance_hash
            and self.certificate.relation_instance_hash == recomputed
        )

    @property
    def programs(self) -> tuple[Program, ...]:
        """Return the source followed by every follow-up arm."""
        return (self.source_program, *self.follow_up_programs)

    def to_data(self) -> dict[str, object]:
        """Return the stable relation/certificate wire representation."""
        return {
            "schema_version": "1.0",
            "relation_id": self.relation_id,
            "instance_id": self.instance_id,
            "instance_hash": self.instance_hash,
            "source_query_id": self.source_query_id,
            "follow_up_query_ids": list(self.follow_up_query_ids),
            "source_program_sha256": self.source_program.canonical_sha256(),
            "follow_up_program_sha256": [
                program.canonical_sha256() for program in self.follow_up_programs
            ],
            "holes": dict(self.holes),
            "expected_observation_relation": self.expected_observation_relation,
            "reset_policy": self.reset_policy,
            "involved_lanes": list(self.involved_lanes),
            "emits_secret_constraints": self.emits_secret_constraints,
            "reducer_rules": list(self.reducer_rules),
            "certificate": self.certificate.to_data(),
        }


class RelationTemplate(Protocol):
    """Common discovery surface for relation registries and selectors."""

    relation_id: str

    def normalize(self, result: ExecutionResult, *, noise_bound: int) -> NormalizedObservation:
        """Normalize one public execution under the declared bound."""
        ...

    def decide(
        self,
        relation: RelationInstance,
        source: ExecutionResult,
        follow_up: ExecutionResult,
        *,
        noise_bound: int,
    ) -> PairDecision:
        """Decide one source/follow-up pair."""
        ...

    def extract(
        self,
        relation: RelationInstance,
        source: ExecutionResult,
        follow_up: ExecutionResult,
        decision: PairDecision,
        *,
        noise_bound: int,
        minimum_certificate: ProofMethod = ProofMethod.EXHAUSTIVE_ENUMERATION,
        fault_variants: tuple[FaultVariant, ...] | None = None,
        initial_state: MicroState | None = None,
    ) -> ConstraintExtraction:
        """Extract only constraints allowed by certificate policy."""
        ...

    def reduction_rules(self, relation: RelationInstance) -> tuple[str, ...]:
        """Return certified witness-reduction rules."""
        ...


class CertifiedTemplate:
    """Shared normalizer, decision, extractor, and reducer surface for all templates."""

    relation_id: str

    def normalize(self, result: ExecutionResult, *, noise_bound: int) -> NormalizedObservation:
        """Normalize a public bucket to a conservative pre-noise fault interval."""
        return normalize_execution(result, noise_bound=noise_bound)

    def decide(
        self,
        relation: RelationInstance,
        source: ExecutionResult,
        follow_up: ExecutionResult,
        *,
        noise_bound: int,
    ) -> PairDecision:
        """Decide one ordered pair after checking architecture and static metrics."""
        if relation.relation_id != self.relation_id:
            raise ValueError("relation instance belongs to another template")
        return decide_pair(
            source,
            follow_up,
            expected_source_static=relation.source_program.static_cycles(),
            expected_follow_up_static=relation.follow_up_programs[0].static_cycles(),
            noise_bound=noise_bound,
            assumptions=relation.certificate.preconditions,
        )

    def extract(
        self,
        relation: RelationInstance,
        source: ExecutionResult,
        follow_up: ExecutionResult,
        decision: PairDecision,
        *,
        noise_bound: int,
        minimum_certificate: ProofMethod = ProofMethod.EXHAUSTIVE_ENUMERATION,
        fault_variants: tuple[FaultVariant, ...] | None = None,
        initial_state: MicroState | None = None,
    ) -> ConstraintExtraction:
        """Compile a sound finite model disjunction with configurable proof policy."""
        from sphinx_interrogator.extractors import extract_finite_models

        if relation.relation_id != self.relation_id:
            raise ValueError("relation instance belongs to another template")
        if fault_variants is None:
            return extract_finite_models(
                relation,
                source,
                follow_up,
                decision,
                noise_bound=noise_bound,
                minimum_certificate=minimum_certificate,
                initial_state=initial_state,
            )
        return extract_finite_models(
            relation,
            source,
            follow_up,
            decision,
            noise_bound=noise_bound,
            fault_variants=fault_variants,
            minimum_certificate=minimum_certificate,
            initial_state=initial_state,
        )

    def reduction_rules(self, relation: RelationInstance) -> tuple[str, ...]:
        """Return only reducer rules bound into the certified instance."""
        if relation.relation_id != self.relation_id:
            raise ValueError("relation instance belongs to another template")
        return relation.reducer_rules


class AnchorSwitchTemplate(CertifiedTemplate):
    """Change only the public anchor bank while preserving static semantics."""

    relation_id = "anchor-switch/v1"

    def applicable(self, *, bank_a: int, bank_b: int, repeats: int = 1) -> Applicability:
        """Check distinct anchors and bounded repetition."""
        reasons = []
        if bank_a == bank_b:
            reasons.append("anchor-switch requires two distinct banks")
        if not 1 <= repeats <= 16:
            reasons.append("anchor-switch repeats must be in 1..=16")
        if reasons:
            return Applicability.reject(*reasons)
        return Applicability.accept("hard reset", "identity lane mapping", "reference fault")

    def instantiate(
        self,
        *,
        instance_id: str,
        lane: int,
        token: int,
        epoch: int,
        bank_a: int,
        bank_b: int,
        pad: int,
        repeats: int = 1,
    ) -> RelationInstance:
        """Construct one certified anchor substitution."""
        applicability = self.applicable(bank_a=bank_a, bank_b=bank_b, repeats=repeats)
        applicability.require()
        source = Program.experiment_cell(
            lane=lane, token=token, epoch=epoch, anchor=bank_a, pad=pad, repeats=repeats
        )
        follow_up = Program.experiment_cell(
            lane=lane, token=token, epoch=epoch, anchor=bank_b, pad=pad, repeats=repeats
        )
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "lane": lane,
                "token": token,
                "epoch": epoch,
                "bank_a": bank_a,
                "bank_b": bank_b,
                "pad": pad,
                "repeats": repeats,
            },
            involved_lanes=(lane,),
            preconditions=applicability.certified_preconditions,
            reducer_rules=("drop-common-fence", "reduce-repeats", "shrink-pad-mod-4"),
        )

    def extract_facts(
        self,
        relation: RelationInstance,
        evidence: RelationEvidence,
        *,
        hard_preconditions_certified: bool,
        decision_threshold: float = 0.5,
    ) -> tuple[BankFact, ...]:
        """Compatibility exact-tutorial extractor; bounded campaigns use `extractors.py`."""
        if relation.relation_id != self.relation_id:
            raise ValueError("relation instance does not belong to anchor-switch/v1")
        if not hard_preconditions_certified:
            return ()
        holes = relation.holes

        def fact(bank: int, *, equal: bool) -> BankFact:
            return BankFact(
                lane=_int_hole(holes, "lane"),
                token=_int_hole(holes, "token"),
                epoch=_int_hole(holes, "epoch"),
                bank=bank,
                equal=equal,
                confidence=evidence.confidence,
                source_relation_instance_id=relation.instance_id,
            )

        if evidence.normalized_delta > decision_threshold:
            return (
                fact(_int_hole(holes, "bank_b"), equal=True),
                fact(_int_hole(holes, "bank_a"), equal=False),
            )
        if evidence.normalized_delta < -decision_threshold:
            return (
                fact(_int_hole(holes, "bank_a"), equal=True),
                fact(_int_hole(holes, "bank_b"), equal=False),
            )
        if evidence.outcome is OutcomeClass.HOLDS and evidence.confidence >= 0.99:
            return (
                fact(_int_hole(holes, "bank_a"), equal=False),
                fact(_int_hole(holes, "bank_b"), equal=False),
            )
        return ()

    def classify(
        self,
        relation_instance_id: str,
        normalized_delta: float,
        *,
        confidence: float,
        source_request_ids: tuple[str, ...],
        decision_threshold: float = 0.5,
    ) -> RelationEvidence:
        """Compatibility classifier for the deterministic tutorial campaign."""
        if normalized_delta > decision_threshold:
            outcome = OutcomeClass.VIOLATED_POSITIVE
        elif normalized_delta < -decision_threshold:
            outcome = OutcomeClass.VIOLATED_NEGATIVE
        elif confidence >= 0.95:
            outcome = OutcomeClass.HOLDS
        else:
            outcome = OutcomeClass.INCONCLUSIVE
        return RelationEvidence(
            relation_instance_id=relation_instance_id,
            outcome=outcome,
            normalized_delta=normalized_delta,
            confidence=confidence,
            source_request_ids=source_request_ids,
        )


class DrainedAnchorSwitchTemplate(CertifiedTemplate):
    """Compare two public anchors through the same drained repetition schedule."""

    relation_id = "drained-anchor-switch/v1"

    def applicable(
        self,
        *,
        bank_a: int,
        bank_b: int,
        repeats: int,
        drain_between: bool = True,
    ) -> Applicability:
        """Check distinct anchors and bounded drained repetition."""
        reasons = []
        if bank_a == bank_b:
            reasons.append("drained-anchor-switch requires two distinct banks")
        if not 2 <= repeats <= 16:
            reasons.append("drained-anchor-switch requires repeats in 2..=16")
        if not drain_between:
            reasons.append("drained-anchor-switch requires certified drain/phase restoration")
        if reasons:
            return Applicability.reject(*reasons)
        return Applicability.accept(
            "hard reset",
            "identity lane mapping",
            "drained replay between cells",
            "restored entry phase",
            "reference fault",
        )

    def instantiate(
        self,
        *,
        instance_id: str,
        lane: int,
        token: int,
        epoch: int,
        bank_a: int,
        bank_b: int,
        pad: int,
        repeats: int,
        drain_between: bool = True,
    ) -> RelationInstance:
        """Construct a repeated anchor substitution with equal public resources."""
        applicability = self.applicable(
            bank_a=bank_a,
            bank_b=bank_b,
            repeats=repeats,
            drain_between=drain_between,
        )
        applicability.require()
        source = _drained_repetitions_program(Cell(lane, token, epoch, bank_a, pad), repeats)
        follow_up = _drained_repetitions_program(Cell(lane, token, epoch, bank_b, pad), repeats)
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "lane": lane,
                "token": token,
                "epoch": epoch,
                "bank_a": bank_a,
                "bank_b": bank_b,
                "pad": pad,
                "repeats": repeats,
                "drain_between": int(drain_between),
            },
            involved_lanes=(lane,),
            preconditions=applicability.certified_preconditions,
            reducer_rules=("reduce-repeats", "shrink-pad-mod-4"),
        )


class TokenSwitchTemplate(CertifiedTemplate):
    """Change a probe token while retaining lane, epoch, anchor, and phase context."""

    relation_id = "token-switch/v1"

    def applicable(self, *, token_a: int, token_b: int) -> Applicability:
        """Check that the transformed token is observably distinct."""
        if token_a == token_b:
            return Applicability.reject("token-switch requires distinct tokens")
        return Applicability.accept("hard reset", "identity lane mapping", "reference fault")

    def instantiate(
        self,
        *,
        instance_id: str,
        lane: int,
        token_a: int,
        token_b: int,
        epoch: int,
        anchor: int,
        pad: int,
    ) -> RelationInstance:
        """Construct one certified token substitution."""
        applicability = self.applicable(token_a=token_a, token_b=token_b)
        applicability.require()
        source = _cell_program(Cell(lane, token_a, epoch, anchor, pad))
        follow_up = _cell_program(Cell(lane, token_b, epoch, anchor, pad))
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "lane": lane,
                "token_a": token_a,
                "token_b": token_b,
                "epoch": epoch,
                "anchor": anchor,
                "pad": pad,
            },
            involved_lanes=(lane,),
            preconditions=applicability.certified_preconditions,
            reducer_rules=("shrink-token-xor", "shrink-pad-mod-4"),
        )


class EpochSwitchTemplate(CertifiedTemplate):
    """Compare low/high public S-box projections with explicit phase padding."""

    relation_id = "epoch-switch/v1"

    def applicable(self, *, epoch_a: int, epoch_b: int) -> Applicability:
        """Check that low and high projection epochs differ."""
        if epoch_a == epoch_b:
            return Applicability.reject("epoch-switch requires distinct epochs")
        return Applicability.accept("hard reset", "identity lane mapping", "reference fault")

    def instantiate(
        self,
        *,
        instance_id: str,
        lane: int,
        token: int,
        epoch_a: int,
        epoch_b: int,
        anchor: int,
        pad_a: int,
        pad_b: int,
    ) -> RelationInstance:
        """Construct one certified epoch/projection substitution."""
        applicability = self.applicable(epoch_a=epoch_a, epoch_b=epoch_b)
        applicability.require()
        source = _cell_program(Cell(lane, token, epoch_a, anchor, pad_a))
        follow_up = _cell_program(Cell(lane, token, epoch_b, anchor, pad_b))
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "lane": lane,
                "token": token,
                "epoch_a": epoch_a,
                "epoch_b": epoch_b,
                "anchor": anchor,
                "pad_a": pad_a,
                "pad_b": pad_b,
            },
            involved_lanes=(lane,),
            preconditions=applicability.certified_preconditions,
            reducer_rules=("shrink-pad-mod-4",),
        )


class PhaseShiftTemplate(CertifiedTemplate):
    """Change only public phase padding and subtract its declared static cost."""

    relation_id = "phase-shift/v1"

    def applicable(self, *, pad_a: int, pad_b: int) -> Applicability:
        """Check that the pads select distinct two-bit phases."""
        if pad_a % 4 == pad_b % 4:
            return Applicability.reject("phase-shift requires distinct two-bit phases")
        return Applicability.accept("hard reset", "identity lane mapping", "reference fault")

    def instantiate(
        self,
        *,
        instance_id: str,
        lane: int,
        token: int,
        epoch: int,
        anchor: int,
        pad_a: int,
        pad_b: int,
    ) -> RelationInstance:
        """Construct one certified phase shift with static normalization."""
        applicability = self.applicable(pad_a=pad_a, pad_b=pad_b)
        applicability.require()
        source = _cell_program(Cell(lane, token, epoch, anchor, pad_a))
        follow_up = _cell_program(Cell(lane, token, epoch, anchor, pad_b))
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "lane": lane,
                "token": token,
                "epoch": epoch,
                "anchor": anchor,
                "pad_a": pad_a,
                "pad_b": pad_b,
            },
            involved_lanes=(lane,),
            preconditions=applicability.certified_preconditions,
            reducer_rules=("shrink-pad-mod-4",),
        )


class RepeatAmplifyTemplate(CertifiedTemplate):
    """Compare one cell with an exact bounded replay-state recurrence."""

    relation_id = "repeat-amplify/v1"

    def applicable(self, *, repeats: int, drain_between: bool = True) -> Applicability:
        """Check the bounded recurrence size."""
        reasons = []
        if not 2 <= repeats <= 16:
            reasons.append("repeat-amplify requires repeats in 2..=16")
        if not drain_between:
            reasons.append("repeat-amplify requires certified drain/phase restoration")
        if reasons:
            return Applicability.reject(*reasons)
        return Applicability.accept(
            "hard reset",
            "identity lane mapping",
            "drained replay between cells",
            "restored entry phase",
            "reference fault",
        )

    def instantiate(
        self,
        *,
        instance_id: str,
        lane: int,
        token: int,
        epoch: int,
        anchor: int,
        pad: int,
        repeats: int,
        drain_between: bool = True,
    ) -> RelationInstance:
        """Construct a one-cell versus repeated-cell comparison."""
        applicability = self.applicable(repeats=repeats, drain_between=drain_between)
        applicability.require()
        cell = Cell(lane, token, epoch, anchor, pad)
        source = _drained_repetitions_program(cell, 1)
        follow_up = _drained_repetitions_program(cell, repeats)
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "lane": lane,
                "token": token,
                "epoch": epoch,
                "anchor": anchor,
                "pad": pad,
                "repeats": repeats,
                "drain_between": int(drain_between),
            },
            involved_lanes=(lane,),
            preconditions=applicability.certified_preconditions,
            reducer_rules=("reduce-repeats", "shrink-pad-mod-4"),
        )


class IndependentSwapTemplate(CertifiedTemplate):
    """Swap two architecture-silent cells to expose scheduler order dependence."""

    relation_id = "independent-swap/v1"

    def applicable(self, *, first: Cell, second: Cell) -> Applicability:
        """Reject a vacuous swap of identical cells."""
        if first == second:
            return Applicability.reject("independent-swap requires distinct cells")
        return Applicability.accept("hard reset", "straight-line silent cells", "reference fault")

    def instantiate(
        self,
        *,
        instance_id: str,
        first: Cell,
        second: Cell,
    ) -> RelationInstance:
        """Construct both orderings of two silent cells."""
        applicability = self.applicable(first=first, second=second)
        applicability.require()
        source = _cells_program((first, second))
        follow_up = _cells_program((second, first))
        lanes = tuple(sorted({first.lane, second.lane}))
        holes = {
            "first_lane": first.lane,
            "first_token": first.token,
            "first_epoch": first.epoch,
            "first_anchor": first.anchor,
            "first_pad": first.pad,
            "second_lane": second.lane,
            "second_token": second.token,
            "second_epoch": second.epoch,
            "second_anchor": second.anchor,
            "second_pad": second.pad,
        }
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes=holes,
            involved_lanes=lanes,
            preconditions=applicability.certified_preconditions,
            reducer_rules=("drop-independent-cell", "shrink-pad-mod-4"),
        )


class ContextLiftTemplate(CertifiedTemplate):
    """Embed an already certified pair in one architecture-silent public context."""

    relation_id = "context-lift/v1"

    def applicable(self, *, base: RelationInstance, prefix_pad: int) -> Applicability:
        """Check the base certificate and common context shape."""
        if len(base.follow_up_programs) != 1:
            return Applicability.reject("context-lift currently requires one follow-up")
        if not base.architectural_precheck():
            return Applicability.reject("base relation lacks an architectural certificate")
        if prefix_pad < 0:
            return Applicability.reject("context prefix padding must be nonnegative")
        return Applicability.accept("base certificate valid", "common silent context", "hard reset")

    def instantiate(
        self,
        *,
        instance_id: str,
        base: RelationInstance,
        prefix_pad: int,
        suffix_fence: bool = True,
    ) -> RelationInstance:
        """Embed a certified pair in matching silent prefix/suffix context."""
        applicability = self.applicable(base=base, prefix_pad=prefix_pad)
        applicability.require()
        source = _lift_program(base.source_program, prefix_pad, suffix_fence)
        follow_up = _lift_program(base.follow_up_programs[0], prefix_pad, suffix_fence)
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "base_instance_hash": base.instance_hash,
                "prefix_pad": prefix_pad,
                "suffix_fence": int(suffix_fence),
            },
            involved_lanes=base.involved_lanes,
            preconditions=applicability.certified_preconditions,
            reducer_rules=("drop-common-context", "shrink-pad-mod-4"),
        )


class RegisterRenameTemplate(CertifiedTemplate):
    """Alpha-rename all register operands under hard-reset zero public input."""

    relation_id = "register-rename/v1"

    def applicable(self, *, permutation: tuple[int, ...]) -> Applicability:
        """Check a nontrivial register bijection."""
        if len(permutation) != 8 or tuple(sorted(permutation)) != tuple(range(8)):
            return Applicability.reject("register permutation must be a bijection over r0..r7")
        if permutation == tuple(range(8)):
            return Applicability.reject("register-rename requires a non-identity permutation")
        return Applicability.accept("hard reset", "zero public register input", "alpha renaming")

    def instantiate(
        self,
        *,
        instance_id: str,
        source: Program,
        permutation: tuple[int, ...],
    ) -> RelationInstance:
        """Alpha-rename every register operand in a validated source program."""
        applicability = self.applicable(permutation=permutation)
        applicability.require()
        follow_up = Program(
            tuple(_rename_instruction(item, permutation) for item in source.instructions)
        )
        lanes = _program_lanes(source)
        holes: dict[str, int | str] = {
            **{f"r{index}": value for index, value in enumerate(permutation)},
            "zero_initialized_registers": 1,
        }
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes=holes,
            involved_lanes=lanes,
            preconditions=applicability.certified_preconditions,
            reducer_rules=("drop-dead-renamed-register",),
            emits_secret_constraints=False,
            proof_method=ProofMethod.DIFFERENTIAL_PROPERTY,
            profile_scope=_ALL_PROFILE_SCOPE,
            architectural_claim=(
                "public digest and final architecture agree up to register permutation"
            ),
        )


class HardReplayTemplate(CertifiedTemplate):
    """Repeat an identical program after hard reset to validate deterministic apparatus."""

    relation_id = "hard-replay/v1"

    def applicable(self, *, repetitions: int, deterministic_observation: bool) -> Applicability:
        """Require bounded repeats and a no-jitter deterministic profile."""
        reasons = []
        if not 2 <= repetitions <= 32:
            reasons.append("hard-replay repetitions must be in 2..=32")
        if not deterministic_observation:
            reasons.append("hard-replay requires a deterministic no-jitter observation profile")
        if reasons:
            return Applicability.reject(*reasons)
        return Applicability.accept("hard reset", "no observation jitter", "fixed challenge")

    def instantiate(
        self,
        *,
        instance_id: str,
        program: Program,
        repetitions: int,
        deterministic_observation: bool,
    ) -> RelationInstance:
        """Construct identical hard-reset replay arms."""
        applicability = self.applicable(
            repetitions=repetitions,
            deterministic_observation=deterministic_observation,
        )
        applicability.require()
        follow_ups = tuple(program for _ in range(repetitions - 1))
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=program,
            follow_ups=follow_ups,
            holes={"repetitions": repetitions, "deterministic_observation": 1},
            involved_lanes=_program_lanes(program),
            preconditions=applicability.certified_preconditions,
            reducer_rules=("reduce-repetitions",),
            emits_secret_constraints=False,
            profile_scope=("tutorial@0.1.0",),
            architectural_claim="identical hard-reset executions have identical architecture",
            fault_free_claim="identical hard-reset executions have identical static cost",
        )


class SoftHistoryContrastTemplate(CertifiedTemplate):
    """Compare one measurement suffix after two certified soft-reset histories."""

    relation_id = "soft-history-contrast/v1"

    def applicable(
        self,
        *,
        history_a: Program,
        history_b: Program,
        measurement: RelationInstance,
        state_model_id: str,
    ) -> Applicability:
        """Check that histories and the measured suffix are public-silent."""
        reasons = []
        if not state_model_id:
            reasons.append("soft-history contrast requires a learned/exact state-model ID")
        if not program_has_silent_architecture(history_a):
            reasons.append("source history is not architecture-silent")
        if not program_has_silent_architecture(history_b):
            reasons.append("follow-up history is not architecture-silent")
        if len(measurement.follow_up_programs) != 1:
            reasons.append("measurement relation must have exactly one follow-up")
        if not measurement.architectural_precheck():
            reasons.append("measurement lacks an architectural certificate")
        if reasons:
            return Applicability.reject(*reasons)
        return Applicability.accept(
            "soft reset entry",
            "public architecture-silent histories",
            "shared certified measurement suffix",
            "named state-model provenance",
            "state-conditioned constraints are retractable",
        )

    def instantiate(
        self,
        *,
        instance_id: str,
        history_a: Program,
        history_b: Program,
        measurement: RelationInstance,
        state_model_id: str,
        source_state: str,
        follow_up_state: str,
    ) -> RelationInstance:
        """Construct a state-conditioned contrast around a certified measurement."""
        applicability = self.applicable(
            history_a=history_a,
            history_b=history_b,
            measurement=measurement,
            state_model_id=state_model_id,
        )
        applicability.require()
        if not source_state or not follow_up_state:
            raise ValueError("soft-history contrast requires named source/follow-up states")
        source = _compose_history_measurement(history_a, measurement.source_program)
        follow_up = _compose_history_measurement(history_b, measurement.source_program)
        return _build_instance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source=source,
            follow_ups=(follow_up,),
            holes={
                "state_model_id": state_model_id,
                "source_state": source_state,
                "follow_up_state": follow_up_state,
                "measurement_relation": measurement.relation_id,
                "measurement_hash": measurement.instance_hash,
            },
            reset_policy="soft",
            involved_lanes=measurement.involved_lanes,
            preconditions=applicability.certified_preconditions,
            reducer_rules=("shorten-history-prefix", "preserve-measurement-suffix"),
            emits_secret_constraints=False,
            profile_scope=("research@0.1.0",),
            architectural_claim=(
                "public architecture remains silent; only certified hidden history differs"
            ),
            fault_free_claim=(
                "fault-free residual is zero after subtracting each public static cost"
            ),
            expected_observation_relation="state_conditioned_difference",
        )


TEMPLATE_REGISTRY: Mapping[str, RelationTemplate] = MappingProxyType(
    {
        template.relation_id: template
        for template in (
            AnchorSwitchTemplate(),
            DrainedAnchorSwitchTemplate(),
            TokenSwitchTemplate(),
            EpochSwitchTemplate(),
            PhaseShiftTemplate(),
            RepeatAmplifyTemplate(),
            IndependentSwapTemplate(),
            ContextLiftTemplate(),
            RegisterRenameTemplate(),
            HardReplayTemplate(),
            SoftHistoryContrastTemplate(),
        )
    }
)


def program_has_silent_architecture(program: Program) -> bool:
    """Return whether only documented architecture-silent experiments and HALT occur."""
    silent = {Op.PROBE, Op.ANCHOR, Op.PAD, Op.FENCE, Op.HALT}
    return all(instruction.op in silent for instruction in program.instructions)


@lru_cache(maxsize=4096)
def _fault_free_model_precheck(
    programs: tuple[Program, ...],
    involved_lanes: tuple[int, ...],
    reset_policy: str,
) -> bool:
    from sphinx_interrogator.target_model import (
        FaultVariant,
        MicroState,
        execute_experiment_program,
    )

    states: tuple[MicroState, ...] = (MicroState(),)
    if reset_policy != "hard":
        states = tuple(
            MicroState(phase=phase, last_bank=last_bank, replay_credit=replay_credit)
            for phase in range(4)
            for last_bank in (None, 0, 1, 2, 3)
            for replay_credit in range(4)
        )
    assignments = itertools.product(range(16), repeat=len(involved_lanes))
    for values in assignments:
        secret_by_lane = dict(zip(involved_lanes, values, strict=True))
        for state in states:
            for program in programs:
                try:
                    model = execute_experiment_program(
                        program,
                        secret_by_lane,
                        initial_state=state,
                        variant=FaultVariant.OFF,
                    )
                except ValueError:
                    return False
                if model.static_cycles != program.static_cycles() or model.fault_cycles != 0:
                    return False
    return True


def _build_instance(
    *,
    relation_id: str,
    instance_id: str,
    source: Program,
    follow_ups: tuple[Program, ...],
    holes: Mapping[str, int | str],
    involved_lanes: tuple[int, ...],
    preconditions: tuple[str, ...],
    reducer_rules: tuple[str, ...],
    reset_policy: str = "hard",
    emits_secret_constraints: bool = True,
    proof_method: ProofMethod = ProofMethod.EXHAUSTIVE_ENUMERATION,
    profile_scope: tuple[str, ...] = _IDENTITY_PROFILE_SCOPE,
    architectural_claim: str = "final public architecture is equal",
    fault_free_claim: str = "subtracting each public static cost yields equal zero residual",
    expected_observation_relation: str = "equal_after_static_normalization",
) -> RelationInstance:
    canonical_holes = dict(sorted(holes.items()))
    instance_hash = _instance_hash(
        relation_id,
        source,
        follow_ups,
        canonical_holes,
        reset_policy,
        involved_lanes,
    )
    certificate = DEFAULT_CERTIFICATE_REGISTRY.issue(
        relation_instance_hash=instance_hash,
        semantic_version=_SEMANTIC_VERSION,
        profile_scope=profile_scope,
        proof_method=proof_method,
        architectural_claim=architectural_claim,
        fault_free_claim=fault_free_claim,
        preconditions=preconditions,
        limitations=(
            "hard secret extraction is limited to identity lane mapping and declared bounded noise",
            "stateful soft-reset composition requires a separate history certificate",
        ),
    )
    return RelationInstance(
        relation_id=relation_id,
        instance_id=instance_id,
        instance_hash=instance_hash,
        source_query_id=f"{instance_id}:source",
        follow_up_query_ids=tuple(
            f"{instance_id}:follow-up:{index}" for index in range(len(follow_ups))
        ),
        source_program=source,
        follow_up_programs=follow_ups,
        holes=MappingProxyType(canonical_holes),
        expected_observation_relation=expected_observation_relation,
        reset_policy=reset_policy,
        involved_lanes=tuple(sorted(set(involved_lanes))),
        emits_secret_constraints=emits_secret_constraints,
        reducer_rules=reducer_rules,
        certificate=certificate,
    )


def _instance_hash(
    relation_id: str,
    source: Program,
    follow_ups: tuple[Program, ...],
    holes: Mapping[str, int | str],
    reset_policy: str,
    involved_lanes: tuple[int, ...],
) -> str:
    data = {
        "relation_id": relation_id,
        "source": source.canonical_sha256(),
        "follow_ups": [program.canonical_sha256() for program in follow_ups],
        "holes": dict(holes),
        "reset_policy": reset_policy,
        "involved_lanes": list(involved_lanes),
    }
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cell_program(cell: Cell) -> Program:
    return _cells_program((cell,))


def _cells_program(cells: tuple[Cell, ...]) -> Program:
    instructions = tuple(item for cell in cells for item in cell.instructions())
    return Program((*instructions, Instruction.fence(), Instruction.halt()))


def _drained_repetitions_program(cell: Cell, repeats: int) -> Program:
    instructions: list[Instruction] = []
    restore = (-(cell.pad + 1 + cell.epoch)) & 0b11
    for _ in range(repeats):
        instructions.extend(cell.instructions())
        instructions.append(Instruction.fence())
        if restore:
            instructions.append(Instruction.pad(restore))
    instructions.append(Instruction.halt())
    return Program(tuple(instructions))


def _compose_history_measurement(history: Program, measurement: Program) -> Program:
    history_body = history.instructions
    if history.instructions[-1].op is Op.HALT:
        history_body = history.instructions[:-1]
    return Program((*history_body, *measurement.instructions))


def _lift_program(program: Program, prefix_pad: int, suffix_fence: bool) -> Program:
    body = program.instructions[:-1]
    prefix = () if prefix_pad == 0 else (Instruction.pad(prefix_pad),)
    suffix = (Instruction.fence(),) if suffix_fence else ()
    return Program((*prefix, *body, *suffix, Instruction.halt()))


def _program_lanes(program: Program) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                instruction.operands[0]
                for instruction in program.instructions
                if instruction.op is Op.PROBE
            }
        )
    )


def _rename_instruction(instruction: Instruction, permutation: tuple[int, ...]) -> Instruction:
    operands = list(instruction.operands)
    positions: tuple[int, ...]
    if instruction.op in {Op.MOVI, Op.MIXOUT}:
        positions = (0,)
    elif instruction.op in {Op.MOV, Op.CMP}:
        positions = (0, 1)
    elif instruction.op in {Op.ADD, Op.XOR, Op.AND, Op.OR}:
        positions = (0, 1, 2)
    elif instruction.op in {Op.SHL, Op.SHR, Op.LOAD}:
        positions = (0, 1)
    elif instruction.op is Op.STORE:
        positions = (0, 2)
    else:
        positions = ()
    for position in positions:
        operands[position] = permutation[operands[position]]
    return Instruction(instruction.op, tuple(operands))


def _int_hole(holes: Mapping[str, int | str], name: str) -> int:
    value = holes[name]
    if not isinstance(value, int):
        raise TypeError(f"relation hole {name} is not an integer")
    return value
