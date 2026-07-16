"""Serializable hard-constraint IR with complete relation provenance."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class ApproximationKind(StrEnum):
    """How completely an observation was represented by a hard constraint."""

    EXACT = "exact"
    BOUNDED = "bounded"


@dataclass(frozen=True, order=True, slots=True)
class FiniteModelAssignment:
    """One allowed secret projection paired with a concrete fault-family member."""

    secret_values: tuple[int, ...]
    fault_variant: str

    def __post_init__(self) -> None:
        if not self.secret_values or any(value < 0 or value > 15 for value in self.secret_values):
            raise ValueError("model assignment contains an invalid secret projection")
        if self.fault_variant not in {"off", "reference", "weak", "signed"}:
            raise ValueError("model assignment contains an unknown fault variant")


@dataclass(frozen=True, slots=True)
class FiniteModelConstraint:
    """Allowed secret/fault models for one or more identity-mapped lanes."""

    constraint_version: str
    constraint_id: str
    lanes: tuple[int, ...]
    allowed_models: tuple[FiniteModelAssignment, ...]
    approximation: ApproximationKind
    relation_instance_id: str
    certificate_id: str
    decision_kind: str
    source_request_ids: tuple[str, ...]
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate a canonical finite relation instead of silently repairing it."""
        if self.constraint_version != "1.0":
            raise ValueError("unsupported constraint version")
        if not self.constraint_id:
            raise ValueError("constraint_id must not be empty")
        if not self.lanes or tuple(sorted(set(self.lanes))) != self.lanes:
            raise ValueError("lanes must be a nonempty sorted unique tuple")
        if not self.allowed_models:
            raise ValueError("allowed_models must not be empty")
        if tuple(sorted(set(self.allowed_models))) != self.allowed_models:
            raise ValueError("allowed_models must be sorted and unique")
        for model in self.allowed_models:
            if len(model.secret_values) != len(self.lanes):
                raise ValueError("assignment width does not match lanes")
        if not self.relation_instance_id or not self.certificate_id:
            raise ValueError("constraint provenance must not be empty")
        if not self.source_request_ids:
            raise ValueError("constraint must link to public source requests")

    @property
    def allowed_assignments(self) -> tuple[tuple[int, ...], ...]:
        """Return the projected secret disjunction, intentionally forgetting fault identity."""
        return tuple(sorted({model.secret_values for model in self.allowed_models}))

    def accepts(
        self,
        secret: Sequence[int] | Mapping[int, int],
        *,
        fault_variant: str,
    ) -> bool:
        """Evaluate this finite relation against a secret and shared private fault member."""
        if isinstance(secret, Mapping):
            assignment = tuple(secret[lane] for lane in self.lanes)
        else:
            assignment = tuple(secret[lane] for lane in self.lanes)
        return FiniteModelAssignment(assignment, fault_variant) in self.allowed_models

    def to_data(self) -> dict[str, object]:
        """Return stable JSON-compatible constraint data."""
        return {
            "constraint_version": self.constraint_version,
            "constraint_id": self.constraint_id,
            "kind": "finite_model_relation",
            "lanes": list(self.lanes),
            "allowed_models": [
                {
                    "secret_values": list(model.secret_values),
                    "fault_variant": model.fault_variant,
                }
                for model in self.allowed_models
            ],
            "approximation": self.approximation.value,
            "relation_instance_id": self.relation_instance_id,
            "certificate_id": self.certificate_id,
            "decision_kind": self.decision_kind,
            "source_request_ids": list(self.source_request_ids),
            "assumptions": list(self.assumptions),
        }

    def canonical_json(self) -> str:
        """Serialize deterministically for persistence, hashing, and replay."""
        return json.dumps(self.to_data(), sort_keys=True, separators=(",", ":"))


class ExtractionStatus(StrEnum):
    """Outcome of compiling a public decision into hard constraints."""

    EMITTED = "emitted"
    INCONCLUSIVE = "inconclusive"
    INVALID = "invalid"
    UNINFORMATIVE = "uninformative"
    POLICY_REJECTED = "policy_rejected"


@dataclass(frozen=True, slots=True)
class ConstraintExtraction:
    """Explicitly label whether a relation emitted hard inference state."""

    status: ExtractionStatus
    hard_constraints: tuple[FiniteModelConstraint, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.status is ExtractionStatus.EMITTED and not self.hard_constraints:
            raise ValueError("emitted extraction requires a hard constraint")
        if self.status is not ExtractionStatus.EMITTED and self.hard_constraints:
            raise ValueError("non-emitted extraction cannot carry hard constraints")
