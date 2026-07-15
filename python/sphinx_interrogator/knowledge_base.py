"""Persistent graph-shaped knowledge base for interrogation testing."""

from __future__ import annotations

from dataclasses import dataclass, field

from sphinx_interrogator.model import ExecutionResult, RelationEvidence
from sphinx_interrogator.relations import BankFact, RelationInstance


@dataclass(frozen=True, slots=True)
class QueryRecord:
    """One logical query and all physical execution responses collected for it."""

    query_id: str
    program_text: str
    results: tuple[ExecutionResult, ...]
    created_at_step: int
    expires_after_step: int | None = None

    def is_live(self, step: int) -> bool:
        """Return whether history-sensitive evidence remains valid at `step`."""
        return self.expires_after_step is None or step <= self.expires_after_step


@dataclass(frozen=True, slots=True)
class RelationRecord:
    """A relation edge, tested evidence, and facts derived from that evidence."""

    instance: RelationInstance
    evidence: RelationEvidence
    derived_facts: tuple[BankFact, ...]


@dataclass(slots=True)
class InterrogationKnowledgeBase:
    """Append-oriented store retaining queries, relation edges, and provenance."""

    queries: dict[str, QueryRecord] = field(default_factory=dict)
    relations: dict[str, RelationRecord] = field(default_factory=dict)
    facts: list[BankFact] = field(default_factory=list)
    step: int = 0

    def add_query(self, record: QueryRecord) -> None:
        """Add a query node while rejecting accidental identifier reuse."""
        if record.query_id in self.queries:
            raise ValueError(f"duplicate query id {record.query_id}")
        self.queries[record.query_id] = record

    def add_relation(self, record: RelationRecord) -> None:
        """Add one tested relation and retain its constraint provenance."""
        instance_id = record.instance.instance_id
        if instance_id in self.relations:
            raise ValueError(f"duplicate relation instance id {instance_id}")
        referenced = (
            record.instance.source_query_id,
            *record.instance.follow_up_query_ids,
        )
        missing = [query_id for query_id in referenced if query_id not in self.queries]
        if missing:
            raise ValueError(f"relation references missing queries: {missing}")
        self.relations[instance_id] = record
        self.facts.extend(record.derived_facts)

    def advance(self) -> None:
        """Advance the logical campaign clock by one interrogation round."""
        self.step += 1

    def live_query_ids(self) -> tuple[str, ...]:
        """Return query identifiers whose state-sensitive evidence has not expired."""
        return tuple(
            query_id for query_id, record in self.queries.items() if record.is_live(self.step)
        )

    def response_diversity(self, query_id: str) -> int:
        """Count distinct coarse responses retained for a logical query."""
        record = self.queries[query_id]
        signatures = {
            (
                result.status,
                result.public_digest,
                result.observation.cycle_bucket,
                result.observation.bucket_width,
            )
            for result in record.results
        }
        return len(signatures)

    def facts_for_relation(self, instance_id: str) -> tuple[BankFact, ...]:
        """Return facts derived from a named relation with provenance intact."""
        return self.relations[instance_id].derived_facts
