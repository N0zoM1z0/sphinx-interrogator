"""Durable constraint-group replay and solver snapshot orchestration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from sphinx_interrogator.constraint_ir import ConstraintProgram
from sphinx_interrogator.constraints import FiniteModelConstraint
from sphinx_interrogator.learner import LearnedMealyMachine
from sphinx_interrogator.persistence import CampaignRepository, PersistenceError
from sphinx_interrogator.solver import (
    CandidateSnapshot,
    ConstraintGroup,
    GroupState,
    HypothesisStore,
    ModelAssignment,
    SolveResult,
    UniquenessResult,
    finite_model_program,
)


class CampaignHypotheses:
    """Keep durable IR groups and the disposable Z3 hypothesis store synchronized."""

    def __init__(
        self,
        repository: CampaignRepository,
        *,
        timeout_ms: int = 5_000,
    ) -> None:
        self.repository = repository
        self.store = HypothesisStore(timeout_ms=timeout_ms)
        self._load()

    def add_finite_constraint(
        self,
        constraint: FiniteModelConstraint,
        *,
        secret_cells: int,
        logical_time: int,
    ) -> ConstraintGroup:
        """Compile, persist, and activate one provenance-rich finite relation."""
        program = finite_model_program(constraint, secret_cells=secret_cells)
        group = ConstraintGroup(
            constraint.constraint_id,
            program,
            hard=True,
            provenance=(
                *constraint.source_request_ids,
                f"relation:{constraint.relation_instance_id}",
                f"certificate:{constraint.certificate_id}",
            ),
        )
        self.add_group(
            constraint_id=constraint.constraint_id,
            group=group,
            relation_instance_id=constraint.relation_instance_id,
            certificate_id=constraint.certificate_id,
            source_request_ids=constraint.source_request_ids,
            approximation=constraint.approximation.value,
            logical_time=logical_time,
        )
        return group

    def add_group(
        self,
        *,
        constraint_id: str,
        group: ConstraintGroup,
        relation_instance_id: str,
        certificate_id: str,
        source_request_ids: tuple[str, ...],
        approximation: str,
        logical_time: int,
    ) -> None:
        """Persist project IR before adding it to the in-memory solver."""
        if constraint_id != group.group_id:
            raise ValueError("persisted M4 constraints require group_id == constraint_id")
        self.repository.append_event(
            event_id=f"constraint:{constraint_id}",
            kind="constraint_added",
            logical_time=logical_time,
            payload={
                "constraint_id": constraint_id,
                "group_id": group.group_id,
                "relation_instance_id": relation_instance_id,
                "certificate_id": certificate_id,
                "source_request_ids": list(source_request_ids),
                "approximation": approximation,
                "constraint": {
                    "ir_program": group.program.to_data(),
                    "hard": group.hard,
                    "weight": group.weight,
                    "provenance": list(group.provenance),
                },
            },
        )
        self.store.add(group)

    def solve(self) -> SolveResult:
        """Solve active persisted groups."""
        return self.store.solve()

    def snapshot(
        self,
        *,
        snapshot_id: str,
        logical_time: int,
        limit: int = 65_536,
    ) -> CandidateSnapshot:
        """Compute and durably record an exact/sampled candidate snapshot."""
        snapshot = self.store.snapshot(limit=limit)
        unique_hex = _secret_hex(snapshot.unique_model)
        self.repository.append_event(
            event_id=f"snapshot:{snapshot_id}",
            kind="candidate_snapshot",
            logical_time=logical_time,
            payload={
                "snapshot_id": snapshot_id,
                "solver_status": snapshot.solver_status.value,
                "exact_count": snapshot.exact_count,
                "unique_secret_hex": unique_hex,
                "snapshot": snapshot.to_data(),
            },
        )
        return snapshot

    def check_uniqueness(self, secret_cells: int) -> UniquenessResult:
        """Run the explicit alternative-model query over ordered secret cells."""
        if secret_cells < 1:
            raise ValueError("secret_cells must be positive")
        return self.store.check_uniqueness(tuple(f"secret_{lane}" for lane in range(secret_cells)))

    def quarantine_core(self, result: SolveResult, *, logical_time: int) -> tuple[str, ...]:
        """Quarantine named unsat-core groups in both solver and durable state."""
        groups = self.store.quarantine_unsat_core(result.unsat_core)
        for group_id in groups:
            self._record_state(group_id, GroupState.QUARANTINED, logical_time)
        return groups

    def quarantine(self, group_id: str, *, logical_time: int, reason: str) -> None:
        """Persistently disable one high-influence group after failed replay/review."""
        if not reason:
            raise ValueError("quarantine requires an auditable reason")
        self.store.quarantine(group_id)
        self._record_state(group_id, GroupState.QUARANTINED, logical_time, reason=reason)

    def retract(self, group_id: str, *, logical_time: int) -> None:
        """Retract a persisted group without deleting its event/provenance."""
        self.store.retract(group_id)
        self._record_state(group_id, GroupState.RETRACTED, logical_time)

    def reactivate(self, group_id: str, *, logical_time: int) -> None:
        """Reactivate a reviewed quarantine in solver and materialized state."""
        self.store.reactivate(group_id)
        self._record_state(
            group_id,
            GroupState.ACTIVE,
            logical_time,
            reason="reviewed replay reproduced the declared evidence",
        )

    def review_replay(
        self,
        group_id: str,
        *,
        reproduced: bool,
        logical_time: int,
        replay_request_ids: tuple[str, ...],
    ) -> GroupState:
        """Quarantine a failed high-influence replay or reactivate a reviewed one."""
        if not replay_request_ids or any(not request_id for request_id in replay_request_ids):
            raise ValueError("replay review requires public request provenance")
        if reproduced:
            if self.store.state(group_id) is GroupState.QUARANTINED:
                self.reactivate(group_id, logical_time=logical_time)
            return self.store.state(group_id)
        self.quarantine(
            group_id,
            logical_time=logical_time,
            reason="high-influence replay disagreed: " + ",".join(replay_request_ids),
        )
        return GroupState.QUARANTINED

    def record_state_model(
        self,
        model: LearnedMealyMachine,
        *,
        logical_time: int,
    ) -> None:
        """Persist one learned state-model artifact and its digest."""
        self.repository.append_event(
            event_id=f"state-model:{model.model_id}:{logical_time}",
            kind="state_model_recorded",
            logical_time=logical_time,
            payload={
                "state_model_id": model.model_id,
                "status": model.status,
                "artifact_digest": model.artifact_digest(),
                "model": model.to_data(),
            },
        )

    def retract_state_model_constraints(
        self,
        state_model_id: str,
        *,
        logical_time: int,
        reason: str,
    ) -> tuple[str, ...]:
        """Retract every active group conditioned on an invalidated state model."""
        if not state_model_id or not reason:
            raise ValueError("state-model retraction requires an ID and reason")
        marker = f"state-model:{state_model_id}"
        retracted: list[str] = []
        for group in self.store.groups:
            if marker not in group.provenance:
                continue
            if self.store.state(group.group_id) is GroupState.RETRACTED:
                continue
            self.store.retract(group.group_id)
            self._record_state(
                group.group_id,
                GroupState.RETRACTED,
                logical_time,
                reason=f"state model {state_model_id} invalidated: {reason}",
            )
            retracted.append(group.group_id)
        return tuple(sorted(retracted))

    def _record_state(
        self,
        group_id: str,
        state: GroupState,
        logical_time: int,
        *,
        reason: str | None = None,
    ) -> None:
        payload: dict[str, object] = {"constraint_id": group_id, "state": state.value}
        if reason is not None:
            payload["reason"] = reason
        self.repository.append_event(
            event_id=f"constraint-state:{group_id}:{logical_time}:{state.value}",
            kind="constraint_state_changed",
            logical_time=logical_time,
            payload=payload,
        )

    def _load(self) -> None:
        rows = self.repository.database.connection.execute(
            "SELECT constraint_id, group_id, data_json, state "
            "FROM constraints ORDER BY constraint_id"
        )
        for row in rows:
            constraint_id = cast("str", row["constraint_id"])
            group_id = cast("str", row["group_id"])
            if constraint_id != group_id:
                raise PersistenceError("persisted constraint/group identity mismatch")
            try:
                decoded: object = json.loads(cast("str", row["data_json"]))
            except json.JSONDecodeError as error:
                raise PersistenceError("persisted constraint IR is invalid JSON") from error
            if not isinstance(decoded, dict):
                raise PersistenceError("persisted constraint IR wrapper must be an object")
            group = _group_from_data(group_id, cast("dict[str, object]", decoded))
            self.store.add(group)
            state = GroupState(cast("str", row["state"]))
            if state is GroupState.QUARANTINED:
                self.store.quarantine(group_id)
            elif state is GroupState.RETRACTED:
                self.store.retract(group_id)


def _group_from_data(group_id: str, data: Mapping[str, object]) -> ConstraintGroup:
    expected = {"ir_program", "hard", "weight", "provenance"}
    extras = sorted(set(data) - expected)
    if extras:
        raise PersistenceError(f"constraint wrapper contains unknown fields: {extras}")
    raw_program = data.get("ir_program")
    if not isinstance(raw_program, dict):
        raise PersistenceError("constraint wrapper ir_program must be an object")
    hard = data.get("hard")
    weight = data.get("weight")
    provenance = data.get("provenance")
    if not isinstance(hard, bool):
        raise PersistenceError("constraint wrapper hard must be Boolean")
    if not isinstance(weight, int) or isinstance(weight, bool):
        raise PersistenceError("constraint wrapper weight must be an integer")
    if not isinstance(provenance, list) or any(not isinstance(item, str) for item in provenance):
        raise PersistenceError("constraint wrapper provenance must be a string list")
    return ConstraintGroup(
        group_id,
        ConstraintProgram.from_data(cast("dict[str, object]", raw_program)),
        hard=hard,
        weight=weight,
        provenance=tuple(cast("list[str]", provenance)),
    )


def _secret_hex(model: ModelAssignment | None) -> str | None:
    if model is None:
        return None
    secret_values = [
        (int(name.removeprefix("secret_")), value)
        for name, value in model.values
        if name.startswith("secret_") and isinstance(value, int)
    ]
    if not secret_values:
        return None
    secret_values.sort()
    if [lane for lane, _ in secret_values] != list(range(len(secret_values))):
        return None
    return "".join(format(value, "x") for _, value in secret_values)
