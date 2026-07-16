#!/usr/bin/env python3
"""Evaluate M8 state learning against real research-profile SphinxVM campaigns."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from sphinx_interrogator.constraint_ir import ConstraintProgram, Expr, NamedAssumption, Sort
from sphinx_interrogator.hypothesis_persistence import CampaignHypotheses
from sphinx_interrogator.learner import (
    AalpyMealyLearner,
    ExactHistoryLearner,
    LearnedMealyMachine,
    OneStateLearner,
    generated_sequences,
    state_model_provenance,
)
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.research_state import (
    MEASURE_HIGH,
    MEASURE_SYMBOL,
    STEP_SYMBOL,
    MeasurementCalibration,
    MembershipTrace,
    ResearchMacroConfig,
    calibrate_measurement,
    evaluate_model_with_traces,
    execute_membership_sequence,
    measure_program,
    research_alphabet,
    step_program,
)
from sphinx_interrogator.solver import ConstraintGroup
from sphinx_interrogator.target_model import SBOX4
from sphinx_trusted_runtime import (
    ChallengeBundle,
    create_challenge,
    create_private_root,
    launch_endpoints,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "benchmarks/profiles/research.toml"


@dataclass(frozen=True, slots=True)
class PublicCampaignContext:
    """Public challenge metadata for one launched research campaign."""

    campaign_index: int
    challenge_id: str
    commitment: str
    public_profile_sha256: str
    public_directory: str

    def to_data(self) -> dict[str, object]:
        """Return report-safe public campaign data."""
        return {
            "campaign_index": self.campaign_index,
            "challenge_id": self.challenge_id,
            "commitment": self.commitment,
            "public_profile_sha256": self.public_profile_sha256,
            "public_directory": self.public_directory,
        }


@dataclass(slots=True)
class OracleCost:
    """Cost counters for real public VM execution."""

    membership_words: int = 0
    logical_queries: int = 0
    physical_executions: int = 0
    hard_resets: int = 0
    challenge_campaigns: int = 0

    def add_calibration(self, calibration: MeasurementCalibration) -> None:
        """Account for hard-reset calibration executions."""
        executions = len(calibration.observations)
        self.logical_queries += executions
        self.physical_executions += executions
        self.hard_resets += executions

    def add_trace(self, trace: MembershipTrace) -> None:
        """Account for one membership word."""
        if trace.sequence:
            self.membership_words += 1
            self.hard_resets += 1
        self.logical_queries += len(trace.steps)
        self.physical_executions += len(trace.steps)

    def combine(self, other: OracleCost) -> OracleCost:
        """Return a summed cost object."""
        return OracleCost(
            membership_words=self.membership_words + other.membership_words,
            logical_queries=self.logical_queries + other.logical_queries,
            physical_executions=self.physical_executions + other.physical_executions,
            hard_resets=self.hard_resets + other.hard_resets,
            challenge_campaigns=self.challenge_campaigns + other.challenge_campaigns,
        )

    def to_data(self) -> dict[str, int]:
        """Return stable JSON data."""
        return {
            "membership_words": self.membership_words,
            "logical_queries": self.logical_queries,
            "physical_executions": self.physical_executions,
            "hard_resets": self.hard_resets,
            "challenge_campaigns": self.challenge_campaigns,
        }


@dataclass(slots=True)
class WireArchive:
    """Public raw request/response lines indexed by request ID."""

    lines: dict[str, tuple[str, str]] = field(default_factory=dict)

    def record(self, request_line: str, response_line: str) -> None:
        """Store one public wire exchange from the VM client recorder."""
        request = json.loads(request_line)
        if not isinstance(request, dict):
            raise TypeError("recorded request must be a JSON object")
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise TypeError("recorded request lacks a request_id")
        self.lines[request_id] = (request_line, response_line)


class RotatingResearchOracle:
    """Membership oracle backed by generic, budget-bounded research campaigns."""

    def __init__(
        self,
        *,
        binary: Path,
        trusted_root: Path,
        output_root: Path,
        namespace: str,
        role: str,
        config: ResearchMacroConfig,
        wire_archive: WireArchive,
        max_membership_words_per_campaign: int,
        calibration_repetitions: int,
    ) -> None:
        if max_membership_words_per_campaign < 1:
            raise ValueError("max membership words per campaign must be positive")
        session_safe_limit = 64 - (4 * calibration_repetitions)
        if session_safe_limit < 1:
            raise ValueError("calibration repetitions leave no public sessions for learning")
        self.binary = binary
        self.trusted_root = trusted_root
        self.output_root = output_root
        self.namespace = namespace
        self.role = role
        self.config = config
        self.wire_archive = wire_archive
        self.max_membership_words_per_campaign = min(
            max_membership_words_per_campaign,
            session_safe_limit,
        )
        self.calibration_repetitions = calibration_repetitions
        self.cost = OracleCost()
        self.traces: list[MembershipTrace] = []
        self.calibrations: list[MeasurementCalibration] = []
        self.campaigns: list[PublicCampaignContext] = []
        self.request_context: dict[str, PublicCampaignContext] = {}
        self.request_calibration: dict[str, MeasurementCalibration] = {}
        self._stack: ExitStack | None = None
        self._client: VmClient | None = None
        self._calibration: MeasurementCalibration | None = None
        self._campaign_index = 0
        self._words_in_campaign = 0
        self._word_index = 0

    def close(self) -> None:
        """Close any active VM client and endpoint process."""
        if self._stack is not None:
            self._stack.close()
        self._stack = None
        self._client = None
        self._calibration = None
        self._words_in_campaign = 0

    def __call__(self, sequence: tuple[str, ...]) -> tuple[str, ...]:
        """MembershipOracle-compatible entry point."""
        return self.trace(sequence).outputs

    def trace(self, sequence: Sequence[str]) -> MembershipTrace:
        """Execute or return one empty membership trace."""
        word = tuple(sequence)
        if not word:
            return MembershipTrace((), (), ())
        if (
            self._client is None
            or self._words_in_campaign >= self.max_membership_words_per_campaign
        ):
            self._start_campaign()
        if self._client is None or self._calibration is None:
            raise RuntimeError("research oracle campaign did not initialize")
        self._word_index += 1
        request_prefix = f"{self.role}-word-{self._word_index:06d}"
        trace = execute_membership_sequence(
            self._client,
            word,
            calibration=self._calibration,
            config=self.config,
            session_id=f"{self.role}-session-{self._word_index:06d}",
            logical_batch_id=f"{self.role}-batch-{self._word_index:06d}",
            request_prefix=request_prefix,
        )
        self._words_in_campaign += 1
        self.cost.add_trace(trace)
        self.traces.append(trace)
        context = self.campaigns[-1]
        for request_id in trace.request_ids:
            self.request_context[request_id] = context
            self.request_calibration[request_id] = self._calibration
        return trace

    def _start_campaign(self) -> None:
        self.close()
        self._campaign_index += 1
        opaque = hashlib.sha256(
            f"m8:{self.namespace}:{self.role}:{self._campaign_index}".encode()
        ).hexdigest()[:20]
        challenge_root = self.trusted_root / f"bundle-independent-{opaque}"
        campaign_private_root = self.trusted_root / f"private-root-{opaque}.bin"
        if not campaign_private_root.exists():
            create_private_root(self.binary, campaign_private_root)
        challenge_id = f"challenge-{self._campaign_index:04d}"
        bundle = _ensure_challenge(
            self.binary,
            profile=PROFILE,
            output=challenge_root,
            private_root_file=campaign_private_root,
            challenge_id=challenge_id,
            campaign_label=f"campaign-{opaque}",
            fault="reference",
        )
        public = _load_public_challenge(bundle.public_directory)
        context = PublicCampaignContext(
            campaign_index=self._campaign_index,
            challenge_id=_string(public, "challenge_id"),
            commitment=_string(public, "commitment"),
            public_profile_sha256=_string(public, "profile_sha256"),
            public_directory=_portable_path(bundle.public_directory, self.output_root),
        )
        stack = ExitStack()
        endpoints = stack.enter_context(
            launch_endpoints(
                self.binary,
                bundle,
                socket_directory=_socket_directory(self.namespace, self.role, self._campaign_index),
                with_judge=False,
            )
        )
        client = stack.enter_context(
            VmClient.connect_unix(
                endpoints.vm_socket,
                timeout_seconds=5.0,
                exchange_recorder=self.wire_archive.record,
            )
        )
        hello = client.hello()
        if hello.profile_name != "research":
            stack.close()
            raise RuntimeError(f"expected research profile, got {hello.profile_name}")
        try:
            calibration = calibrate_measurement(
                client,
                config=self.config,
                session_prefix=f"{self.role}-campaign-{self._campaign_index:04d}",
                request_prefix=f"{self.role}-campaign-{self._campaign_index:04d}",
                logical_batch_id=f"{self.role}-calibration-{self._campaign_index:04d}",
                repetitions=self.calibration_repetitions,
            )
        except Exception:
            stack.close()
            raise
        self._stack = stack
        self._client = client
        self._calibration = calibration
        self._words_in_campaign = 0
        self.calibrations.append(calibration)
        self.campaigns.append(context)
        self.cost.challenge_campaigns += 1
        self.cost.add_calibration(calibration)
        for observation in calibration.observations:
            self.request_context[observation.request_id] = context
            self.request_calibration[observation.request_id] = calibration


def parse_args() -> argparse.Namespace:
    """Parse state-learning evaluation options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "runs/state-learning-m8")
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--max-words-per-campaign", type=int, default=50)
    parser.add_argument("--calibration-repetitions", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    """Run no-learner, exact-history, and learned-state variants on real SphinxVM."""
    args = parse_args()
    if args.max_depth < 1:
        raise ValueError("--max-depth must be positive")
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        print("SPHINX_VM_BINARY is required", file=sys.stderr)
        return 2
    binary = Path(configured).resolve()
    if not binary.is_file():
        print(f"SphinxVM binary does not exist: {binary}", file=sys.stderr)
        return 2

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    namespace = hashlib.sha256(str(output).encode()).hexdigest()[:16]
    trusted_root = ROOT / "runs/.trusted-state-learning-m8" / namespace
    trusted_root.mkdir(parents=True, exist_ok=True)

    config = ResearchMacroConfig()
    alphabet = research_alphabet()
    held_out = generated_sequences(alphabet.input_symbols, max_depth=args.max_depth)
    wire_archive = WireArchive()
    oracles: list[RotatingResearchOracle] = []
    started = time.perf_counter()
    try:
        no_oracle = _oracle(
            binary,
            trusted_root,
            output,
            namespace,
            "no-learner",
            config,
            wire_archive,
            args,
        )
        oracles.append(no_oracle)
        singleton_outputs = {
            symbol: no_oracle.trace((symbol,)).outputs[-1]
            for symbol in (STEP_SYMBOL, MEASURE_SYMBOL)
        }
        no_learner = OneStateLearner().learn(
            model_id="research-no-learner",
            alphabet=alphabet,
            outputs_by_symbol=singleton_outputs,
        )

        exact_oracle = _oracle(
            binary,
            trusted_root,
            output,
            namespace,
            "exact-history",
            config,
            wire_archive,
            args,
        )
        oracles.append(exact_oracle)
        exact = ExactHistoryLearner().learn(
            model_id="research-exact-history",
            alphabet=alphabet,
            oracle=exact_oracle,
            maximum_depth=args.max_depth,
        )

        learned_oracle = _oracle(
            binary,
            trusted_root,
            output,
            namespace,
            "learned-state",
            config,
            wire_archive,
            args,
        )
        oracles.append(learned_oracle)
        learned = AalpyMealyLearner(max_states=6).learn(
            model_id="research-aalpy-lstar",
            alphabet=alphabet,
            oracle=learned_oracle,
            held_out_sequences=held_out,
        )

        held_out_oracle = _oracle(
            binary,
            trusted_root,
            output,
            namespace,
            "held-out",
            config,
            wire_archive,
            args,
        )
        oracles.append(held_out_oracle)
        held_out_traces = tuple(held_out_oracle.trace(sequence) for sequence in held_out)

        variants = [
            _variant("no_learner", no_learner, held_out_traces, no_oracle),
            _variant("exact_history", exact, held_out_traces, exact_oracle),
            _variant("learned_state", learned, held_out_traces, learned_oracle),
        ]
        by_mode = {variant["mode"]: variant for variant in variants}
        targets = {
            "exact_history_accuracy_eq_1": by_mode["exact_history"]["held_out_accuracy"] == 1.0,
            "learned_state_accuracy_ge_0_95": (
                float(by_mode["learned_state"]["held_out_accuracy"]) >= 0.95
            ),
            "learned_state_beats_no_learner": (
                float(by_mode["learned_state"]["held_out_accuracy"])
                > float(by_mode["no_learner"]["held_out_accuracy"])
            ),
            "state_model_counterexample_retracted": False,
        }
        retraction = _record_retraction_demo(
            output,
            no_learner,
            by_mode["no_learner"],
            held_out_traces,
            held_out_oracle,
            wire_archive,
        )
        targets["state_model_counterexample_retracted"] = bool(retraction["retracted_groups"])
        total_cost = OracleCost()
        for oracle in oracles:
            total_cost = total_cost.combine(oracle.cost)
        state_conditioned_inference = _record_state_conditioned_inference(
            output,
            learned,
            held_out_traces,
            held_out_oracle,
            wire_archive,
            config,
        )
        report = {
            "report_version": "2.0",
            "profile_name": "research",
            "fixture": "real-sphinxvm-research-soft-reset",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "private_artifacts_included": False,
            "shared_private_root": False,
            "macro": _macro_data(config),
            "alphabet": alphabet.to_data(),
            "held_out_sequences": len(held_out_traces),
            "held_out_evidence": {
                "cost": held_out_oracle.cost.to_data(),
                "traces": [trace.to_data() for trace in held_out_traces],
            },
            "variants": variants,
            "campaigns": {
                oracle.role: {
                    "public_campaigns": [campaign.to_data() for campaign in oracle.campaigns],
                    "calibrations": [calibration.to_data() for calibration in oracle.calibrations],
                }
                for oracle in oracles
            },
            "cost": total_cost.to_data(),
            "state_conditioned_inference": state_conditioned_inference,
            "retraction_demo": retraction,
            "targets_met": targets,
        }
    finally:
        for oracle in reversed(oracles):
            oracle.close()

    schema = json.loads((ROOT / "spec/state-learning-report.schema.json").read_text("utf-8"))
    jsonschema.Draft202012Validator(schema).validate(report)
    _write_json(output / "state-learning-report.json", report)
    _write_markdown(output / "state-learning-report.md", report)
    print(json.dumps(targets, indent=2, sort_keys=True))
    return int(not all(targets.values()))


def _oracle(
    binary: Path,
    trusted_root: Path,
    output: Path,
    namespace: str,
    role: str,
    config: ResearchMacroConfig,
    wire_archive: WireArchive,
    args: argparse.Namespace,
) -> RotatingResearchOracle:
    return RotatingResearchOracle(
        binary=binary,
        trusted_root=trusted_root,
        output_root=output,
        namespace=namespace,
        role=role,
        config=config,
        wire_archive=wire_archive,
        max_membership_words_per_campaign=args.max_words_per_campaign,
        calibration_repetitions=args.calibration_repetitions,
    )


def _variant(
    mode: str,
    model: LearnedMealyMachine,
    held_out_traces: tuple[MembershipTrace, ...],
    oracle: RotatingResearchOracle,
) -> dict[str, object]:
    conformance = evaluate_model_with_traces(model, held_out_traces)
    trace_by_sequence = {trace.sequence: trace for trace in held_out_traces}
    counterexamples = []
    for counterexample in conformance.counterexamples[:10]:
        trace = trace_by_sequence[counterexample.sequence]
        counterexample_data = counterexample.to_data()
        counterexamples.append(
            {
                "input": counterexample_data["sequence"],
                "expected": counterexample_data["expected"],
                "observed": counterexample_data["observed"],
                "request_ids": list(trace.request_ids),
            }
        )
    return {
        "mode": mode,
        "model_id": model.model_id,
        "algorithm": model.algorithm,
        "status": model.status,
        "states": len(model.states),
        "held_out_accuracy": conformance.held_out_accuracy,
        "tested_sequences": conformance.tested_sequences,
        "exact_matches": conformance.exact_matches,
        "counterexamples": len(conformance.counterexamples),
        "counterexample_examples": counterexamples,
        "transition_coverage": conformance.transition_coverage,
        "artifact_digest": model.artifact_digest(),
        "training_cost": oracle.cost.to_data(),
        "training_membership_cache_digest": model.membership_cache_digest,
    }


def _record_retraction_demo(
    output: Path,
    no_learner: LearnedMealyMachine,
    no_learner_variant: Mapping[str, object],
    held_out_traces: tuple[MembershipTrace, ...],
    held_out_oracle: RotatingResearchOracle,
    wire_archive: WireArchive,
) -> dict[str, object]:
    examples = no_learner_variant.get("counterexample_examples")
    if not isinstance(examples, list) or not examples:
        return {"status": "blocked", "reason": "no no-learner counterexample was observed"}
    first = examples[0]
    if not isinstance(first, dict):
        raise TypeError("counterexample example must be an object")
    sequence = tuple(_string_list(first, "input"))
    trace = next(item for item in held_out_traces if item.sequence == sequence)
    context = held_out_oracle.request_context[trace.request_ids[0]]
    digest = hashlib.sha256(
        json.dumps(trace.to_data(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]
    repository_root = output / f"retraction-demo-{digest}"
    if repository_root.exists():
        shutil.rmtree(repository_root)
    repository = CampaignRepository.create(
        repository_root,
        CampaignManifest(
            campaign_id=f"m8-retraction-{digest}",
            challenge_id=context.challenge_id,
            challenge_commitment=context.commitment,
            profile_name="research",
            semantic_version="0.1.0",
            public_profile_sha256=context.public_profile_sha256,
            seed=800_001,
            minimum_certificate_strength="exhaustive-enumeration",
            logical_query_budget=1_000,
            physical_execution_budget=20_000,
            hard_reset_budget=100,
        ),
    )
    try:
        query_ids = []
        for position, request_id in enumerate(trace.request_ids):
            request_line, response_line = wire_archive.lines[request_id]
            request = json.loads(request_line)
            if not isinstance(request, dict):
                raise TypeError("archived request must be an object")
            program = _string(request, "program")
            query_id = f"counterexample-query-{position}"
            query_ids.append(query_id)
            repository.append_event(
                event_id=f"query:{query_id}",
                kind="query_created",
                logical_time=0,
                payload={
                    "query_id": query_id,
                    "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
                    "program_text": program,
                    "expires_after": None,
                },
            )
        batch_id = "m8-counterexample-batch"
        repository.append_event(
            event_id=f"batch:{batch_id}",
            kind="batch_scheduled",
            logical_time=0,
            payload={
                "batch_id": batch_id,
                "seed": 800_001,
                "schedule": query_ids,
                "status": "complete",
            },
        )
        for position, request_id in enumerate(trace.request_ids):
            request_line, response_line = wire_archive.lines[request_id]
            repository.record_raw_execution(
                execution_id=f"counterexample-execution-{position}",
                query_id=query_ids[position],
                batch_id=batch_id,
                position=position,
                request_line=request_line,
                response_line=response_line,
                logical_time=1,
            )
        certificate_id = "m8-state-counterexample-certificate"
        relation_instance_id = "m8-state-counterexample-relation"
        repository.append_event(
            event_id=f"certificate:{certificate_id}",
            kind="certificate_registered",
            logical_time=2,
            payload={
                "certificate_id": certificate_id,
                "certificate": {
                    "proof_method": "held-out-public-replay",
                    "request_ids": list(trace.request_ids),
                },
            },
        )
        repository.append_event(
            event_id=f"relation:{relation_instance_id}",
            kind="relation_recorded",
            logical_time=2,
            payload={
                "relation_instance_id": relation_instance_id,
                "relation_id": "m8-state-counterexample/v1",
                "certificate_id": certificate_id,
                "relation": {
                    "sequence": list(trace.sequence),
                    "observed": list(trace.outputs),
                    "expected": first["expected"],
                },
            },
        )
        hypotheses = CampaignHypotheses(repository)
        hypotheses.record_state_model(no_learner, logical_time=3)
        group_id = "constraint:m8-state-conditioned-evidence"
        predicted_high = _first_measure_position(first.get("expected"), MEASURE_HIGH)
        if predicted_high is None:
            return {
                "status": "blocked",
                "reason": "no model-predicted high measurement was available",
            }
        calibration = held_out_oracle.request_calibration[trace.request_ids[predicted_high]]
        states_before = _states_before(no_learner, trace.sequence)
        state_label = states_before[predicted_high]
        candidate_values = _effective_nibble_values(
            anchor_bank=calibration.anchor_bank,
            token=0,
            epoch=0,
        )
        program = _state_conditioned_constraint_program(
            group_id=group_id,
            model_id=no_learner.model_id,
            state_label=state_label,
            candidate_values=candidate_values,
            source_request_ids=trace.request_ids,
            states=no_learner.states,
        )
        group = ConstraintGroup(
            group_id,
            program,
            hard=True,
            provenance=(
                *trace.request_ids,
                *state_model_provenance(no_learner.model_id, "q0"),
                "projection:effective_nibble_lane_0",
            ),
        )
        hypotheses.add_group(
            constraint_id=group_id,
            group=group,
            relation_instance_id=relation_instance_id,
            certificate_id=certificate_id,
            source_request_ids=trace.request_ids,
            approximation="state-conditioned-evidence",
            logical_time=4,
        )
        retracted = hypotheses.retract_state_model_constraints(
            no_learner.model_id,
            logical_time=5,
            reason="held-out public counterexample: " + ",".join(trace.request_ids),
        )
        materialized_digest = repository.database.digest()
        event_count = len(repository.events)
    finally:
        repository.close()
    return {
        "status": "retracted",
        "repository": _portable_path(repository_root, output),
        "state_model_id": no_learner.model_id,
        "counterexample": {
            "input": list(trace.sequence),
            "expected": first["expected"],
            "observed": list(trace.outputs),
            "request_ids": list(trace.request_ids),
        },
        "constraint_group_id": group_id,
        "constraint": {
            "projection_scope": "effective_nibble_lane_0",
            "state_label": state_label,
            "effective_nibble_candidates": list(candidate_values),
            "ir_sha256": hashlib.sha256(program.canonical_json().encode()).hexdigest(),
            "literal_true": program.assertion == Expr.literal(Sort.bool(), True),
        },
        "retracted_groups": list(retracted),
        "materialized_digest": materialized_digest,
        "event_count": event_count,
    }


def _record_state_conditioned_inference(
    output: Path,
    learned: LearnedMealyMachine,
    held_out_traces: tuple[MembershipTrace, ...],
    held_out_oracle: RotatingResearchOracle,
    wire_archive: WireArchive,
    config: ResearchMacroConfig,
) -> dict[str, object]:
    """Persist one non-trivial learned-state-conditioned secret projection."""
    del config
    selected = _select_high_measurement(learned, held_out_traces)
    if selected is None:
        return {"status": "blocked", "reason": "no correctly predicted high measurement found"}
    trace, position, state_label = selected
    context = held_out_oracle.request_context[trace.request_ids[position]]
    calibration = held_out_oracle.request_calibration[trace.request_ids[position]]
    candidate_values = _effective_nibble_values(
        anchor_bank=calibration.anchor_bank,
        token=0,
        epoch=0,
    )
    digest = hashlib.sha256(
        json.dumps(
            {
                "model": learned.artifact_digest(),
                "trace": trace.to_data(),
                "position": position,
                "state": state_label,
                "candidates": candidate_values,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:12]
    repository_root = output / f"state-inference-{digest}"
    if repository_root.exists():
        shutil.rmtree(repository_root)
    repository = CampaignRepository.create(
        repository_root,
        CampaignManifest(
            campaign_id=f"m8-state-inference-{digest}",
            challenge_id=context.challenge_id,
            challenge_commitment=context.commitment,
            profile_name="research",
            semantic_version="0.1.0",
            public_profile_sha256=context.public_profile_sha256,
            seed=800_101,
            minimum_certificate_strength="exhaustive-enumeration",
            logical_query_budget=1_000,
            physical_execution_budget=20_000,
            hard_reset_budget=100,
        ),
    )
    group_id = "constraint:m8-learned-state-bank"
    certificate_id = "m8-learned-state-bank-certificate"
    relation_instance_id = "m8-learned-state-bank-relation"
    try:
        query_ids = _record_trace_queries(repository, trace, wire_archive, logical_time=0)
        batch_id = "m8-learned-state-bank-batch"
        repository.append_event(
            event_id=f"batch:{batch_id}",
            kind="batch_scheduled",
            logical_time=0,
            payload={
                "batch_id": batch_id,
                "seed": 800_101,
                "schedule": query_ids,
                "status": "complete",
            },
        )
        _record_trace_executions(
            repository,
            trace,
            wire_archive,
            query_ids=query_ids,
            batch_id=batch_id,
            logical_time=1,
        )
        repository.append_event(
            event_id=f"certificate:{certificate_id}",
            kind="certificate_registered",
            logical_time=2,
            payload={
                "certificate_id": certificate_id,
                "certificate": {
                    "proof_method": "learned-state-held-out-public-replay",
                    "model_id": learned.model_id,
                    "model_digest": learned.artifact_digest(),
                    "request_ids": list(trace.request_ids),
                },
            },
        )
        repository.append_event(
            event_id=f"relation:{relation_instance_id}",
            kind="relation_recorded",
            logical_time=2,
            payload={
                "relation_instance_id": relation_instance_id,
                "relation_id": "m8-learned-state-bank/v1",
                "certificate_id": certificate_id,
                "relation": {
                    "sequence": list(trace.sequence),
                    "outputs": list(trace.outputs),
                    "measurement_position": position,
                    "state_label": state_label,
                    "anchor_bank": calibration.anchor_bank,
                    "threshold_bucket": calibration.threshold_bucket,
                    "projection_scope": "effective_nibble_lane_0",
                    "candidate_values": list(candidate_values),
                },
            },
        )
        hypotheses = CampaignHypotheses(repository)
        hypotheses.record_state_model(learned, logical_time=3)
        program = _state_conditioned_constraint_program(
            group_id=group_id,
            model_id=learned.model_id,
            state_label=state_label,
            candidate_values=candidate_values,
            source_request_ids=trace.request_ids,
            states=learned.states,
        )
        group = ConstraintGroup(
            group_id,
            program,
            hard=True,
            provenance=(
                *trace.request_ids,
                *state_model_provenance(learned.model_id, state_label),
                "projection:effective_nibble_lane_0",
            ),
        )
        hypotheses.add_group(
            constraint_id=group_id,
            group=group,
            relation_instance_id=relation_instance_id,
            certificate_id=certificate_id,
            source_request_ids=trace.request_ids,
            approximation="exact-state-conditioned-effective-nibble",
            logical_time=4,
        )
        solve = hypotheses.solve()
        snapshot = hypotheses.snapshot(snapshot_id="m8-state-conditioned", logical_time=5, limit=64)
        materialized_digest = repository.database.digest()
        event_count = len(repository.events)
    finally:
        repository.close()
    return {
        "status": "complete",
        "model_id": learned.model_id,
        "model_digest": learned.artifact_digest(),
        "repository": _portable_path(repository_root, output),
        "projection_scope": "effective_nibble_lane_0",
        "projection_note": (
            "research profiles hide lane permutation and salts; this constrains the "
            "public macro's effective secret nibble, not a raw unsalted lane value"
        ),
        "nontrivial_constraints": 1,
        "constraint_groups": [
            {
                "group_id": group_id,
                "state_label": state_label,
                "source_request_ids": list(trace.request_ids),
                "measurement_request_id": trace.request_ids[position],
                "measurement_position": position,
                "anchor_bank": calibration.anchor_bank,
                "output": trace.steps[position].output,
                "effective_nibble_candidates_before": 16,
                "effective_nibble_candidates_after": len(candidate_values),
                "effective_nibble_candidates": list(candidate_values),
                "retractable_by": f"state-model:{learned.model_id}",
                "ir_sha256": hashlib.sha256(program.canonical_json().encode()).hexdigest(),
            }
        ],
        "solver_status": solve.status.value,
        "candidate_snapshot": snapshot.to_data(),
        "materialized_digest": materialized_digest,
        "event_count": event_count,
    }


def _record_trace_queries(
    repository: CampaignRepository,
    trace: MembershipTrace,
    wire_archive: WireArchive,
    *,
    logical_time: int,
) -> list[str]:
    query_ids = []
    for position, request_id in enumerate(trace.request_ids):
        request_line, _response_line = wire_archive.lines[request_id]
        request = json.loads(request_line)
        if not isinstance(request, dict):
            raise TypeError("archived request must be an object")
        program = _string(request, "program")
        query_id = f"trace-query-{position}"
        query_ids.append(query_id)
        repository.append_event(
            event_id=f"query:{query_id}",
            kind="query_created",
            logical_time=logical_time,
            payload={
                "query_id": query_id,
                "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
                "program_text": program,
                "expires_after": None,
            },
        )
    return query_ids


def _record_trace_executions(
    repository: CampaignRepository,
    trace: MembershipTrace,
    wire_archive: WireArchive,
    *,
    query_ids: Sequence[str],
    batch_id: str,
    logical_time: int,
) -> None:
    if len(query_ids) != len(trace.request_ids):
        raise ValueError("query IDs must align with trace request IDs")
    for position, request_id in enumerate(trace.request_ids):
        request_line, response_line = wire_archive.lines[request_id]
        repository.record_raw_execution(
            execution_id=f"trace-execution-{position}",
            query_id=query_ids[position],
            batch_id=batch_id,
            position=position,
            request_line=request_line,
            response_line=response_line,
            logical_time=logical_time,
        )


def _select_high_measurement(
    model: LearnedMealyMachine,
    traces: tuple[MembershipTrace, ...],
) -> tuple[MembershipTrace, int, str] | None:
    for trace in traces:
        if model.predict(trace.sequence) != trace.outputs:
            continue
        states_before = _states_before(model, trace.sequence)
        for position, step in enumerate(trace.steps):
            if step.symbol == MEASURE_SYMBOL and step.output == MEASURE_HIGH:
                return trace, position, states_before[position]
    return None


def _first_measure_position(raw_outputs: object, output_symbol: str) -> int | None:
    if not isinstance(raw_outputs, list):
        return None
    for position, item in enumerate(raw_outputs):
        if item == output_symbol:
            return position
    return None


def _states_before(model: LearnedMealyMachine, sequence: Sequence[str]) -> tuple[str, ...]:
    state = model.initial_state
    states: list[str] = []
    for symbol in sequence:
        states.append(state)
        state = model.transitions[state][symbol].next_state
    return tuple(states)


def _effective_nibble_values(*, anchor_bank: int, token: int, epoch: int) -> tuple[str, ...]:
    if not 0 <= anchor_bank <= 3:
        raise ValueError("anchor bank must fit in two bits")
    if not 0 <= token <= 15:
        raise ValueError("token must fit in four bits")
    if epoch not in {0, 1}:
        raise ValueError("epoch must be 0 or 1")
    del token
    return tuple(
        format(value, "x")
        for value in range(16)
        if ((SBOX4[value] >> (2 * epoch)) & 0b11) == anchor_bank
    )


def _state_conditioned_constraint_program(
    *,
    group_id: str,
    model_id: str,
    state_label: str,
    candidate_values: tuple[str, ...],
    source_request_ids: tuple[str, ...],
    states: tuple[str, ...],
) -> ConstraintProgram:
    if state_label not in states:
        raise ValueError("state label must be part of the learned model")
    if not candidate_values or len(candidate_values) >= 16:
        raise ValueError("state-conditioned secret projection must be non-trivial")
    nibble_sort = Sort.finite(
        "effective_nibble_hex",
        tuple(format(value, "x") for value in range(16)),
    )
    state_sort = Sort.finite("learned_state_id", states)
    effective_nibble = Expr.variable("effective_nibble_lane_0", nibble_sort)
    learned_state = Expr.variable("learned_state", state_sort)
    state_clause = Expr.equal(learned_state, Expr.literal(state_sort, state_label))
    bank_clause = Expr.disjunction(
        tuple(
            Expr.equal(effective_nibble, Expr.literal(nibble_sort, value))
            for value in candidate_values
        )
    )
    provenance = (
        *source_request_ids,
        *state_model_provenance(model_id, state_label),
        "projection:effective_nibble_lane_0",
    )
    return ConstraintProgram(
        "1.0",
        (effective_nibble, learned_state),
        (
            NamedAssumption(
                name="m8_state_conditioned_bank",
                expression=bank_clause,
                group=group_id,
                provenance=provenance,
            ),
        ),
        Expr.conjunction((state_clause, bank_clause)),
    )


def _macro_data(config: ResearchMacroConfig) -> dict[str, object]:
    measure = measure_program(0, config)
    step = step_program(config)
    return {
        "macro_version": "research-soft-reset-phase/v1",
        "lane": config.lane,
        "token": config.token,
        "epoch": config.epoch,
        "measure_repeats": config.measure_repeats,
        "expected_fault_amplification_cycles": config.measure_repeats,
        "programs": {
            "step": {
                "static_cycles": step.static_cycles(),
                "instructions": step.resources().instructions,
                "sha256": hashlib.sha256(step.render().encode()).hexdigest(),
            },
            "measure": {
                "static_cycles": measure.static_cycles(),
                "instructions": measure.resources().instructions,
                "sha256": hashlib.sha256(measure.render().encode()).hexdigest(),
            },
        },
    }


def _ensure_challenge(
    binary: Path,
    *,
    profile: Path,
    output: Path,
    private_root_file: Path,
    challenge_id: str,
    campaign_label: str,
    fault: str,
) -> ChallengeBundle:
    if (output / "public/challenge.json").is_file():
        return ChallengeBundle(output / "public", output / "private", private_root_file)
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"challenge directory is partial or incompatible: {output}")
    if output.exists():
        output.rmdir()
    return create_challenge(
        binary,
        profile=profile,
        root=output,
        private_root_file=private_root_file,
        challenge_id=challenge_id,
        campaign_label=campaign_label,
        fault=fault,
    )


def _socket_directory(namespace: str, role: str, campaign_index: int) -> Path:
    role_digest = hashlib.sha256(role.encode()).hexdigest()[:6]
    return Path(tempfile.gettempdir()) / f"sphx-m8-{namespace[:8]}-{role_digest}-{campaign_index}"


def _load_public_challenge(public_directory: Path) -> Mapping[str, object]:
    decoded = json.loads((public_directory / "challenge.json").read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise TypeError("public challenge must be a JSON object")
    return decoded


def _write_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_markdown(path: Path, report: Mapping[str, object]) -> None:
    lines = [
        "# State Learning Evaluation",
        "",
        f"- Fixture: `{report['fixture']}`",
        f"- Held-out sequences: `{report['held_out_sequences']}`",
        f"- Private artifacts included: `{report['private_artifacts_included']}`",
        "",
        "| mode | states | held-out accuracy | counterexamples | training words | campaigns |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    variants = report.get("variants")
    if not isinstance(variants, list):
        raise TypeError("report variants must be a list")
    for variant in variants:
        if not isinstance(variant, dict):
            raise TypeError("variant must be an object")
        cost = _mapping(variant, "training_cost")
        lines.append(
            "| "
            f"{variant['mode']} | {variant['states']} | "
            f"{float(variant['held_out_accuracy']):.3f} | "
            f"{variant['counterexamples']} | "
            f"{cost['membership_words']} | {cost['challenge_campaigns']} |"
        )
    targets = _mapping(report, "targets_met")
    lines.extend(
        [
            "",
            "## Targets",
            "",
            *[f"- `{key}`: `{value}`" for key, value in sorted(targets.items())],
        ]
    )
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _portable_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a nonempty string")
    return value


def _string_list(data: Mapping[str, object], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be a list of strings")
    return value


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
