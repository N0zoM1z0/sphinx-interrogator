"""Deterministic scheduling and write-ahead harness tests."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import pytest

from sphinx_interrogator.harness import (
    DurableExecutionHarness,
    ExecutionSpec,
    FakeEndpoint,
    RepositoryWireRecorder,
    balanced_pair_schedule,
)
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository


def _repository(tmp_path: Path) -> CampaignRepository:
    repository = CampaignRepository.create(
        tmp_path / "run",
        CampaignManifest(
            campaign_id="harness-test",
            challenge_id="challenge",
            profile_name="tutorial",
            semantic_version="0.1.0",
            public_profile_sha256="2" * 64,
            seed=29,
            minimum_certificate_strength="exhaustive-enumeration",
            logical_query_budget=80,
            physical_execution_budget=240,
            hard_reset_budget=240,
        ),
    )
    repository.append_event(
        event_id="query:q1",
        kind="query_created",
        logical_time=0,
        payload={
            "query_id": "q1",
            "program_sha256": hashlib.sha256(b"HALT\n").hexdigest(),
            "program_text": "HALT\n",
            "expires_after": None,
        },
    )
    schedule = balanced_pair_schedule(("relation-1",), repetitions=2, seed=29)
    repository.append_event(
        event_id="batch:b1",
        kind="batch_scheduled",
        logical_time=0,
        payload={
            "batch_id": "b1",
            "seed": 29,
            "schedule": [item.to_data() for item in schedule],
            "status": "scheduled",
        },
    )
    return repository


def _spec(execution_id: str, position: int) -> ExecutionSpec:
    return ExecutionSpec(
        execution_id=execution_id,
        query_id="q1",
        batch_id="b1",
        position=position,
        program="HALT\n",
        session_id="session-1",
        reset="hard",
        logical_time=1,
        execution_seed_id=f"seed-{position}",
    )


def test_balanced_schedule_is_seeded_correlated_and_exactly_balanced() -> None:
    """Each pair/repetition has both arms while random order remains replayable."""
    left = balanced_pair_schedule(("a", "b", "c"), repetitions=7, seed=31)
    right = balanced_pair_schedule(("a", "b", "c"), repetitions=7, seed=31)
    different = balanced_pair_schedule(("a", "b", "c"), repetitions=7, seed=32)
    assert left == right
    assert left != different
    counts = Counter((item.pair_id, item.arm) for item in left)
    assert counts == Counter({(pair, arm): 7 for pair in "abc" for arm in ("source", "follow_up")})
    for pair_id in "abc":
        for repetition in range(7):
            group = [
                item for item in left if item.pair_id == pair_id and item.repetition == repetition
            ]
            assert {item.arm for item in group} == {"source", "follow_up"}
            assert len({item.correlation_group for item in group}) == 1


def test_fake_endpoint_uses_the_same_raw_and_resume_path(tmp_path: Path) -> None:
    """The unit fake records exact public lines and never bypasses durable evidence."""
    repository = _repository(tmp_path)
    endpoint = FakeEndpoint(RepositoryWireRecorder(repository), buckets=(4, 5))
    harness = DurableExecutionHarness(repository, endpoint)
    assert harness.execute(_spec("execution-0", 0)).observation.cycle_bucket == 4
    assert harness.execute(_spec("execution-1", 1)).observation.cycle_bucket == 5
    assert endpoint.calls == ["execution-0", "execution-1"]
    assert repository.database.table_count("executions") == 2
    assert repository.raw.get("execution-0") is not None
    repository.close()


def test_recorder_crash_resumes_from_raw_without_calling_endpoint_again(tmp_path: Path) -> None:
    """A failure after response fsync cannot duplicate a physical execution on resume."""
    repository = _repository(tmp_path)

    def injected_crash() -> None:
        raise RuntimeError("crash after wire record")

    first_endpoint = FakeEndpoint(
        RepositoryWireRecorder(repository, after_raw=injected_crash),
        buckets=(9,),
    )
    first = DurableExecutionHarness(repository, first_endpoint)
    with pytest.raises(RuntimeError, match="crash after wire"):
        first.execute(_spec("execution-0", 0))
    assert first_endpoint.calls == ["execution-0"]
    assert repository.raw.get("execution-0") is not None
    assert repository.database.table_count("executions") == 0
    repository.close()

    resumed_repository = CampaignRepository.open(tmp_path / "run")
    unused_endpoint = FakeEndpoint(
        RepositoryWireRecorder(resumed_repository),
        buckets=(99,),
    )
    resumed = DurableExecutionHarness(resumed_repository, unused_endpoint)
    result = resumed.execute(_spec("execution-0", 0))
    assert result.observation.cycle_bucket == 9
    assert unused_endpoint.calls == []
    assert resumed_repository.database.table_count("executions") == 1
    resumed_repository.close()


def test_transport_failure_creates_neither_raw_nor_oracle_evidence(tmp_path: Path) -> None:
    """An endpoint error remains a transport error and cannot become an observation."""
    repository = _repository(tmp_path)

    class FailingEndpoint:
        def execute(self, *args: object, **kwargs: object):
            del args, kwargs
            raise TimeoutError("fake transport timeout")

    harness = DurableExecutionHarness(repository, FailingEndpoint())  # type: ignore[arg-type]
    with pytest.raises(TimeoutError, match="transport timeout"):
        harness.execute(_spec("execution-timeout", 0))
    assert repository.raw.get("execution-timeout") is None
    assert repository.database.table_count("executions") == 0
    repository.close()
