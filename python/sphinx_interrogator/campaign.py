"""Interrogation loop scaffolding with auditable relation provenance."""

from __future__ import annotations

from dataclasses import replace

from sphinx_interrogator.knowledge_base import (
    InterrogationKnowledgeBase,
    QueryRecord,
    RelationRecord,
)
from sphinx_interrogator.model import RelationEvidence
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.relations import AnchorSwitchTemplate, RelationInstance
from sphinx_interrogator.solver import BankEqualityConstraint, SecretDomain
from sphinx_interrogator.statistics import bucket_midpoint, paired_location
from sphinx_interrogator.synthesis import GrammarGuidedSelector, QueryCandidate


class AnchorSwitchRunner:
    """Execute, classify, and record one anchor-switch relation instance."""

    def __init__(self, client: VmClient, knowledge_base: InterrogationKnowledgeBase) -> None:
        """Bind a public protocol client and campaign knowledge base."""
        self._client = client
        self._knowledge_base = knowledge_base
        self._template = AnchorSwitchTemplate()

    def run(
        self,
        relation: RelationInstance,
        *,
        samples: int,
        reset: str,
        hard_preconditions_certified: bool,
    ) -> RelationEvidence:
        """Collect interleaved paired samples and compile certified violations."""
        if samples < 1:
            raise ValueError("samples must be positive")
        if len(relation.follow_up_programs) != 1:
            raise ValueError("anchor-switch scaffold expects exactly one follow-up")
        source_results = []
        follow_up_results = []
        batch_id = f"batch:{relation.instance_id}"
        for index in range(samples):
            seed = f"{relation.instance_id}:{index}"
            source_results.append(
                self._client.execute(
                    relation.source_program.render(),
                    session_id=f"{relation.instance_id}:source",
                    logical_batch_id=batch_id,
                    reset=reset,
                    execution_seed_id=seed,
                )
            )
            follow_up_results.append(
                self._client.execute(
                    relation.follow_up_programs[0].render(),
                    session_id=f"{relation.instance_id}:follow-up",
                    logical_batch_id=batch_id,
                    reset=reset,
                    execution_seed_id=seed,
                )
            )
        source_values = [
            bucket_midpoint(result.observation.cycle_bucket, result.observation.bucket_width)
            for result in source_results
        ]
        follow_up_values = [
            bucket_midpoint(result.observation.cycle_bucket, result.observation.bucket_width)
            for result in follow_up_results
        ]
        estimate = paired_location(source_values, follow_up_values)
        request_ids = tuple(
            result.request_id
            for pair in zip(source_results, follow_up_results, strict=True)
            for result in pair
        )
        evidence = self._template.classify(
            relation.instance_id,
            estimate.location,
            confidence=estimate.confidence,
            source_request_ids=request_ids,
        )
        source_record = QueryRecord(
            query_id=relation.source_query_id,
            program_text=relation.source_program.render(),
            results=tuple(source_results),
            created_at_step=self._knowledge_base.step,
        )
        follow_up_record = QueryRecord(
            query_id=relation.follow_up_query_ids[0],
            program_text=relation.follow_up_programs[0].render(),
            results=tuple(follow_up_results),
            created_at_step=self._knowledge_base.step,
        )
        self._knowledge_base.add_query(source_record)
        self._knowledge_base.add_query(follow_up_record)
        facts = self._template.extract_facts(
            relation,
            evidence,
            hard_preconditions_certified=hard_preconditions_certified,
        )
        self._knowledge_base.add_relation(
            RelationRecord(instance=relation, evidence=evidence, derived_facts=facts)
        )
        self._knowledge_base.advance()
        return evidence


class TutorialCampaign:
    """Small exact-mode campaign demonstrating the intended closed loop.

    The complete Codex task replaces this reference loop with persisted campaigns,
    MaxSMT, richer relation families, explicit query budgets, and mutation tests.
    """

    def __init__(self, client: VmClient, cells: int) -> None:
        """Create a tutorial campaign for identity-mapped four-bit cells."""
        self.knowledge_base = InterrogationKnowledgeBase()
        self.domain = SecretDomain(cells)
        self._selector = GrammarGuidedSelector()
        self._runner = AnchorSwitchRunner(client, self.knowledge_base)
        self._template = AnchorSwitchTemplate()
        self._used: list[QueryCandidate] = []

    def step(self) -> RelationEvidence | None:
        """Synthesize and execute one hard-reset exact relation query."""
        scored = self._selector.choose(self.domain, used=self._used)
        if scored is None:
            return None
        candidate = scored.query
        active_pad = (candidate.lane ^ candidate.token ^ candidate.epoch) & 0b11
        candidate = replace(candidate, pad=active_pad)
        instance_id = f"tutorial:{len(self._used)}"
        relation = self._template.instantiate(
            instance_id=instance_id,
            lane=candidate.lane,
            token=candidate.token,
            epoch=candidate.epoch,
            bank_a=candidate.bank_a,
            bank_b=candidate.bank_b,
            pad=candidate.pad,
            repeats=candidate.repeats,
        )
        evidence = self._runner.run(
            relation,
            samples=3,
            reset="hard",
            hard_preconditions_certified=True,
        )
        self._used.extend(replace(candidate, pad=pad) for pad in range(4))
        constraints = (
            BankEqualityConstraint.from_fact(fact)
            for fact in self.knowledge_base.facts_for_relation(instance_id)
        )
        self.domain.apply_all(constraints)
        return evidence

    def run(self, maximum_steps: int = 128) -> tuple[int, ...] | None:
        """Run until uniqueness, no novel query, or the explicit step budget ends."""
        if maximum_steps < 1:
            raise ValueError("maximum_steps must be positive")
        for _ in range(maximum_steps):
            unique = self.domain.unique_secret()
            if unique is not None:
                return unique
            evidence = self.step()
            if evidence is None:
                return None
        return self.domain.unique_secret()
