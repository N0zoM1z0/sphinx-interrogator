"""Sound finite-domain extractors for exact and bounded identity profiles."""

from __future__ import annotations

import hashlib
import itertools
import json

from sphinx_interrogator.certificates import ProofMethod
from sphinx_interrogator.constraints import (
    ApproximationKind,
    ConstraintExtraction,
    ExtractionStatus,
    FiniteModelAssignment,
    FiniteModelConstraint,
)
from sphinx_interrogator.model import ExecutionResult
from sphinx_interrogator.normalization import DecisionKind, PairDecision
from sphinx_interrogator.relations import RelationInstance
from sphinx_interrogator.target_model import (
    FaultVariant,
    MicroState,
    execute_experiment_program,
)

_ALL_VARIANTS = tuple(FaultVariant)


def extract_finite_models(
    relation: RelationInstance,
    source: ExecutionResult,
    follow_up: ExecutionResult,
    decision: PairDecision,
    *,
    noise_bound: int,
    fault_variants: tuple[FaultVariant, ...] = _ALL_VARIANTS,
    minimum_certificate: ProofMethod = ProofMethod.EXHAUSTIVE_ENUMERATION,
    initial_state: MicroState | None = None,
) -> ConstraintExtraction:
    """Enumerate every secret/fault model consistent with both public buckets."""
    if noise_bound < 0:
        raise ValueError("noise_bound must be nonnegative")
    if not fault_variants or len(set(fault_variants)) != len(fault_variants):
        raise ValueError("fault_variants must be a nonempty unique tuple")
    if len(relation.follow_up_programs) != 1:
        return ConstraintExtraction(
            ExtractionStatus.INVALID,
            (),
            "finite extractor currently accepts exactly one follow-up",
        )
    resolved_initial = MicroState() if initial_state is None else initial_state
    if relation.reset_policy != "hard" or resolved_initial != MicroState():
        return ConstraintExtraction(
            ExtractionStatus.INVALID,
            (),
            "finite M3 extractor requires the unique hard-reset state",
        )
    if not relation.emits_secret_constraints or not relation.involved_lanes:
        return ConstraintExtraction(
            ExtractionStatus.UNINFORMATIVE,
            (),
            "relation is an apparatus/control check and emits no secret constraints",
        )
    if not relation.instance_binding_valid():
        return ConstraintExtraction(
            ExtractionStatus.INVALID,
            (),
            "relation programs/holes do not match the certified instance hash",
        )
    if not relation.architectural_precheck():
        return ConstraintExtraction(
            ExtractionStatus.INVALID,
            (),
            "relation architectural precheck failed",
        )
    if not relation.fault_free_precheck():
        return ConstraintExtraction(
            ExtractionStatus.INVALID,
            (),
            "relation fault-free observation precheck failed",
        )
    if not relation.certificate.meets(minimum_certificate):
        return ConstraintExtraction(
            ExtractionStatus.POLICY_REJECTED,
            (),
            "certificate strength is below campaign policy",
        )
    if decision.kind is DecisionKind.INVALID:
        return ConstraintExtraction(ExtractionStatus.INVALID, (), decision.reason or "invalid pair")
    if decision.kind is DecisionKind.INCONCLUSIVE:
        return ConstraintExtraction(
            ExtractionStatus.INCONCLUSIVE,
            (),
            "quantization/noise interval crosses more than one order outcome",
        )
    expected_request_ids = (source.request_id, follow_up.request_id)
    if decision.source_request_ids != expected_request_ids:
        return ConstraintExtraction(
            ExtractionStatus.INVALID,
            (),
            "decision provenance does not match the supplied public executions",
        )

    allowed: list[FiniteModelAssignment] = []
    lanes = relation.involved_lanes
    for secret_values in itertools.product(range(16), repeat=len(lanes)):
        secret_by_lane = dict(zip(lanes, secret_values, strict=True))
        for variant in fault_variants:
            source_model = execute_experiment_program(
                relation.source_program,
                secret_by_lane,
                initial_state=resolved_initial,
                variant=variant,
            )
            follow_model = execute_experiment_program(
                relation.follow_up_programs[0],
                secret_by_lane,
                initial_state=resolved_initial,
                variant=variant,
            )
            if _observation_feasible(
                source,
                static_cycles=source_model.static_cycles,
                fault_cycles=source_model.fault_cycles,
                noise_bound=noise_bound,
            ) and _observation_feasible(
                follow_up,
                static_cycles=follow_model.static_cycles,
                fault_cycles=follow_model.fault_cycles,
                noise_bound=noise_bound,
            ):
                allowed.append(FiniteModelAssignment(secret_values, variant.value))

    allowed_models = tuple(sorted(allowed))
    complete_model_count = (16 ** len(lanes)) * len(fault_variants)
    if not allowed_models:
        return ConstraintExtraction(
            ExtractionStatus.INVALID,
            (),
            "no declared secret/fault/noise model can reproduce the public buckets",
        )
    if len(allowed_models) == complete_model_count:
        return ConstraintExtraction(
            ExtractionStatus.UNINFORMATIVE,
            (),
            "public buckets retain the complete finite model domain",
        )
    approximation = (
        ApproximationKind.EXACT
        if source.observation.bucket_width == 1
        and follow_up.observation.bucket_width == 1
        and noise_bound == 0
        and decision.kind
        in {
            DecisionKind.EXACT_LESS,
            DecisionKind.EXACT_EQUAL,
            DecisionKind.EXACT_GREATER,
        }
        else ApproximationKind.BOUNDED
    )
    constraint_id = _constraint_id(relation, source, follow_up, allowed_models)
    constraint = FiniteModelConstraint(
        constraint_version="1.0",
        constraint_id=constraint_id,
        lanes=lanes,
        allowed_models=allowed_models,
        approximation=approximation,
        relation_instance_id=relation.instance_id,
        certificate_id=relation.certificate.certificate_id,
        decision_kind=decision.kind.value,
        source_request_ids=expected_request_ids,
        assumptions=(
            *decision.assumptions,
            "identity_lane_mapping",
            "unique_hard_reset_state",
            "fault_variant_is_shared_campaign_state",
            f"independent_noise_in_[{-noise_bound},{noise_bound}]",
        ),
    )
    return ConstraintExtraction(
        ExtractionStatus.EMITTED,
        (constraint,),
        f"retained {len(allowed_models)} of {complete_model_count} finite models",
    )


def _observation_feasible(
    result: ExecutionResult,
    *,
    static_cycles: int,
    fault_cycles: int,
    noise_bound: int,
) -> bool:
    width = result.observation.bucket_width
    bucket = result.observation.cycle_bucket
    return any(
        max(0, static_cycles + fault_cycles + noise) // width == bucket
        for noise in range(-noise_bound, noise_bound + 1)
    )


def _constraint_id(
    relation: RelationInstance,
    source: ExecutionResult,
    follow_up: ExecutionResult,
    allowed_models: tuple[FiniteModelAssignment, ...],
) -> str:
    data = {
        "relation_instance_hash": relation.instance_hash,
        "source_request_id": source.request_id,
        "follow_up_request_id": follow_up.request_id,
        "source_bucket": source.observation.cycle_bucket,
        "follow_up_bucket": follow_up.observation.cycle_bucket,
        "allowed_models": [[*model.secret_values, model.fault_variant] for model in allowed_models],
    }
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"constraint:{hashlib.sha256(encoded).hexdigest()[:24]}"
