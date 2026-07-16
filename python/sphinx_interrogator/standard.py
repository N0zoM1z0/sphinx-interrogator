"""Bounded-noise standard-profile recovery through certified public relations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from sphinx_interrogator.certificates import ProofMethod
from sphinx_interrogator.constraints import ConstraintExtraction, ExtractionStatus
from sphinx_interrogator.frontier import ActiveFrontier, NoveltyStatus
from sphinx_interrogator.harness import (
    DurableExecutionHarness,
    ExecutionSpec,
    balanced_pair_schedule,
)
from sphinx_interrogator.hypothesis_persistence import CampaignHypotheses
from sphinx_interrogator.model import ExecutionResult
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository
from sphinx_interrogator.relations import RelationInstance, RepeatAmplifyTemplate
from sphinx_interrogator.solver import SolverStatus
from sphinx_interrogator.synthesis import (
    BoundedRelationGrammar,
    CegisSynthesizer,
    DiverseCommittee,
    RepeatAmplifyCandidate,
    SynthesisContext,
    SynthesisModel,
    SynthesisResult,
    SynthesisStatus,
)

_FAULT_VARIANTS = ("off", "reference", "weak", "signed")


class StandardSelectorMode(StrEnum):
    """Predeclared full-system and fair selector baseline modes."""

    FULL = "full"
    RANDOM = "random"
    STATELESS = "stateless"
    KB_NO_SYNTHESIS = "kb_no_synthesis"
    SYNTHESIS_NO_KB = "synthesis_no_kb"


@dataclass(frozen=True, slots=True)
class StandardRecoveryResult:
    """One exact/inconclusive standard campaign and its durable public report."""

    status: str
    run_directory: Path
    report: Mapping[str, object]


@dataclass(slots=True)
class _Timing:
    synthesis_seconds: float = 0.0
    vm_and_wire_persistence_seconds: float = 0.0
    solver_seconds: float = 0.0
    statistics_seconds: float = 0.0
    learning_seconds: float = 0.0
    report_persistence_seconds: float = 0.0

    def to_data(self, total_seconds: float) -> dict[str, object]:
        return {
            "measurement_method": "wall-clock-segments/v1",
            "total": total_seconds,
            "synthesis": self.synthesis_seconds,
            "vm_and_wire_persistence": self.vm_and_wire_persistence_seconds,
            "solver": self.solver_seconds,
            "statistics": self.statistics_seconds,
            "learning": self.learning_seconds,
            "report_persistence": self.report_persistence_seconds,
        }


def recover_standard(
    *,
    vm_binary: Path,
    challenge: Path,
    run_directory: Path,
    campaign_seed: int,
    selector_mode: StandardSelectorMode = StandardSelectorMode.FULL,
    submit_judge: bool = True,
) -> StandardRecoveryResult:
    """Recover one 32-bit identity-profile secret using bounded hard evidence only."""
    started = time.perf_counter()
    timing = _Timing()
    if campaign_seed < 0:
        raise ValueError("campaign seed must be nonnegative")
    if not vm_binary.is_file():
        raise ValueError("SphinxVM binary does not exist")
    public = _load_object(challenge / "public/challenge.json", "public challenge")
    profile_path = challenge / "public/profile.toml"
    profile = _load_profile(profile_path)
    _require_standard_profile(profile)
    challenge_id = _string(public, "challenge_id")
    budgets = _mapping(public, "budgets")
    manifest = CampaignManifest(
        campaign_id=f"standard-{selector_mode.value}-{challenge_id}-{campaign_seed}",
        challenge_id=challenge_id,
        challenge_commitment=_string(public, "commitment"),
        profile_name="standard",
        semantic_version="0.1.0",
        public_profile_sha256=_sha256_file(profile_path),
        seed=campaign_seed,
        minimum_certificate_strength=ProofMethod.EXHAUSTIVE_ENUMERATION.value,
        logical_query_budget=_integer(budgets, "logical_queries"),
        physical_execution_budget=_integer(budgets, "physical_executions"),
        hard_reset_budget=_integer(budgets, "hard_resets"),
    )
    existing = _existing_report(run_directory, manifest)
    if existing is not None:
        return StandardRecoveryResult(_string(existing, "status"), run_directory, existing)

    repository = CampaignRepository.create(run_directory, manifest)
    try:
        hypotheses = CampaignHypotheses(repository)
        harness, client = DurableExecutionHarness.start_process(
            repository,
            vm_binary,
            challenge=challenge,
            timeout_seconds=5.0,
        )
        lane_domains = [set(range(16)) for _ in range(_integer(profile, "secret_cells"))]
        fault_domain = set(_FAULT_VARIANTS)
        relation_index = 0
        cegis_refinements = 0
        synthesizer = CegisSynthesizer()
        last_results: tuple[ExecutionResult, ExecutionResult] | None = None
        try:
            hello = client.hello()
            if (
                hello.profile_name != "standard"
                or hello.semantic_version != "0.1.0"
                or hello.bucket_width != 4
                or not hello.hard_reset_available
                or hello.lanes != len(lane_domains)
            ):
                raise ValueError("target does not satisfy the bounded standard contract")
            for lane in range(hello.lanes):
                for epoch in (0, 1):
                    before = len(lane_domains[lane])
                    used: set[str] = set()
                    while len(lane_domains[lane]) == before:
                        selection_started = time.perf_counter()
                        selected, synthesis_result = _select_candidate(
                            selector_mode,
                            lane=lane,
                            epoch=epoch,
                            lane_domain=frozenset(lane_domains[lane]),
                            secret_cells=hello.lanes,
                            used=used,
                            campaign_seed=campaign_seed,
                            synthesizer=synthesizer,
                        )
                        timing.synthesis_seconds += time.perf_counter() - selection_started
                        if selected is None:
                            break
                        used.add(selected.canonical_key())
                        if synthesis_result is not None:
                            cegis_refinements += len(synthesis_result.counterexamples)
                            if (
                                selector_mode is StandardSelectorMode.FULL
                                and synthesis_result.status is SynthesisStatus.SAT
                            ):
                                frontier = ActiveFrontier(repository)
                                frontier_candidate = synthesis_result.frontier_candidate(
                                    candidate_id=f"standard-select-{relation_index:03d}",
                                    expires_after=relation_index,
                                )
                                novelty = frontier.consider(
                                    frontier_candidate,
                                    logical_time=relation_index,
                                )
                                if novelty.status is not NoveltyStatus.NOVEL:
                                    raise RuntimeError(
                                        f"synthesized candidate was not novel: {novelty.reason}"
                                    )
                                chosen = frontier.select(logical_time=relation_index)
                                if chosen is None or chosen.candidate_id != (
                                    f"standard-select-{relation_index:03d}"
                                ):
                                    raise RuntimeError(
                                        "frontier did not select the synthesized query"
                                    )
                        relation = selected.lower(f"standard-{relation_index:03d}-l{lane}-e{epoch}")
                        execution_started = time.perf_counter()
                        last_results, extraction = _execute_relation(
                            repository,
                            hypotheses,
                            harness,
                            relation,
                            relation_index=relation_index,
                            campaign_seed=campaign_seed,
                            secret_cells=hello.lanes,
                            noise_bound=1,
                        )
                        timing.vm_and_wire_persistence_seconds += (
                            time.perf_counter() - execution_started
                        )
                        relation_index += 1
                        if extraction.status is ExtractionStatus.EMITTED:
                            for constraint in extraction.hard_constraints:
                                allowed = {
                                    model.secret_values[0] for model in constraint.allowed_models
                                }
                                lane_domains[lane].intersection_update(allowed)
                                fault_domain.intersection_update(
                                    model.fault_variant for model in constraint.allowed_models
                                )
                            if not lane_domains[lane] or not fault_domain:
                                raise RuntimeError(
                                    "bounded extraction emptied the finite hypothesis"
                                )
                        elif extraction.status not in {
                            ExtractionStatus.INCONCLUSIVE,
                            ExtractionStatus.UNINFORMATIVE,
                        }:
                            raise RuntimeError(
                                f"standard extraction failed: {extraction.status.value}: "
                                f"{extraction.reason}"
                            )
        finally:
            client.close()

        secret_candidate_count = math.prod(len(domain) for domain in lane_domains)
        solve_started = time.perf_counter()
        solve = hypotheses.solve()
        guessed_secret: str | None = None
        uniqueness_data: dict[str, object]
        if secret_candidate_count == 1:
            uniqueness = hypotheses.check_uniqueness(len(lane_domains))
            guessed_secret = _secret_from_domains(lane_domains)
            uniqueness_data = {
                "solver_status": uniqueness.status.value,
                "unique": uniqueness.unique,
                "alternative_model_unsat": uniqueness.status is SolverStatus.UNSAT,
                "candidate_secret_hex": guessed_secret,
                "reason": uniqueness.reason,
            }
            if uniqueness.unique is not True or uniqueness.status is not SolverStatus.UNSAT:
                guessed_secret = None
        else:
            uniqueness_data = {
                "solver_status": solve.status.value,
                "unique": False,
                "alternative_model_unsat": False,
                "candidate_secret_hex": None,
                "reason": f"factorized domain retains {secret_candidate_count} secrets",
            }
        timing.solver_seconds += time.perf_counter() - solve_started
        full_model_count = secret_candidate_count * len(fault_domain)
        repository.append_event(
            event_id="snapshot:standard-final",
            kind="candidate_snapshot",
            logical_time=relation_index + 1,
            payload={
                "snapshot_id": "standard-final",
                "solver_status": solve.status.value,
                "exact_count": full_model_count,
                "unique_secret_hex": guessed_secret,
                "snapshot": {
                    "approximation": "factorized-exact-bounded",
                    "secret_candidate_count": secret_candidate_count,
                    "full_model_count": full_model_count,
                    "lane_domains": [sorted(domain) for domain in lane_domains],
                    "fault_domain": sorted(fault_domain),
                    "secret_projection_uniqueness": uniqueness_data,
                },
            },
        )

        judge_response: Mapping[str, object] | None = None
        if guessed_secret is not None and submit_judge:
            judge_response = _submit_judge(
                vm_binary,
                challenge,
                campaign_token=_string(public, "campaign_token"),
                guess=guessed_secret,
            )
            repository.append_event(
                event_id="judge:standard-final",
                kind="judge_recorded",
                logical_time=relation_index + 2,
                payload={
                    "submission_id": "standard-final",
                    "challenge_id": challenge_id,
                    "submission_recorded": _boolean(judge_response, "submission_recorded"),
                    "accepted": _boolean(judge_response, "accepted"),
                    "response": dict(judge_response),
                },
            )

        if solve.status is SolverStatus.UNSAT:
            status = "inconsistent"
        elif guessed_secret is None:
            status = "inconclusive"
        elif judge_response is None:
            status = "unique_exact_unjudged"
        elif _boolean(judge_response, "accepted"):
            status = "unique_exact"
        else:
            status = "judge_rejected"
        basic = repository.report()
        total_before_report = time.perf_counter() - started
        report: dict[str, object] = {
            "report_version": "1.0",
            "campaign_id": manifest.campaign_id,
            "challenge_id": challenge_id,
            "profile_name": "standard",
            "semantic_version": "0.1.0",
            "campaign_seed": campaign_seed,
            "selector_mode": selector_mode.value,
            "status": status,
            "unique_secret_hex": guessed_secret,
            "remaining_secret_candidates": secret_candidate_count,
            "uniqueness": uniqueness_data,
            "solver": {
                "status": solve.status.value,
                "candidate_approximation": "factorized-exact-bounded",
                "exact_full_model_count": full_model_count,
                "active_fault_variants": sorted(fault_domain),
            },
            "cost": {
                "logical_relation_families": repository.database.table_count("batches"),
                "physical_executions": repository.database.table_count("executions"),
                "hard_resets": repository.database.table_count("executions"),
                "last_public_physical_remaining": (
                    None
                    if last_results is None
                    else min(result.physical_executions_remaining for result in last_results)
                ),
            },
            "evidence": {
                "hard_bounded_constraints": repository.database.table_count("constraints"),
                "stochastic_soft_groups": 0,
                "cegis_refinements": cegis_refinements,
                "result_class": "bounded-hard-exact",
            },
            "judge": None if judge_response is None else dict(judge_response),
            "timing_seconds": timing.to_data(total_before_report),
            "artifacts": {
                "manifest": "manifest.json",
                "events": "events.jsonl",
                "database": "campaign.sqlite3",
                "raw_directory": "raw",
                "materialized_digest": basic["materialized_digest"],
            },
        }
        report_started = time.perf_counter()
        _write_json(run_directory / "report.json", report)
        timing.report_persistence_seconds += time.perf_counter() - report_started
        report["timing_seconds"] = timing.to_data(time.perf_counter() - started)
        _write_json(run_directory / "report.json", report)
        return StandardRecoveryResult(status, run_directory, report)
    finally:
        repository.close()


def _select_candidate(
    mode: StandardSelectorMode,
    *,
    lane: int,
    epoch: int,
    lane_domain: frozenset[int],
    secret_cells: int,
    used: set[str],
    campaign_seed: int,
    synthesizer: CegisSynthesizer,
) -> tuple[RepeatAmplifyCandidate | None, SynthesisResult | None]:
    active_pad = (lane ^ epoch) & 3
    candidates = tuple(
        RepeatAmplifyCandidate(lane, 0, epoch, anchor, active_pad, 16)
        for anchor in range(4)
        if RepeatAmplifyCandidate(lane, 0, epoch, anchor, active_pad, 16).canonical_key()
        not in used
    )
    if not candidates:
        return None, None
    if mode in {StandardSelectorMode.FULL, StandardSelectorMode.SYNTHESIS_NO_KB}:
        models = []
        for value in sorted(lane_domain):
            secret = [0] * secret_cells
            secret[lane] = value
            models.append(SynthesisModel(f"lane-{lane}-value-{value:02d}", tuple(secret)))
        committee = DiverseCommittee.select(
            tuple(models),
            limit=len(models),
            complete=True,
            source="standard-factorized-lane-domain",
        )
        grammar = BoundedRelationGrammar(
            lanes=(lane,),
            tokens=(0,),
            epochs=(epoch,),
            pads=(active_pad,),
            repeat_counts=(16,),
            include_anchor_switch=False,
        )
        local = CegisSynthesizer(grammar, hole_filler=synthesizer.hole_filler)
        result = local.synthesize(
            committee,
            SynthesisContext(
                hypothesis_fingerprint=_domain_fingerprint(lane, epoch, lane_domain),
                profile_name="standard",
                bucket_width=4,
                noise_bound=1,
                maximum_bucket_size=max(1, len(lane_domain) - len(lane_domain) // 4),
                excluded_candidate_keys=tuple(sorted(used)),
            ),
        )
        if result.status is not SynthesisStatus.SAT or result.score is None:
            # An inconclusive physical observation has not eliminated the
            # candidates in the current outcome bucket.  CEGIS can therefore
            # exhaust the assignments that separate its first model pair
            # before the bounded four-anchor experiment is complete.  Keep
            # the failed synthesis result for audit metadata and fall back to
            # the cheapest unexplored certified assignment.
            return min(candidates, key=lambda candidate: candidate.canonical_key()), result
        if not isinstance(result.score.candidate, RepeatAmplifyCandidate):
            raise RuntimeError("standard grammar returned the wrong relation skeleton")
        return result.score.candidate, result
    if mode is StandardSelectorMode.RANDOM:
        selected = min(
            candidates,
            key=lambda candidate: hashlib.sha256(
                f"{campaign_seed}:{candidate.canonical_key()}".encode()
            ).hexdigest(),
        )
    elif mode is StandardSelectorMode.STATELESS:
        selected = max(candidates, key=lambda candidate: candidate.canonical_key())
    else:
        selected = min(candidates, key=lambda candidate: candidate.canonical_key())
    return selected, None


def _execute_relation(
    repository: CampaignRepository,
    hypotheses: CampaignHypotheses,
    harness: DurableExecutionHarness,
    relation: RelationInstance,
    *,
    relation_index: int,
    campaign_seed: int,
    secret_cells: int,
    noise_bound: int,
) -> tuple[tuple[ExecutionResult, ExecutionResult], ConstraintExtraction]:
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
    batch_id = f"standard-batch-{relation_index:03d}"
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
        source_arm = item.arm == "source"
        query_id = relation.source_query_id if source_arm else relation.follow_up_query_ids[0]
        program = relation.source_program if source_arm else relation.follow_up_programs[0]
        execution_id = f"standard-exec-{relation_index:03d}-{item.arm.replace('_', '-')}"
        by_arm[item.arm] = harness.execute(
            ExecutionSpec(
                execution_id=execution_id,
                query_id=query_id,
                batch_id=batch_id,
                position=item.position,
                program=program.render(),
                session_id=f"standard-{item.arm}",
                reset="hard",
                logical_time=logical_time,
                execution_seed_id=item.correlation_group,
            )
        )
    source = by_arm["source"]
    follow_up = by_arm["follow_up"]
    template = RepeatAmplifyTemplate()
    decision = template.decide(relation, source, follow_up, noise_bound=noise_bound)
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
        noise_bound=noise_bound,
        minimum_certificate=ProofMethod.EXHAUSTIVE_ENUMERATION,
    )
    for constraint in extraction.hard_constraints:
        hypotheses.add_finite_constraint(
            constraint,
            secret_cells=secret_cells,
            logical_time=logical_time,
        )
    return (source, follow_up), extraction


def _existing_report(
    run_directory: Path,
    manifest: CampaignManifest,
) -> Mapping[str, object] | None:
    path = run_directory / "report.json"
    if not path.exists():
        return None
    report = _load_object(path, "standard report")
    status = report.get("status")
    if report.get("campaign_id") != manifest.campaign_id or status not in {
        "unique_exact",
        "unique_exact_unjudged",
        "inconclusive",
    }:
        return None
    repository = CampaignRepository.open(run_directory)
    try:
        if repository.manifest != manifest:
            raise ValueError("standard report manifest does not match this challenge")
        artifacts = report.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError("standard report lacks artifact metadata")
        if artifacts.get("materialized_digest") != repository.database.digest():
            raise ValueError("standard report materialized digest does not replay")
        expected_judges = int(status == "unique_exact")
        if repository.database.table_count("judge_submissions") != expected_judges:
            raise ValueError("standard report judge count does not match status")
    finally:
        repository.close()
    return report


def _submit_judge(
    vm_binary: Path,
    challenge: Path,
    *,
    campaign_token: str,
    guess: str,
) -> Mapping[str, object]:
    completed = subprocess.run(
        [
            str(vm_binary),
            "judge",
            "--challenge",
            str(challenge),
            "--campaign-token",
            campaign_token,
            "--guess",
            guess,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"standard judge failed: {completed.stderr.strip()}")
    try:
        decoded: object = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("standard judge returned invalid JSON") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("standard judge response is not an object")
    return cast("dict[str, object]", decoded)


def _require_standard_profile(profile: Mapping[str, object]) -> None:
    expected: dict[str, object] = {
        "profile_version": "1.0",
        "name": "standard",
        "semantic_version": "0.1.0",
        "lanes": 8,
        "secret_cells": 8,
        "hidden_permutation": False,
        "hidden_salts": False,
        "bucket_width": 4,
        "noise_mode": "bounded_seeded",
        "noise_bound": 1,
    }
    mismatches = [key for key, value in expected.items() if profile.get(key) != value]
    if mismatches:
        raise ValueError(f"unsupported standard profile fields: {mismatches}")


def _load_profile(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            decoded = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError("cannot read public standard profile") from error
    return cast("dict[str, object]", decoded)


def _secret_from_domains(domains: list[set[int]]) -> str:
    if any(len(domain) != 1 for domain in domains):
        raise ValueError("cannot render a non-unique factorized secret")
    return "".join(format(next(iter(domain)), "x") for domain in domains)


def _domain_fingerprint(lane: int, epoch: int, domain: frozenset[int]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"lane": lane, "epoch": epoch, "domain": sorted(domain)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


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
            raise RuntimeError("short write while persisting standard report")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
