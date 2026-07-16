"""TTL-aware multidimensional novelty and deterministic frontier selection."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from sphinx_interrogator.constraint_ir import Expr
from sphinx_interrogator.persistence import CampaignRepository
from sphinx_interrogator.solver import ImplicationStatus


class NoveltyStatus(StrEnum):
    """Outcome of testing one candidate against active campaign knowledge."""

    NOVEL = "novel"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class FrontierCandidate:
    """One public query/relation candidate with explicit novelty projections."""

    candidate_id: str
    structural_key: str
    relation_key: str
    state_key: str
    observation_key: str
    partition_key: str
    semantic_key: str
    score: float
    data: Mapping[str, object]
    expires_after: int | None = None
    semantic_expression: Expr | None = None

    def __post_init__(self) -> None:
        keys = (
            self.candidate_id,
            self.structural_key,
            self.relation_key,
            self.state_key,
            self.observation_key,
            self.partition_key,
            self.semantic_key,
        )
        if any(not key for key in keys):
            raise ValueError("frontier candidate IDs/keys must not be empty")
        if self.expires_after is not None and self.expires_after < 0:
            raise ValueError("frontier TTL must be nonnegative")
        if not math.isfinite(self.score):
            raise ValueError("frontier candidate score must be finite")


@dataclass(frozen=True, slots=True)
class NoveltyDecision:
    """Auditable acceptance/rejection with each novel projection named."""

    status: NoveltyStatus
    candidate_id: str
    novel_dimensions: tuple[str, ...]
    implication: ImplicationStatus | None
    reason: str


class ActiveFrontier:
    """Persist candidates only after structural and semantic novelty checks."""

    def __init__(self, repository: CampaignRepository) -> None:
        self.repository = repository

    def consider(
        self,
        candidate: FrontierCandidate,
        *,
        logical_time: int,
        implication_check: Callable[[Expr], ImplicationStatus] | None = None,
    ) -> NoveltyDecision:
        """Classify and append a candidate; solver unknown defers rather than proves."""
        if logical_time < 0:
            raise ValueError("frontier logical time must be nonnegative")
        if candidate.expires_after is not None and candidate.expires_after < logical_time:
            return NoveltyDecision(
                NoveltyStatus.EXPIRED,
                candidate.candidate_id,
                (),
                None,
                "candidate TTL elapsed before insertion",
            )
        rows = self.repository.database.active_frontier(logical_time)
        existing_ids = {cast("str", row["candidate_id"]) for row in rows}
        if candidate.candidate_id in existing_ids:
            return NoveltyDecision(
                NoveltyStatus.DUPLICATE,
                candidate.candidate_id,
                (),
                None,
                "candidate ID already exists in the active frontier",
            )
        if any(row["structural_key"] == candidate.structural_key for row in rows):
            return NoveltyDecision(
                NoveltyStatus.DUPLICATE,
                candidate.candidate_id,
                (),
                None,
                "canonical program structure is already active",
            )

        implication: ImplicationStatus | None = None
        if candidate.semantic_expression is not None:
            if implication_check is None:
                raise ValueError("semantic expression requires an implication checker")
            implication = implication_check(candidate.semantic_expression)
            if implication is ImplicationStatus.UNKNOWN:
                return NoveltyDecision(
                    NoveltyStatus.UNKNOWN,
                    candidate.candidate_id,
                    (),
                    implication,
                    "semantic implication timed out or was unknown; novelty is unproven",
                )
            if implication is ImplicationStatus.IMPLIED:
                return NoveltyDecision(
                    NoveltyStatus.DUPLICATE,
                    candidate.candidate_id,
                    (),
                    implication,
                    "active hard constraints already imply the candidate semantics",
                )

        dimensions = ["structural"]
        for dimension, column, value in (
            ("relation", "relation_key", candidate.relation_key),
            ("state", "state_key", candidate.state_key),
            ("observation", "observation_key", candidate.observation_key),
            ("partition", "partition_key", candidate.partition_key),
            ("semantic-key", "semantic_key", candidate.semantic_key),
        ):
            if all(row[column] != value for row in rows):
                dimensions.append(dimension)
        if implication is ImplicationStatus.NOT_IMPLIED:
            dimensions.append("semantic-implication")
        self.repository.append_event(
            event_id=f"frontier:{candidate.candidate_id}",
            kind="frontier_candidate",
            logical_time=logical_time,
            payload={
                "candidate_id": candidate.candidate_id,
                "structural_key": candidate.structural_key,
                "relation_key": candidate.relation_key,
                "state_key": candidate.state_key,
                "observation_key": candidate.observation_key,
                "partition_key": candidate.partition_key,
                "semantic_key": candidate.semantic_key,
                "score": candidate.score,
                "expires_after": candidate.expires_after,
                "candidate": dict(candidate.data),
            },
        )
        return NoveltyDecision(
            NoveltyStatus.NOVEL,
            candidate.candidate_id,
            tuple(dimensions),
            implication,
            "candidate adds at least one active novelty projection",
        )

    def select(self, *, logical_time: int) -> FrontierCandidate | None:
        """Select highest score with candidate ID as the deterministic tie-break."""
        rows = self.repository.database.active_frontier(logical_time)
        if not rows:
            return None
        return _candidate_from_row(rows[0])


def _candidate_from_row(row: sqlite3.Row) -> FrontierCandidate:
    decoded: object = json.loads(cast("str", row["data_json"]))
    if not isinstance(decoded, dict):
        raise ValueError("materialized frontier candidate data is not an object")
    return FrontierCandidate(
        candidate_id=cast("str", row["candidate_id"]),
        structural_key=cast("str", row["structural_key"]),
        relation_key=cast("str", row["relation_key"]),
        state_key=cast("str", row["state_key"]),
        observation_key=cast("str", row["observation_key"]),
        partition_key=cast("str", row["partition_key"]),
        semantic_key=cast("str", row["semantic_key"]),
        score=float(row["score"]),
        data=cast("dict[str, object]", decoded),
        expires_after=cast("int | None", row["expires_after"]),
    )
