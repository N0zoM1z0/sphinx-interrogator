"""TTL, novelty, implication-unknown, and deterministic frontier tests."""

from __future__ import annotations

from pathlib import Path

from sphinx_interrogator.constraint_ir import Expr, Sort
from sphinx_interrogator.frontier import (
    ActiveFrontier,
    FrontierCandidate,
    NoveltyStatus,
)
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository
from sphinx_interrogator.solver import ImplicationStatus


def _repository(tmp_path: Path) -> CampaignRepository:
    return CampaignRepository.create(
        tmp_path / "run",
        CampaignManifest(
            campaign_id="frontier-test",
            challenge_id="challenge",
            challenge_commitment="0" * 64,
            profile_name="tutorial",
            semantic_version="0.1.0",
            public_profile_sha256="3" * 64,
            seed=41,
            minimum_certificate_strength="exhaustive-enumeration",
            logical_query_budget=80,
            physical_execution_budget=240,
            hard_reset_budget=240,
        ),
    )


def _candidate(
    candidate_id: str,
    structural: str,
    *,
    score: float = 1.0,
    expires_after: int | None = None,
    semantic: bool = False,
) -> FrontierCandidate:
    return FrontierCandidate(
        candidate_id=candidate_id,
        structural_key=structural,
        relation_key=f"relation:{candidate_id}",
        state_key=f"state:{candidate_id}",
        observation_key=f"observation:{candidate_id}",
        partition_key=f"partition:{candidate_id}",
        semantic_key=f"semantic:{candidate_id}",
        score=score,
        data={"program": "HALT\n"},
        expires_after=expires_after,
        semantic_expression=Expr.literal(Sort.bool(), True) if semantic else None,
    )


def test_structural_duplicate_and_expired_candidates_are_not_appended(tmp_path: Path) -> None:
    """TTL and canonical syntax rejection leave the append-only log unchanged."""
    repository = _repository(tmp_path)
    frontier = ActiveFrontier(repository)
    first = frontier.consider(_candidate("first", "same"), logical_time=0)
    assert first.status is NoveltyStatus.NOVEL
    before = len(repository.events)
    duplicate = frontier.consider(_candidate("duplicate", "same"), logical_time=0)
    expired = frontier.consider(_candidate("expired", "new", expires_after=0), logical_time=1)
    assert duplicate.status is NoveltyStatus.DUPLICATE
    assert expired.status is NoveltyStatus.EXPIRED
    assert len(repository.events) == before
    repository.close()


def test_implication_unknown_is_not_treated_as_novelty_proof(tmp_path: Path) -> None:
    """A solver timeout defers the candidate; only a countermodel establishes novelty."""
    repository = _repository(tmp_path)
    frontier = ActiveFrontier(repository)
    candidate = _candidate("semantic", "structure-semantic", semantic=True)
    unknown = frontier.consider(
        candidate,
        logical_time=0,
        implication_check=lambda _: ImplicationStatus.UNKNOWN,
    )
    assert unknown.status is NoveltyStatus.UNKNOWN
    assert repository.database.table_count("frontier") == 0
    novel = frontier.consider(
        candidate,
        logical_time=0,
        implication_check=lambda _: ImplicationStatus.NOT_IMPLIED,
    )
    assert novel.status is NoveltyStatus.NOVEL
    assert "semantic-implication" in novel.novel_dimensions

    implied = frontier.consider(
        _candidate("implied", "other", semantic=True),
        logical_time=0,
        implication_check=lambda _: ImplicationStatus.IMPLIED,
    )
    assert implied.status is NoveltyStatus.DUPLICATE
    assert repository.database.table_count("frontier") == 1
    repository.close()


def test_selection_uses_score_then_stable_id_and_filters_elapsed_ttl(tmp_path: Path) -> None:
    """Selection is replayable and does not return stale history-sensitive queries."""
    repository = _repository(tmp_path)
    frontier = ActiveFrontier(repository)
    frontier.consider(_candidate("z-last", "s-z", score=5.0), logical_time=0)
    frontier.consider(
        _candidate("a-first", "s-a", score=5.0, expires_after=0),
        logical_time=0,
    )
    assert frontier.select(logical_time=0).candidate_id == "a-first"  # type: ignore[union-attr]
    assert frontier.select(logical_time=1).candidate_id == "z-last"  # type: ignore[union-attr]
    repository.close()
