"""Deterministic black-box tutorial recovery, uniqueness, judge, and report flow."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sphinx_interrogator.certificates import ProofMethod
from sphinx_interrogator.constraints import ExtractionStatus
from sphinx_interrogator.harness import (
    DurableExecutionHarness,
    ExecutionSpec,
    balanced_pair_schedule,
)
from sphinx_interrogator.hypothesis_persistence import CampaignHypotheses
from sphinx_interrogator.model import ExecutionResult
from sphinx_interrogator.persistence import (
    CampaignManifest,
    CampaignRepository,
    CampaignResultStatus,
    normalize_campaign_result_status,
)
from sphinx_interrogator.protocol import submit_judge as submit_judge_request
from sphinx_interrogator.relations import AnchorSwitchTemplate, RelationInstance
from sphinx_interrogator.solver import SolverStatus, UniquenessResult


@dataclass(frozen=True, slots=True)
class TutorialRecoveryResult:
    """Public recovery outcome and durable artifact location."""

    status: str
    run_directory: Path
    report: Mapping[str, object]


def recover_tutorial(
    *,
    public_challenge: Path,
    vm_socket: Path,
    judge_socket: Path | None,
    run_directory: Path,
    campaign_seed: int,
    submit_judge: bool = True,
) -> TutorialRecoveryResult:
    """Recover a tutorial challenge through public relation observations only."""
    wall_started = time.time()
    perf_started = time.perf_counter()
    if campaign_seed < 0:
        raise ValueError("campaign seed must be nonnegative")
    if submit_judge and judge_socket is None:
        raise ValueError("judge socket is required when judge submission is enabled")
    public = _load_object(public_challenge / "challenge.json", "public challenge")
    profile_path = public_challenge / "profile.toml"
    profile_digest = _sha256_file(profile_path)
    challenge_id = _string(public, "challenge_id")
    budgets = _mapping(public, "budgets")
    manifest = CampaignManifest(
        campaign_id=f"tutorial-{challenge_id}-{campaign_seed}",
        challenge_id=challenge_id,
        challenge_commitment=_string(public, "commitment"),
        profile_name="tutorial",
        semantic_version="0.1.0",
        public_profile_sha256=profile_digest,
        seed=campaign_seed,
        minimum_certificate_strength=ProofMethod.EXHAUSTIVE_ENUMERATION.value,
        logical_query_budget=_integer(budgets, "logical_queries"),
        physical_execution_budget=_integer(budgets, "physical_executions"),
        hard_reset_budget=_integer(budgets, "hard_resets"),
    )
    existing_report = _existing_accepted_report(run_directory, manifest)
    if existing_report is not None:
        return TutorialRecoveryResult("unique_exact", run_directory, existing_report)

    repository = CampaignRepository.create(run_directory, manifest)
    hypotheses = CampaignHypotheses(repository)
    harness, client = DurableExecutionHarness.connect_unix(
        repository,
        socket_path=vm_socket,
        timeout_seconds=5.0,
    )
    final_results: tuple[ExecutionResult, ExecutionResult] | None = None
    try:
        hello = client.hello()
        if (
            hello.profile_name != "tutorial"
            or hello.semantic_version != manifest.semantic_version
            or hello.bucket_width != 1
            or not hello.hard_reset_available
        ):
            raise ValueError("target does not satisfy the exact tutorial recovery contract")
        relation_index = 0
        for lane in range(hello.lanes):
            for epoch in (0, 1):
                for bank_a, bank_b in ((0, 1), (2, 3)):
                    relation = AnchorSwitchTemplate().instantiate(
                        instance_id=(
                            f"tutorial-{relation_index:02d}-l{lane}-e{epoch}-a{bank_a}-b{bank_b}"
                        ),
                        lane=lane,
                        token=0,
                        epoch=epoch,
                        bank_a=bank_a,
                        bank_b=bank_b,
                        pad=(lane ^ epoch) & 3,
                    )
                    final_results = _execute_relation(
                        repository,
                        hypotheses,
                        harness,
                        relation,
                        relation_index=relation_index,
                        campaign_seed=campaign_seed,
                        secret_cells=hello.lanes,
                    )
                    relation_index += 1
    finally:
        client.close()

    solve = hypotheses.solve()
    uniqueness = hypotheses.check_uniqueness(hello.lanes)
    guessed_secret = _secret_from_uniqueness(uniqueness, hello.lanes)
    snapshot = hypotheses.store.snapshot(limit=64)
    snapshot_data = snapshot.to_data()
    snapshot_data["secret_projection_uniqueness"] = {
        "solver_status": uniqueness.status.value,
        "unique": uniqueness.unique,
        "alternative_model_unsat": uniqueness.status is SolverStatus.UNSAT,
        "candidate_secret_hex": guessed_secret,
        "reason": uniqueness.reason,
    }
    repository.append_event(
        event_id="snapshot:tutorial-final",
        kind="candidate_snapshot",
        logical_time=17,
        payload={
            "snapshot_id": "tutorial-final",
            "solver_status": snapshot.solver_status.value,
            "exact_count": snapshot.exact_count,
            "unique_secret_hex": guessed_secret,
            "snapshot": snapshot_data,
        },
    )

    judge_response: Mapping[str, object] | None = None
    if guessed_secret is not None and submit_judge:
        if judge_socket is None:
            raise RuntimeError("judge socket disappeared after recovery validation")
        judge_response = submit_judge_request(
            judge_socket,
            campaign_token=_string(public, "campaign_token"),
            guess=guessed_secret,
        )
        repository.append_event(
            event_id="judge:tutorial-final",
            kind="judge_recorded",
            logical_time=18,
            payload={
                "submission_id": "tutorial-final",
                "challenge_id": challenge_id,
                "submission_recorded": _boolean(judge_response, "submission_recorded"),
                "accepted": _boolean(judge_response, "accepted"),
                "response": dict(judge_response),
            },
        )

    if solve.status is SolverStatus.UNSAT:
        status = CampaignResultStatus.MODEL_INCONSISTENT.value
    elif guessed_secret is None:
        status = CampaignResultStatus.CANDIDATE_SET.value
    elif judge_response is None or _boolean(judge_response, "accepted"):
        status = CampaignResultStatus.UNIQUE_EXACT.value
    else:
        status = CampaignResultStatus.TARGET_ERROR.value
    basic = repository.report()
    report: dict[str, object] = {
        "report_version": "1.0",
        "campaign_id": manifest.campaign_id,
        "challenge_id": challenge_id,
        "profile_name": hello.profile_name,
        "semantic_version": hello.semantic_version,
        "campaign_seed": campaign_seed,
        "status": status,
        "unique_secret_hex": guessed_secret,
        "uniqueness": snapshot_data["secret_projection_uniqueness"],
        "solver": {
            "status": solve.status.value,
            "candidate_approximation": snapshot.approximation,
            "exact_full_model_count": snapshot.exact_count,
            "sampled_model_count": snapshot.sampled_count,
        },
        "cost": {
            "logical_relation_families": repository.database.table_count("batches"),
            "physical_executions": repository.database.table_count("executions"),
            "hard_resets": repository.database.table_count("executions"),
            "last_public_physical_remaining": (
                None
                if final_results is None
                else min(result.physical_executions_remaining for result in final_results)
            ),
        },
        "judge": None if judge_response is None else dict(judge_response),
        "artifacts": {
            "manifest": "manifest.json",
            "events": "events.jsonl",
            "database": "campaign.sqlite3",
            "raw_directory": "raw",
            "materialized_digest": basic["materialized_digest"],
        },
    }
    report_path = run_directory / "report.json"
    _write_json(report_path, report)
    repository.finalize_manifest(
        status=_manifest_status(status),
        artifact_paths={
            "report.json": report_path,
            "events.jsonl": run_directory / "events.jsonl",
            "campaign.sqlite3": run_directory / "campaign.sqlite3",
        },
        started_at=_iso_time(wall_started),
        ended_at=_iso_time(time.time()),
        duration_ms=int((time.perf_counter() - perf_started) * 1000),
    )
    repository.close()
    return TutorialRecoveryResult(status, run_directory, report)


def _execute_relation(
    repository: CampaignRepository,
    hypotheses: CampaignHypotheses,
    harness: DurableExecutionHarness,
    relation: RelationInstance,
    *,
    relation_index: int,
    campaign_seed: int,
    secret_cells: int,
) -> tuple[ExecutionResult, ExecutionResult]:
    logical_time = relation_index + 1
    for query_id, program in zip(
        (relation.source_query_id, *relation.follow_up_query_ids),
        relation.programs,
        strict=True,
    ):
        repository.append_event(
            event_id=f"query:{query_id}",
            kind="query_created",
            logical_time=logical_time,
            payload={
                "query_id": query_id,
                "program_sha256": program.canonical_sha256(),
                "program_text": program.render(),
                "expires_after": None,
            },
        )
    repository.append_event(
        event_id=f"certificate:{relation.certificate.certificate_id}",
        kind="certificate_registered",
        logical_time=logical_time,
        payload={
            "certificate_id": relation.certificate.certificate_id,
            "certificate": relation.certificate.to_data(),
        },
    )
    repository.append_event(
        event_id=f"relation:{relation.instance_id}",
        kind="relation_recorded",
        logical_time=logical_time,
        payload={
            "relation_instance_id": relation.instance_id,
            "relation_id": relation.relation_id,
            "certificate_id": relation.certificate.certificate_id,
            "relation": relation.to_data(),
        },
    )
    batch_id = f"batch-{relation_index:02d}"
    schedule = balanced_pair_schedule(
        (relation.instance_id,), repetitions=1, seed=campaign_seed + relation_index
    )
    repository.append_event(
        event_id=f"batch:{batch_id}",
        kind="batch_scheduled",
        logical_time=logical_time,
        payload={
            "batch_id": batch_id,
            "seed": campaign_seed + relation_index,
            "schedule": [item.to_data() for item in schedule],
            "status": "scheduled",
        },
    )
    by_arm: dict[str, ExecutionResult] = {}
    for item in schedule:
        query_id = (
            relation.source_query_id if item.arm == "source" else relation.follow_up_query_ids[0]
        )
        program = (
            relation.source_program if item.arm == "source" else relation.follow_up_programs[0]
        )
        execution_id = f"exec-{relation_index:02d}-{item.arm.replace('_', '-')}"
        by_arm[item.arm] = harness.execute(
            ExecutionSpec(
                execution_id=execution_id,
                query_id=query_id,
                batch_id=batch_id,
                position=item.position,
                program=program.render(),
                session_id=f"session-{relation_index:02d}-{item.arm}",
                reset="hard",
                logical_time=logical_time,
                execution_seed_id=item.correlation_group,
            )
        )
    source = by_arm["source"]
    follow_up = by_arm["follow_up"]
    template = AnchorSwitchTemplate()
    decision = template.decide(relation, source, follow_up, noise_bound=0)
    repository.append_event(
        event_id=f"decision:{relation.instance_id}",
        kind="decision_recorded",
        logical_time=logical_time,
        payload={
            "decision_id": relation.instance_id,
            "relation_instance_id": relation.instance_id,
            "kind": decision.kind.value,
            "decision": decision.to_data(),
        },
    )
    extraction = template.extract(
        relation,
        source,
        follow_up,
        decision,
        noise_bound=0,
        minimum_certificate=ProofMethod.EXHAUSTIVE_ENUMERATION,
    )
    if extraction.status is not ExtractionStatus.EMITTED:
        raise RuntimeError(
            f"exact tutorial relation {relation.instance_id} did not emit: "
            f"{extraction.status.value}: {extraction.reason}"
        )
    for constraint in extraction.hard_constraints:
        hypotheses.add_finite_constraint(
            constraint,
            secret_cells=secret_cells,
            logical_time=logical_time,
        )
    return source, follow_up


def _secret_from_uniqueness(uniqueness: UniquenessResult, secret_cells: int) -> str | None:
    if uniqueness.unique is not True or uniqueness.candidate is None:
        return None
    values = []
    for lane in range(secret_cells):
        value = uniqueness.candidate.get(f"secret_{lane}")
        if not isinstance(value, int) or isinstance(value, bool):
            raise RuntimeError("secret model does not contain integer nibbles")
        values.append(value)
    return "".join(format(value, "x") for value in values)


def _existing_accepted_report(
    run_directory: Path,
    manifest: CampaignManifest,
) -> Mapping[str, object] | None:
    path = run_directory / "report.json"
    if not path.exists():
        return None
    report = _load_object(path, "tutorial report")
    if report.get("campaign_id") == manifest.campaign_id and report.get("status") == "unique_exact":
        judge = report.get("judge")
        if isinstance(judge, dict) and judge.get("accepted") is True:
            repository = CampaignRepository.open(run_directory)
            try:
                if not repository.manifest.same_public_inputs(manifest):
                    raise ValueError("accepted report manifest does not match this challenge")
                artifacts = report.get("artifacts")
                if not isinstance(artifacts, dict):
                    raise ValueError("accepted report lacks artifact metadata")
                if artifacts.get("materialized_digest") != repository.database.digest():
                    raise ValueError("accepted report materialized digest does not replay")
                if repository.database.table_count("judge_submissions") != 1:
                    raise ValueError("accepted report lacks its one judge event")
                if repository.manifest.to_data()["manifest_version"] != "1.2":
                    repository.finalize_manifest(
                        status=CampaignResultStatus.UNIQUE_EXACT,
                        artifact_paths={
                            "report.json": run_directory / "report.json",
                            "events.jsonl": run_directory / "events.jsonl",
                            "campaign.sqlite3": run_directory / "campaign.sqlite3",
                        },
                    )
            finally:
                repository.close()
            return report
    return None


def _load_object(path: Path, context: str) -> dict[str, object]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {context}") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{context} must be a JSON object")
    return cast("dict[str, object]", decoded)


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    encoded = json.dumps(data, indent=2, sort_keys=True).encode() + b"\n"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        if os.write(descriptor, encoded) != len(encoded):
            raise RuntimeError("short write while persisting tutorial report")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_status(status: str) -> CampaignResultStatus:
    return normalize_campaign_result_status(status)


def _iso_time(timestamp: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return cast("dict[str, object]", value)


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _boolean(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be Boolean")
    return value
