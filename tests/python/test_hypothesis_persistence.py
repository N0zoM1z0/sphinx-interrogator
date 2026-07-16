"""Durable IR replay, exact uniqueness, snapshots, and rollback tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sphinx_interrogator.constraints import (
    ApproximationKind,
    FiniteModelAssignment,
    FiniteModelConstraint,
)
from sphinx_interrogator.hypothesis_persistence import CampaignHypotheses
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository
from sphinx_interrogator.solver import (
    ConstraintGroup,
    GroupState,
    SolverStatus,
    finite_model_program,
)


def _repository(tmp_path: Path) -> CampaignRepository:
    repository = CampaignRepository.create(
        tmp_path / "run",
        CampaignManifest(
            campaign_id="hypothesis-test",
            challenge_id="challenge",
            challenge_commitment="0" * 64,
            profile_name="tutorial",
            semantic_version="0.1.0",
            public_profile_sha256="4" * 64,
            seed=43,
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
    repository.append_event(
        event_id="batch:b1",
        kind="batch_scheduled",
        logical_time=0,
        payload={
            "batch_id": "b1",
            "seed": 43,
            "schedule": ["source", "follow-up"],
            "status": "complete",
        },
    )
    for position, request_id in enumerate(("request-source", "request-follow-up")):
        request = json.dumps(
            {
                "protocol_version": "1.0",
                "request_id": request_id,
                "kind": "execute",
            }
        )
        response = json.dumps(
            {
                "protocol_version": "1.0",
                "request_id": request_id,
                "kind": "execute_result",
                "ok": True,
            }
        )
        repository.record_raw_execution(
            execution_id=f"execution-{position}",
            query_id="q1",
            batch_id="b1",
            position=position,
            request_line=request,
            response_line=response,
            logical_time=1,
        )
    repository.append_event(
        event_id="certificate:cert-1",
        kind="certificate_registered",
        logical_time=2,
        payload={"certificate_id": "cert-1", "certificate": {"fixture": True}},
    )
    repository.append_event(
        event_id="relation:relation-1",
        kind="relation_recorded",
        logical_time=2,
        payload={
            "relation_instance_id": "relation-1",
            "relation_id": "anchor-switch/v1",
            "certificate_id": "cert-1",
            "relation": {"fixture": True},
        },
    )
    return repository


def _constraint(identifier: str, secret: int) -> FiniteModelConstraint:
    return FiniteModelConstraint(
        constraint_version="1.0",
        constraint_id=identifier,
        lanes=(0,),
        allowed_models=(FiniteModelAssignment((secret,), "reference"),),
        approximation=ApproximationKind.EXACT,
        relation_instance_id="relation-1",
        certificate_id="cert-1",
        decision_kind="exact_greater",
        source_request_ids=("request-source", "request-follow-up"),
        assumptions=("hard reset",),
    )


def test_persisted_constraint_replays_to_same_unique_model_and_snapshot(tmp_path: Path) -> None:
    """Canonical IR, not a Z3 object, reconstructs exact state after restart."""
    repository = _repository(tmp_path)
    hypotheses = CampaignHypotheses(repository)
    hypotheses.add_finite_constraint(
        _constraint("constraint:111111111111111111111111", 9),
        secret_cells=1,
        logical_time=3,
    )
    result = hypotheses.solve()
    assert result.status is SolverStatus.SAT
    assert result.model is not None
    assert result.model.get("secret_0") == 9
    uniqueness = hypotheses.check_uniqueness(1)
    assert uniqueness.status is SolverStatus.UNSAT
    assert uniqueness.unique is True
    snapshot = hypotheses.snapshot(snapshot_id="snapshot-1", logical_time=4, limit=16)
    assert snapshot.exact_count == 1
    assert repository.database.table_count("candidate_snapshots") == 1
    original_digest = repository.database.digest()
    repository.close()

    reopened = CampaignRepository.open(tmp_path / "run")
    replayed = CampaignHypotheses(reopened)
    assert replayed.solve().model == result.model
    assert reopened.rebuild() == original_digest
    rebuilt = CampaignHypotheses(reopened)
    assert rebuilt.solve().model == result.model
    reopened.close()


def test_unsat_core_quarantine_and_retraction_survive_replay(tmp_path: Path) -> None:
    """Rollback changes only active state; both contradictory evidence records remain."""
    repository = _repository(tmp_path)
    hypotheses = CampaignHypotheses(repository)
    first_id = "constraint:111111111111111111111111"
    second_id = "constraint:222222222222222222222222"
    hypotheses.add_finite_constraint(_constraint(first_id, 1), secret_cells=1, logical_time=3)
    hypotheses.add_finite_constraint(_constraint(second_id, 2), secret_cells=1, logical_time=3)
    inconsistent = hypotheses.solve()
    assert inconsistent.status is SolverStatus.UNSAT
    assert hypotheses.quarantine_core(inconsistent, logical_time=4) == (first_id, second_id)
    assert hypotheses.solve().status is SolverStatus.SAT
    hypotheses.reactivate(first_id, logical_time=5)
    assert hypotheses.solve().model is not None
    hypotheses.retract(first_id, logical_time=6)
    assert hypotheses.store.state(first_id) is GroupState.RETRACTED
    assert repository.database.active_constraint_ids() == ()
    assert repository.database.table_count("constraints") == 2
    repository.close()

    reopened = CampaignRepository.open(tmp_path / "run")
    replayed = CampaignHypotheses(reopened)
    assert replayed.store.state(first_id) is GroupState.RETRACTED
    assert replayed.store.state(second_id) is GroupState.QUARANTINED
    assert replayed.solve().status is SolverStatus.SAT
    reopened.close()


def test_high_influence_soft_replay_quarantines_repairs_and_persists(tmp_path: Path) -> None:
    """Failed replay disables one soft group; reviewed reproduction safely repairs it."""
    repository = _repository(tmp_path)
    hypotheses = CampaignHypotheses(repository)
    constraint = _constraint("constraint:333333333333333333333333", 6)
    group = ConstraintGroup(
        constraint.constraint_id,
        finite_model_program(constraint, secret_cells=1),
        hard=False,
        weight=9,
        provenance=("correlation:block-1", "correlation:block-2"),
    )
    hypotheses.add_group(
        constraint_id=constraint.constraint_id,
        group=group,
        relation_instance_id=constraint.relation_instance_id,
        certificate_id=constraint.certificate_id,
        source_request_ids=constraint.source_request_ids,
        approximation="probabilistic-soft",
        logical_time=3,
    )
    assert hypotheses.store.high_influence_soft_groups(limit=1) == (group,)
    assert (
        hypotheses.review_replay(
            group.group_id,
            reproduced=False,
            logical_time=4,
            replay_request_ids=("replay-failed-a", "replay-failed-b"),
        )
        is GroupState.QUARANTINED
    )
    assert hypotheses.store.high_influence_soft_groups(limit=1) == ()
    assert (
        hypotheses.review_replay(
            group.group_id,
            reproduced=True,
            logical_time=5,
            replay_request_ids=("replay-passed-a", "replay-passed-b"),
        )
        is GroupState.ACTIVE
    )
    repository.close()

    reopened = CampaignRepository.open(tmp_path / "run")
    replayed = CampaignHypotheses(reopened)
    assert replayed.store.state(group.group_id) is GroupState.ACTIVE
    state_events = tuple(
        event for event in reopened.events if event.kind == "constraint_state_changed"
    )
    assert state_events[-2].payload["reason"].startswith("high-influence replay disagreed")
    assert state_events[-1].payload["reason"] == (
        "reviewed replay reproduced the declared evidence"
    )
    reopened.close()
