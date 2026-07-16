"""Bounded-noise standard-profile recovery through certified public relations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from sphinx_interrogator.certificates import ProofMethod
from sphinx_interrogator.constraints import ConstraintExtraction, ExtractionStatus
from sphinx_interrogator.frontier import (
    ActiveFrontier,
    FrontierCandidate,
    NoveltyStatus,
)
from sphinx_interrogator.harness import (
    DurableExecutionHarness,
    ExecutionSpec,
    balanced_pair_schedule,
)
from sphinx_interrogator.hypothesis_persistence import CampaignHypotheses
from sphinx_interrogator.knowledge_base import (
    InterrogationKnowledgeBase,
    QueryRecord,
    RelationRecord,
)
from sphinx_interrogator.model import ExecutionResult, OutcomeClass, RelationEvidence
from sphinx_interrogator.normalization import DecisionKind, PairDecision
from sphinx_interrogator.persistence import (
    CampaignManifest,
    CampaignRepository,
    CampaignResultStatus,
    normalize_campaign_result_status,
)
from sphinx_interrogator.protocol import submit_judge as submit_judge_request
from sphinx_interrogator.relations import TEMPLATE_REGISTRY, RelationInstance
from sphinx_interrogator.solver import SolverStatus
from sphinx_interrogator.synthesis import (
    BoundedRelationGrammar,
    CegisSynthesizer,
    DiverseCommittee,
    DrainedAnchorSwitchCandidate,
    RepeatAmplifyCandidate,
    ResourceBounds,
    SynthesisContext,
    SynthesisModel,
    SynthesisResult,
    SynthesisStatus,
    TypedCandidate,
    score_candidate,
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
    public_challenge: Path,
    vm_socket: Path,
    judge_socket: Path | None,
    run_directory: Path,
    campaign_seed: int,
    selector_mode: StandardSelectorMode = StandardSelectorMode.FULL,
    submit_judge: bool = True,
) -> StandardRecoveryResult:
    """Recover one 32-bit identity-profile secret using bounded hard evidence only."""
    wall_started = time.time()
    started = time.perf_counter()
    timing = _Timing()
    if campaign_seed < 0:
        raise ValueError("campaign seed must be nonnegative")
    if submit_judge and judge_socket is None:
        raise ValueError("judge socket is required when judge submission is enabled")
    public = _load_object(public_challenge / "challenge.json", "public challenge")
    profile_path = public_challenge / "profile.toml"
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
        knowledge = InterrogationKnowledgeBase()
        frontier = ActiveFrontier(repository)
        harness, client = DurableExecutionHarness.connect_unix(
            repository,
            socket_path=vm_socket,
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
                            knowledge=knowledge,
                            frontier=frontier,
                            logical_time=relation_index,
                        )
                        timing.synthesis_seconds += time.perf_counter() - selection_started
                        if selected is None:
                            break
                        used.add(selected.canonical_key())
                        if synthesis_result is not None:
                            cegis_refinements += len(synthesis_result.counterexamples)
                        relation = selected.lower(f"standard-{relation_index:03d}-l{lane}-e{epoch}")
                        execution_started = time.perf_counter()
                        last_results, extraction, decision = _execute_relation(
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
                        _record_knowledge(
                            knowledge,
                            relation,
                            last_results,
                            decision,
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
            if judge_socket is None:
                raise RuntimeError("judge socket disappeared after recovery validation")
            judge_response = submit_judge_request(
                judge_socket,
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
            status = CampaignResultStatus.MODEL_INCONSISTENT.value
        elif guessed_secret is None:
            status = CampaignResultStatus.CANDIDATE_SET.value
        elif judge_response is None or _boolean(judge_response, "accepted"):
            status = CampaignResultStatus.UNIQUE_EXACT.value
        else:
            status = CampaignResultStatus.TARGET_ERROR.value
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
                "knowledge_relations": len(knowledge.relations),
                "frontier_candidates": repository.database.table_count("frontier"),
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
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
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
    knowledge: InterrogationKnowledgeBase,
    frontier: ActiveFrontier,
    logical_time: int,
) -> tuple[TypedCandidate | None, SynthesisResult | None]:
    active_pad = (lane ^ epoch) & 3
    if mode in {StandardSelectorMode.FULL, StandardSelectorMode.SYNTHESIS_NO_KB}:
        grammar = BoundedRelationGrammar(
            lanes=(lane,),
            tokens=(0,),
            epochs=(epoch,),
            pads=(active_pad,),
            repeat_counts=(15,),
            include_anchor_switch=False,
            include_drained_anchor_switch=True,
            include_repeat_amplify=True,
            resources=ResourceBounds(combined_instructions=192),
        )
        candidates = tuple(
            candidate
            for candidate in grammar.all_candidates()
            if candidate.canonical_key() not in used
        )
        if not candidates:
            return None, None
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
        if mode is StandardSelectorMode.SYNTHESIS_NO_KB:
            return result.score.candidate, result

        scored = tuple(
            score_candidate(candidate, committee, result.context) for candidate in candidates
        )
        by_key = {candidate.canonical_key(): candidate for candidate in candidates}
        ranked_scores = [
            result.score,
            *(
                candidate_score
                for candidate_score in sorted(scored, key=lambda item: item.objective_key())
                if candidate_score.candidate.canonical_key()
                != result.score.candidate.canonical_key()
            ),
        ]
        objective_rank = {
            candidate_score.candidate.canonical_key(): rank
            for rank, candidate_score in enumerate(ranked_scores)
        }
        for candidate_score in scored:
            candidate = candidate_score.candidate
            if not isinstance(candidate, (DrainedAnchorSwitchCandidate, RepeatAmplifyCandidate)):
                raise RuntimeError("standard frontier received the wrong candidate type")
            candidate_suffix = hashlib.sha256(candidate.canonical_key().encode()).hexdigest()[:12]
            relation = candidate.lower(f"frontier-{logical_time:03d}-{candidate_suffix}")
            usage = _knowledge_usage(knowledge, candidate)
            frontier_candidate = FrontierCandidate(
                candidate_id=f"standard-frontier-{logical_time:03d}-{candidate_suffix}",
                structural_key=relation.instance_hash,
                relation_key=relation.relation_id,
                state_key="hard-reset/v1",
                observation_key="bucket:4:noise:1",
                partition_key=hashlib.sha256(
                    json.dumps(
                        candidate_score.to_data(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                semantic_key=candidate.canonical_key(),
                score=-(objective_rank[candidate.canonical_key()] + usage * 0.001),
                data={
                    "candidate": dict(candidate.hole_values()),
                    "synthesis_score": candidate_score.to_data(),
                    "objective_rank": objective_rank[candidate.canonical_key()],
                    "knowledge_prior_uses": usage,
                },
                expires_after=logical_time,
            )
            novelty = frontier.consider(frontier_candidate, logical_time=logical_time)
            if novelty.status is not NoveltyStatus.NOVEL:
                raise RuntimeError(f"full frontier rejected a bounded candidate: {novelty.reason}")
        chosen = frontier.select(logical_time=logical_time)
        if chosen is None:
            raise RuntimeError("full frontier contained no selectable candidate")
        try:
            return by_key[chosen.semantic_key], result
        except KeyError as error:
            raise RuntimeError("frontier selected an unknown candidate") from error
    candidates = tuple(
        RepeatAmplifyCandidate(lane, 0, epoch, anchor, active_pad, 16)
        for anchor in range(4)
        if RepeatAmplifyCandidate(lane, 0, epoch, anchor, active_pad, 16).canonical_key()
        not in used
    )
    if not candidates:
        return None, None
    if mode is StandardSelectorMode.RANDOM:
        selected = min(
            candidates,
            key=lambda candidate: hashlib.sha256(
                f"{campaign_seed}:{candidate.canonical_key()}".encode()
            ).hexdigest(),
        )
    elif mode is StandardSelectorMode.STATELESS:
        selected = max(candidates, key=lambda candidate: candidate.canonical_key())
    elif mode is StandardSelectorMode.KB_NO_SYNTHESIS:
        selected = min(
            candidates,
            key=lambda candidate: (
                _knowledge_usage(knowledge, candidate),
                candidate.canonical_key(),
            ),
        )
    else:
        raise RuntimeError(f"unimplemented standard selector mode: {mode.value}")
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
) -> tuple[tuple[ExecutionResult, ExecutionResult], ConstraintExtraction, PairDecision]:
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
    template = TEMPLATE_REGISTRY[relation.relation_id]
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
    return (source, follow_up), extraction, decision


def _knowledge_usage(
    knowledge: InterrogationKnowledgeBase,
    candidate: TypedCandidate,
) -> int:
    relation_id = candidate.lower("knowledge-usage").relation_id
    holes = candidate.hole_values()
    return sum(
        record.instance.relation_id == relation_id
        and all(record.instance.holes.get(key) == value for key, value in holes.items())
        for record in knowledge.relations.values()
    )


def _record_knowledge(
    knowledge: InterrogationKnowledgeBase,
    relation: RelationInstance,
    results: tuple[ExecutionResult, ExecutionResult],
    decision: PairDecision,
) -> None:
    source, follow_up = results
    knowledge.add_query(
        QueryRecord(
            relation.source_query_id,
            relation.source_program.render(),
            (source,),
            knowledge.step,
        )
    )
    knowledge.add_query(
        QueryRecord(
            relation.follow_up_query_ids[0],
            relation.follow_up_programs[0].render(),
            (follow_up,),
            knowledge.step,
        )
    )
    outcome = {
        DecisionKind.EXACT_GREATER: OutcomeClass.VIOLATED_POSITIVE,
        DecisionKind.BOUNDED_GREATER: OutcomeClass.VIOLATED_POSITIVE,
        DecisionKind.EXACT_LESS: OutcomeClass.VIOLATED_NEGATIVE,
        DecisionKind.BOUNDED_LESS: OutcomeClass.VIOLATED_NEGATIVE,
        DecisionKind.EXACT_EQUAL: OutcomeClass.HOLDS,
        DecisionKind.INCONCLUSIVE: OutcomeClass.INCONCLUSIVE,
        DecisionKind.INVALID: OutcomeClass.INCONCLUSIVE,
    }[decision.kind]
    delta = 0.0
    if decision.delta_interval is not None:
        delta = (decision.delta_interval.lower + decision.delta_interval.upper) / 2
    knowledge.add_relation(
        RelationRecord(
            relation,
            RelationEvidence(
                relation_instance_id=relation.instance_id,
                outcome=outcome,
                normalized_delta=delta,
                confidence=1.0 if decision.hard_eligible else 0.0,
                source_request_ids=decision.source_request_ids,
                metadata={"decision_kind": decision.kind.value},
            ),
            (),
        )
    )
    knowledge.advance()


def _existing_report(
    run_directory: Path,
    manifest: CampaignManifest,
) -> Mapping[str, object] | None:
    path = run_directory / "report.json"
    if not path.exists():
        return None
    report = _load_object(path, "standard report")
    status = report.get("status")
    if not isinstance(status, str):
        return None
    try:
        normative_status = normalize_campaign_result_status(status)
    except ValueError:
        return None
    if report.get("campaign_id") != manifest.campaign_id:
        return None
    if status != normative_status.value:
        report = dict(report)
        report["status"] = normative_status.value
        _write_json(path, report)
    repository = CampaignRepository.open(run_directory)
    try:
        if not repository.manifest.same_public_inputs(manifest):
            raise ValueError("standard report manifest does not match this challenge")
        artifacts = report.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError("standard report lacks artifact metadata")
        if artifacts.get("materialized_digest") != repository.database.digest():
            raise ValueError("standard report materialized digest does not replay")
        expected_judges = int(
            normative_status is CampaignResultStatus.UNIQUE_EXACT
            and report.get("judge") is not None
        )
        if repository.database.table_count("judge_submissions") != expected_judges:
            raise ValueError("standard report judge count does not match status")
        if repository.manifest.to_data()["manifest_version"] != "1.2":
            repository.finalize_manifest(
                status=normative_status,
                artifact_paths={
                    "report.json": run_directory / "report.json",
                    "events.jsonl": run_directory / "events.jsonl",
                    "campaign.sqlite3": run_directory / "campaign.sqlite3",
                },
            )
    finally:
        repository.close()
    return report


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


def _manifest_status(status: str) -> CampaignResultStatus:
    return normalize_campaign_result_status(status)


def _iso_time(timestamp: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


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
