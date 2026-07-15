"""Shared immutable models for public observations and inference evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class OutcomeClass(StrEnum):
    """Classification of a tested observation relation."""

    HOLDS = "holds"
    VIOLATED_POSITIVE = "violated_positive"
    VIOLATED_NEGATIVE = "violated_negative"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    """Public timing observation for one physical execution."""

    cycle_bucket: int
    bucket_width: int
    samples_in_vm: int = 1

    @property
    def lower_cycle_bound(self) -> int:
        """Return the inclusive lower bound represented by the bucket."""
        return self.cycle_bucket * self.bucket_width

    @property
    def upper_cycle_bound(self) -> int:
        """Return the inclusive upper bound represented by the bucket."""
        return (self.cycle_bucket + 1) * self.bucket_width - 1


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Typed subset of an `execute_result` protocol message."""

    request_id: str
    session_id: str
    status: str
    public_digest: str
    observation: ExecutionObservation
    retired_instructions: int
    static_cycles: int
    physical_executions_used: int
    physical_executions_remaining: int
    logical_queries_used: int
    logical_queries_remaining: int
    hard_resets_used: int
    hard_resets_remaining: int
    server_version: str
    profile_version: str


@dataclass(frozen=True, slots=True)
class RelationEvidence:
    """Auditable result of testing one certified relation instance."""

    relation_instance_id: str
    outcome: OutcomeClass
    normalized_delta: float
    confidence: float
    source_request_ids: tuple[str, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    """Finite summary of the current secret hypothesis space."""

    exact_count: int | None
    lane_domains: tuple[frozenset[int], ...]
    unique_secret_hex: str | None
