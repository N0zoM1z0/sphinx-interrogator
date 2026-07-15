"""Certified relational transformations and secret-fact extraction."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from sphinx_interrogator.ast import Program
from sphinx_interrogator.model import OutcomeClass, RelationEvidence


@dataclass(frozen=True, slots=True)
class RelationCertificate:
    """Machine-checkable metadata for a relation's two proof obligations."""

    certificate_id: str
    semantic_version: str
    proof_method: str
    architectural_claim: str
    fault_free_claim: str
    artifact_digest: str
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BankFact:
    """A logical equality or disequality about one projected secret bank."""

    lane: int
    token: int
    epoch: int
    bank: int
    equal: bool
    confidence: float
    source_relation_instance_id: str


@dataclass(frozen=True, slots=True)
class RelationInstance:
    """A concrete source/follow-up experiment pair with a proof certificate."""

    relation_id: str
    instance_id: str
    source_query_id: str
    follow_up_query_ids: tuple[str, ...]
    source_program: Program
    follow_up_programs: tuple[Program, ...]
    holes: Mapping[str, int]
    expected_observation_relation: str
    certificate: RelationCertificate

    def architectural_precheck(self) -> bool:
        """Check the syntactic sufficient condition used by the scaffold certificate.

        Version 1 experiment cells contain only architecture-silent probe operations,
        fences, padding, and HALT. The full implementation replaces this sufficient
        check with a bounded relational semantic proof.
        """
        return all(program_has_silent_architecture(program) for program in self.programs)

    @property
    def programs(self) -> tuple[Program, ...]:
        """Return source followed by all generated follow-ups."""
        return (self.source_program, *self.follow_up_programs)


class AnchorSwitchTemplate:
    """Change only the public anchor bank while preserving static semantics."""

    relation_id = "anchor-switch/v1"

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
        """Instantiate a relation at concrete grammar-hole values."""
        if bank_a == bank_b:
            raise ValueError("anchor-switch requires two distinct banks")
        source = Program.experiment_cell(
            lane=lane,
            token=token,
            epoch=epoch,
            anchor=bank_a,
            pad=pad,
            repeats=repeats,
        )
        follow_up = Program.experiment_cell(
            lane=lane,
            token=token,
            epoch=epoch,
            anchor=bank_b,
            pad=pad,
            repeats=repeats,
        )
        digest_input = "\0".join((self.relation_id, source.render(), follow_up.render()))
        artifact_digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
        certificate = RelationCertificate(
            certificate_id=f"cert:{artifact_digest[:16]}",
            semantic_version="0.1.0",
            proof_method="smt-bounded-complete",
            architectural_claim="final public architectural states are equal",
            fault_free_claim="normalized aggregate cycle costs are equal",
            artifact_digest=artifact_digest,
            limitations=(
                "hard facts require a certified active phase and unsuppressed replay state",
                "scaffold precheck covers architecture-silent experiment programs only",
            ),
        )
        return RelationInstance(
            relation_id=self.relation_id,
            instance_id=instance_id,
            source_query_id=f"{instance_id}:a",
            follow_up_query_ids=(f"{instance_id}:b",),
            source_program=source,
            follow_up_programs=(follow_up,),
            holes={
                "lane": lane,
                "token": token,
                "epoch": epoch,
                "bank_a": bank_a,
                "bank_b": bank_b,
                "pad": pad,
                "repeats": repeats,
            },
            expected_observation_relation="equal",
            certificate=certificate,
        )

    def extract_facts(
        self,
        relation: RelationInstance,
        evidence: RelationEvidence,
        *,
        hard_preconditions_certified: bool,
        decision_threshold: float = 0.5,
    ) -> tuple[BankFact, ...]:
        """Compile a directional violation into auditable bank facts.

        A positive delta means the follow-up using `bank_b` was slower. Under the
        certified reference-fault preconditions this entails equality with `bank_b`
        and disequality with `bank_a`; a negative delta gives the converse. Without
        those preconditions the evidence remains useful for ranking but not as a hard
        logical constraint.
        """
        if relation.relation_id != self.relation_id:
            raise ValueError("relation instance does not belong to anchor-switch/v1")
        if not hard_preconditions_certified:
            return ()
        holes = relation.holes

        def fact(bank: int, *, equal: bool) -> BankFact:
            return BankFact(
                lane=holes["lane"],
                token=holes["token"],
                epoch=holes["epoch"],
                bank=bank,
                equal=equal,
                confidence=evidence.confidence,
                source_relation_instance_id=relation.instance_id,
            )

        if evidence.normalized_delta > decision_threshold:
            return (
                fact(holes["bank_b"], equal=True),
                fact(holes["bank_a"], equal=False),
            )
        if evidence.normalized_delta < -decision_threshold:
            return (
                fact(holes["bank_a"], equal=True),
                fact(holes["bank_b"], equal=False),
            )
        if evidence.outcome is OutcomeClass.HOLDS and evidence.confidence >= 0.99:
            return (
                fact(holes["bank_a"], equal=False),
                fact(holes["bank_b"], equal=False),
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
        """Classify a normalized paired estimate into the relation outcome alphabet."""
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


def program_has_silent_architecture(program: Program) -> bool:
    """Return whether a program uses only architecture-silent experiment operations."""
    silent = {"PROBE", "ANCHOR", "PAD", "FENCE", "HALT"}
    return all(instruction.op.value in silent for instruction in program.instructions)
