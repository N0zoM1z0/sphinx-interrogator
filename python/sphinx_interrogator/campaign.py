"""Interrogation loop and public controller surfaces with auditable provenance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar

from sphinx_interrogator.knowledge_base import (
    InterrogationKnowledgeBase,
    QueryRecord,
    RelationRecord,
)
from sphinx_interrogator.model import RelationEvidence
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.relations import AnchorSwitchTemplate, RelationInstance
from sphinx_interrogator.solver import BankEqualityConstraint, SecretDomain
from sphinx_interrogator.statistics import bucket_midpoint, paired_location
from sphinx_interrogator.synthesis import GrammarGuidedSelector, QueryCandidate

_CONTROLLER_VERSION = "1.0"
_DEFAULT_RELATION_FAMILIES = (
    "anchor-switch/v1",
    "token-switch/v1",
    "epoch-switch/v1",
    "phase-shift/v1",
    "repeat-amplify/v1",
    "independent-swap/v1",
    "context-lift/v1",
    "register-rename/v1",
    "hard-replay/v1",
    "soft-history-contrast/v1",
)


class CampaignMode(StrEnum):
    """Auditable top-level interrogation selector modes."""

    INFER = "infer"
    LEARN_STATE = "learn-state"
    CALIBRATE = "calibrate"
    REPLAY = "replay"
    REDUCE = "reduce"
    DIVERSIFY = "diversify"


@dataclass(frozen=True, slots=True)
class ControllerContext:
    """Public selector inputs; private challenge state is intentionally absent."""

    secret_cells: int = 1
    used_candidates: tuple[QueryCandidate, ...] = ()
    relation_family: str = "anchor-switch/v1"
    state_model_id: str | None = None
    high_influence_group_ids: tuple[str, ...] = ()
    known_relation_families: tuple[str, ...] = _DEFAULT_RELATION_FAMILIES
    uncovered_relation_families: tuple[str, ...] = _DEFAULT_RELATION_FAMILIES
    noise_profile: str = "bounded"
    reducer_family: str = "repeat-amplify/v1"

    def __post_init__(self) -> None:
        if self.secret_cells < 1:
            raise ValueError("secret_cells must be positive")
        if not self.relation_family:
            raise ValueError("relation_family must be non-empty")
        if not self.reducer_family:
            raise ValueError("reducer_family must be non-empty")
        if not self.noise_profile:
            raise ValueError("noise_profile must be non-empty")

    def to_public_data(self) -> dict[str, object]:
        """Return a JSON-compatible summary that excludes private challenge data."""
        return {
            "secret_cells": self.secret_cells,
            "used_candidate_count": len(self.used_candidates),
            "relation_family": self.relation_family,
            "state_model_id": self.state_model_id,
            "high_influence_group_ids": list(self.high_influence_group_ids),
            "known_relation_families": list(self.known_relation_families),
            "uncovered_relation_families": list(self.uncovered_relation_families),
            "noise_profile": self.noise_profile,
            "reducer_family": self.reducer_family,
        }


@dataclass(frozen=True, slots=True)
class ControllerAction:
    """One deterministic controller decision with score and provenance."""

    mode: CampaignMode
    action_id: str
    priority: float
    reason: str
    payload: Mapping[str, object]
    score_components: Mapping[str, float]
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("action_id must be non-empty")
        if not self.reason:
            raise ValueError("reason must be non-empty")
        object.__setattr__(self, "payload", _freeze_public_mapping(self.payload))
        object.__setattr__(
            self,
            "score_components",
            MappingProxyType(dict(sorted(self.score_components.items()))),
        )

    def to_data(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible public report."""
        return {
            "mode": self.mode.value,
            "action_id": self.action_id,
            "priority": self.priority,
            "reason": self.reason,
            "payload": _public_data(self.payload),
            "score_components": dict(self.score_components),
            "provenance": list(self.provenance),
        }


class CampaignController:
    """Deterministic public selector facade for the main interrogation modes."""

    MODES: ClassVar[tuple[CampaignMode, ...]] = (
        CampaignMode.INFER,
        CampaignMode.LEARN_STATE,
        CampaignMode.CALIBRATE,
        CampaignMode.REPLAY,
        CampaignMode.REDUCE,
        CampaignMode.DIVERSIFY,
    )

    _MODE_INDEX: ClassVar[dict[CampaignMode, int]] = {
        mode: index for index, mode in enumerate(MODES)
    }

    def __init__(self, selector: GrammarGuidedSelector | None = None) -> None:
        """Create a controller over public selectors and artifact entrypoints."""
        self._selector = selector or GrammarGuidedSelector()

    def available_modes(self) -> tuple[CampaignMode, ...]:
        """Return the complete stable mode surface."""
        return self.MODES

    def plan(
        self,
        context: ControllerContext,
        *,
        allowed: Iterable[CampaignMode | str] | None = None,
    ) -> tuple[ControllerAction, ...]:
        """Build all eligible actions and sort them by deterministic priority."""
        allowed_modes = self._allowed_modes(allowed)
        builders = {
            CampaignMode.INFER: self._infer_action,
            CampaignMode.LEARN_STATE: self._learn_state_action,
            CampaignMode.CALIBRATE: self._calibrate_action,
            CampaignMode.REPLAY: self._replay_action,
            CampaignMode.REDUCE: self._reduce_action,
            CampaignMode.DIVERSIFY: self._diversify_action,
        }
        actions = tuple(builders[mode](context) for mode in self.MODES if mode in allowed_modes)
        if not actions:
            raise ValueError("at least one controller mode must be allowed")
        return tuple(sorted(actions, key=self._action_sort_key))

    def select(
        self,
        context: ControllerContext,
        *,
        allowed: Iterable[CampaignMode | str] | None = None,
    ) -> ControllerAction:
        """Return the highest-priority action for the public context."""
        return self.plan(context, allowed=allowed)[0]

    def plan_report(
        self,
        context: ControllerContext,
        *,
        allowed: Iterable[CampaignMode | str] | None = None,
    ) -> dict[str, object]:
        """Return an auditable JSON-compatible controller plan."""
        actions = self.plan(context, allowed=allowed)
        return {
            "controller_version": _CONTROLLER_VERSION,
            "black_box_boundary": "public-jsonl-process-only",
            "private_artifacts_included": False,
            "modes": [mode.value for mode in self.MODES],
            "eligible_modes": [action.mode.value for action in actions],
            "selected": actions[0].to_data(),
            "actions": [action.to_data() for action in actions],
            "context": context.to_public_data(),
        }

    def _allowed_modes(
        self, allowed: Iterable[CampaignMode | str] | None
    ) -> frozenset[CampaignMode]:
        if allowed is None:
            return frozenset(self.MODES)
        return frozenset(CampaignMode(mode) for mode in allowed)

    def _action_sort_key(self, action: ControllerAction) -> tuple[float, int, str]:
        return (-action.priority, self._MODE_INDEX[action.mode], action.action_id)

    def _infer_action(self, context: ControllerContext) -> ControllerAction:
        domain = SecretDomain(context.secret_cells)
        scored = self._selector.choose(domain, used=context.used_candidates)
        if scored is None:
            return ControllerAction(
                mode=CampaignMode.INFER,
                action_id="infer:no-novel-candidate",
                priority=15.0,
                reason="no novel public grammar candidate remains for the active domain",
                payload={
                    "status": "blocked",
                    "selector": "grammar-guided-cegis-v1",
                    "candidate_count": domain.candidate_count(),
                },
                score_components={
                    "candidate_reduction_proxy": 0.0,
                    "novelty": 0.0,
                    "cost_penalty": 0.0,
                },
                provenance=(
                    "SecretDomain",
                    "GrammarGuidedSelector.choose",
                ),
            )
        candidate = scored.query
        return ControllerAction(
            mode=CampaignMode.INFER,
            action_id=f"infer:{candidate.canonical_key()}",
            priority=100.0,
            reason="highest-scoring public grammar candidate splits the current domain",
            payload={
                "status": "ready",
                "selector": "grammar-guided-cegis-v1",
                "relation_family": context.relation_family,
                "candidate_key": candidate.canonical_key(),
                "holes": dict(candidate.hole_values()),
                "predicted_partition": scored.outcome_partition,
                "candidate_count": domain.candidate_count(),
                "entrypoint": "TutorialCampaign.step",
            },
            score_components={
                "candidate_reduction_proxy": scored.information_gain_bits,
                "novelty": 1.0,
                "cost_penalty": float(scored.static_cycles),
                "total": scored.score,
            },
            provenance=(
                "SecretDomain.public_domain",
                "GrammarGuidedSelector.score",
                "QueryCandidate.lower",
            ),
        )

    def _learn_state_action(self, context: ControllerContext) -> ControllerAction:
        state_uncertainty = 1.0 if context.state_model_id is None else 0.35
        state_model_id = context.state_model_id or "uninitialized"
        return ControllerAction(
            mode=CampaignMode.LEARN_STATE,
            action_id=f"learn-state:{state_model_id}",
            priority=88.0 if context.state_model_id is None else 55.0,
            reason="learn or refresh the public hidden-state abstraction before soft evidence",
            payload={
                "status": "ready",
                "state_model_id": state_model_id,
                "learner_mode": "learned-abstraction",
                "entrypoint": "just evaluate-state-learning",
                "required_profile": "research",
            },
            score_components={
                "state_uncertainty": state_uncertainty,
                "constraint_lift_proxy": 0.6,
                "cost_penalty": 0.4,
            },
            provenance=(
                "research_state.ActiveStateLearner",
                "runs/state-learning-m8/state-learning-report.json",
            ),
        )

    def _calibrate_action(self, context: ControllerContext) -> ControllerAction:
        return ControllerAction(
            mode=CampaignMode.CALIBRATE,
            action_id=f"calibrate:{context.noise_profile}",
            priority=78.0,
            reason="estimate public noise and relation reliability before hard extraction",
            payload={
                "status": "ready",
                "noise_profile": context.noise_profile,
                "schedule": "paired-randomized-anchor-sweep",
                "entrypoint": "sphinx-interrogate benchmark",
                "records_seed": True,
            },
            score_components={
                "noise_risk": 0.7,
                "reliability_gain": 0.8,
                "cost_penalty": 0.5,
            },
            provenance=(
                "statistics.paired_location",
                "benchmark-standard calibration seeds",
            ),
        )

    def _replay_action(self, context: ControllerContext) -> ControllerAction:
        has_groups = bool(context.high_influence_group_ids)
        return ControllerAction(
            mode=CampaignMode.REPLAY,
            action_id="replay:high-influence-groups" if has_groups else "replay:waiting",
            priority=92.0 if has_groups else 45.0,
            reason=(
                "revalidate high-influence constraint groups through the public transcript"
                if has_groups
                else "wait until solver influence identifies groups worth replaying"
            ),
            payload={
                "status": "ready" if has_groups else "blocked",
                "group_ids": context.high_influence_group_ids,
                "entrypoint": "sphinx-interrogate replay",
                "requires_raw_transcript": True,
            },
            score_components={
                "solver_influence": 1.0 if has_groups else 0.0,
                "reproducibility_gain": 0.8 if has_groups else 0.2,
                "cost_penalty": 0.3,
            },
            provenance=(
                "CampaignRepository.rebuild",
                "HypothesisStore.named_assumptions",
            ),
        )

    def _reduce_action(self, context: ControllerContext) -> ControllerAction:
        return ControllerAction(
            mode=CampaignMode.REDUCE,
            action_id=f"reduce:{context.reducer_family}",
            priority=65.0,
            reason="minimize a public high-value relation witness while preserving provenance",
            payload={
                "status": "ready",
                "family": context.reducer_family,
                "entrypoint": "sphinx-interrogate reduce",
                "preservation": "implies-core",
            },
            score_components={
                "witness_value": 0.7,
                "provenance_preservation": 1.0,
                "cost_penalty": 0.4,
            },
            provenance=(
                "RelationReducer.reduce",
                "runs/reduced-witnesses-m9/reduced-witnesses-report.json",
            ),
        )

    def _diversify_action(self, context: ControllerContext) -> ControllerAction:
        family = (
            context.uncovered_relation_families[0]
            if context.uncovered_relation_families
            else "repeat-amplify/v1"
        )
        return ControllerAction(
            mode=CampaignMode.DIVERSIFY,
            action_id=f"diversify:{family}",
            priority=58.0,
            reason="fill uncovered relation, grammar, or state regions before local search stalls",
            payload={
                "status": "ready",
                "target_family": family,
                "known_relation_families": context.known_relation_families,
                "entrypoint": "frontier structural/semantic novelty",
            },
            score_components={
                "coverage_gap": 1.0 if context.uncovered_relation_families else 0.0,
                "local_density_penalty": 0.2,
                "cost_penalty": 0.3,
            },
            provenance=(
                "InterrogationKnowledgeBase.frontier",
                "FrontierCandidate.semantic_key",
            ),
        )


def _freeze_public_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_public(value[key]) for key in sorted(value)})


def _freeze_public(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_public_mapping({str(key): item for key, item in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_freeze_public(item) for item in value)
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"controller payload contains unsupported public value {type(value)!r}")


def _public_data(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _public_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_public_data(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"controller payload contains unsupported public value {type(value)!r}")


class AnchorSwitchRunner:
    """Execute, classify, and record one anchor-switch relation instance."""

    def __init__(self, client: VmClient, knowledge_base: InterrogationKnowledgeBase) -> None:
        """Bind a public protocol client and campaign knowledge base."""
        self._client = client
        self._knowledge_base = knowledge_base
        self._template = AnchorSwitchTemplate()

    def run(
        self,
        relation: RelationInstance,
        *,
        samples: int,
        reset: str,
        hard_preconditions_certified: bool,
    ) -> RelationEvidence:
        """Collect interleaved paired samples and compile certified violations."""
        if samples < 1:
            raise ValueError("samples must be positive")
        if len(relation.follow_up_programs) != 1:
            raise ValueError("anchor-switch scaffold expects exactly one follow-up")
        source_results = []
        follow_up_results = []
        batch_id = f"batch:{relation.instance_id}"
        for index in range(samples):
            seed = f"{relation.instance_id}:{index}"
            source_results.append(
                self._client.execute(
                    relation.source_program.render(),
                    session_id=f"{relation.instance_id}:source",
                    logical_batch_id=batch_id,
                    reset=reset,
                    execution_seed_id=seed,
                )
            )
            follow_up_results.append(
                self._client.execute(
                    relation.follow_up_programs[0].render(),
                    session_id=f"{relation.instance_id}:follow-up",
                    logical_batch_id=batch_id,
                    reset=reset,
                    execution_seed_id=seed,
                )
            )
        source_values = [
            bucket_midpoint(result.observation.cycle_bucket, result.observation.bucket_width)
            for result in source_results
        ]
        follow_up_values = [
            bucket_midpoint(result.observation.cycle_bucket, result.observation.bucket_width)
            for result in follow_up_results
        ]
        estimate = paired_location(source_values, follow_up_values)
        request_ids = tuple(
            result.request_id
            for pair in zip(source_results, follow_up_results, strict=True)
            for result in pair
        )
        evidence = self._template.classify(
            relation.instance_id,
            estimate.location,
            confidence=estimate.confidence,
            source_request_ids=request_ids,
        )
        source_record = QueryRecord(
            query_id=relation.source_query_id,
            program_text=relation.source_program.render(),
            results=tuple(source_results),
            created_at_step=self._knowledge_base.step,
        )
        follow_up_record = QueryRecord(
            query_id=relation.follow_up_query_ids[0],
            program_text=relation.follow_up_programs[0].render(),
            results=tuple(follow_up_results),
            created_at_step=self._knowledge_base.step,
        )
        self._knowledge_base.add_query(source_record)
        self._knowledge_base.add_query(follow_up_record)
        facts = self._template.extract_facts(
            relation,
            evidence,
            hard_preconditions_certified=hard_preconditions_certified,
        )
        self._knowledge_base.add_relation(
            RelationRecord(instance=relation, evidence=evidence, derived_facts=facts)
        )
        self._knowledge_base.advance()
        return evidence


class TutorialCampaign:
    """Small exact-mode campaign demonstrating the intended closed loop.

    The complete Codex task replaces this reference loop with persisted campaigns,
    MaxSMT, richer relation families, explicit query budgets, and mutation tests.
    """

    def __init__(self, client: VmClient, cells: int) -> None:
        """Create a tutorial campaign for identity-mapped four-bit cells."""
        self.knowledge_base = InterrogationKnowledgeBase()
        self.domain = SecretDomain(cells)
        self._selector = GrammarGuidedSelector()
        self._runner = AnchorSwitchRunner(client, self.knowledge_base)
        self._template = AnchorSwitchTemplate()
        self._used: list[QueryCandidate] = []

    def step(self) -> RelationEvidence | None:
        """Synthesize and execute one hard-reset exact relation query."""
        scored = self._selector.choose(self.domain, used=self._used)
        if scored is None:
            return None
        candidate = scored.query
        active_pad = (candidate.lane ^ candidate.token ^ candidate.epoch) & 0b11
        candidate = replace(candidate, pad=active_pad)
        instance_id = f"tutorial:{len(self._used)}"
        relation = self._template.instantiate(
            instance_id=instance_id,
            lane=candidate.lane,
            token=candidate.token,
            epoch=candidate.epoch,
            bank_a=candidate.bank_a,
            bank_b=candidate.bank_b,
            pad=candidate.pad,
            repeats=candidate.repeats,
        )
        evidence = self._runner.run(
            relation,
            samples=3,
            reset="hard",
            hard_preconditions_certified=True,
        )
        self._used.extend(replace(candidate, pad=pad) for pad in range(4))
        constraints = (
            BankEqualityConstraint.from_fact(fact)
            for fact in self.knowledge_base.facts_for_relation(instance_id)
        )
        self.domain.apply_all(constraints)
        return evidence

    def run(self, maximum_steps: int = 128) -> tuple[int, ...] | None:
        """Run until uniqueness, no novel query, or the explicit step budget ends."""
        if maximum_steps < 1:
            raise ValueError("maximum_steps must be positive")
        for _ in range(maximum_steps):
            unique = self.domain.unique_secret()
            if unique is not None:
                return unique
            evidence = self.step()
            if evidence is None:
                return None
        return self.domain.unique_secret()
