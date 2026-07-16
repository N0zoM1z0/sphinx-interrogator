"""Tests for typed grammar, SMT hole filling, and CEGIS query synthesis."""

from __future__ import annotations

import random
from pathlib import Path

from sphinx_interrogator.constraints import (
    ApproximationKind,
    FiniteModelAssignment,
    FiniteModelConstraint,
)
from sphinx_interrogator.frontier import ActiveFrontier, FrontierCandidate, NoveltyStatus
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository
from sphinx_interrogator.solver import (
    ConstraintGroup,
    HypothesisStore,
    SecretDomain,
    finite_model_program,
)
from sphinx_interrogator.synthesis import (
    BoundedRelationGrammar,
    CegisSynthesizer,
    CounterexamplePair,
    DiverseCommittee,
    HoleFillResult,
    QueryCandidate,
    RelationSkeleton,
    RepeatAmplifyCandidate,
    SignatureInterval,
    SynthesisContext,
    SynthesisModel,
    SynthesisStatus,
    TypedCandidate,
    concrete_signature,
    entropy_of_partition,
    interval_distance,
    score_candidate,
    symbolic_signature,
)
from sphinx_interrogator.target_model import FaultVariant, MicroState


def _committee(
    secrets: tuple[int, ...] = tuple(range(16)),
    *,
    fault: FaultVariant = FaultVariant.REFERENCE,
) -> DiverseCommittee:
    models = tuple(SynthesisModel(f"model-{value:02d}", (value,), fault) for value in secrets)
    return DiverseCommittee.select(models, limit=len(models), complete=True)


def _context(committee: DiverseCommittee, **changes: object) -> SynthesisContext:
    values: dict[str, object] = {
        "hypothesis_fingerprint": committee.fingerprint(),
        "maximum_bucket_size": max(1, len(committee.models) // 2),
    }
    values.update(changes)
    return SynthesisContext(**values)  # type: ignore[arg-type]


def test_entropy_rewards_balanced_partition() -> None:
    """A balanced exact/proxy partition carries more disagreement information."""
    assert entropy_of_partition((4, 4, 8)) > entropy_of_partition((1, 1, 14))


def test_compatibility_selector_returns_a_typed_candidate() -> None:
    """The M5 compatibility API still returns typed, canonical one-cell holes."""
    from sphinx_interrogator.synthesis import GrammarGuidedSelector

    selector = GrammarGuidedSelector(tokens=(0,), epochs=(0,), pads=(0,))
    selected = selector.choose(SecretDomain(1))
    assert selected is not None
    assert selected.query.lane == 0
    assert len(selected.outcome_partition) == 3
    assert selected.query.lower("compatibility").architectural_precheck()


def test_bounded_skeletons_lower_to_certified_resource_safe_ast_pairs() -> None:
    """Skeleton assignments are typed ASTs and preserve both certified relations."""
    grammar = BoundedRelationGrammar(
        lanes=(0,), tokens=(0,), epochs=(0,), pads=(0, 1), repeat_counts=(2, 4)
    )
    assert {skeleton.kind.value for skeleton in grammar.skeletons()} == {
        "anchor-switch",
        "repeat-amplify",
    }
    candidates = grammar.all_candidates()
    assert candidates
    assert any(isinstance(candidate, QueryCandidate) for candidate in candidates)
    assert any(isinstance(candidate, RepeatAmplifyCandidate) for candidate in candidates)
    for index, candidate in enumerate(candidates):
        relation = candidate.lower(f"typed-{index}")
        assert relation.architectural_precheck()
        assert relation.fault_free_precheck()
        assert all(not program.effects().writes_digest for program in relation.programs)


def test_tiny_exact_domain_matches_the_bruteforce_known_optimum() -> None:
    """SMT/CEGIS returns the same lexicographic optimum as exhaustive scoring."""
    committee = _committee((0, 4, 8, 12))
    context = _context(committee, maximum_bucket_size=2)
    grammar = BoundedRelationGrammar(
        lanes=(0,),
        tokens=(0,),
        epochs=(0,),
        pads=(0,),
        include_repeat_amplify=False,
    )
    result = CegisSynthesizer(grammar).synthesize(committee, context)
    assert result.status is SynthesisStatus.SAT
    assert result.verification_complete
    assert result.score is not None
    brute_force = min(
        (score_candidate(candidate, committee, context) for candidate in grammar.all_candidates()),
        key=lambda score: score.objective_key(),
    )
    assert result.score.objective_key() == brute_force.objective_key()
    assert result.score.candidate == QueryCandidate(0, 0, 0, 1, 2, 0)
    assert result.score.partition_score_kind == "exact-information"


def test_cegis_adds_a_counterexample_from_an_oversized_bucket() -> None:
    """An impossible strict balance target causes real pair refinement before stopping."""
    committee = _committee()
    grammar = BoundedRelationGrammar(
        lanes=(0,),
        tokens=(0,),
        epochs=(0,),
        pads=(0,),
        include_repeat_amplify=False,
    )
    result = CegisSynthesizer(grammar).synthesize(
        committee, _context(committee, maximum_bucket_size=7)
    )
    assert result.status is SynthesisStatus.SAT
    assert result.iterations > 1
    assert result.counterexamples
    assert not result.verification_complete
    assert all(pair.source_bucket_size >= 2 for pair in result.counterexamples)


def test_noise_margin_changes_the_selected_skeleton() -> None:
    """Positive interval separation selects drained amplification over a cheap pair."""
    committee = _committee()
    grammar = BoundedRelationGrammar(
        lanes=(0,), tokens=(0,), epochs=(0,), pads=(0,), repeat_counts=(2, 4, 8)
    )
    exact = CegisSynthesizer(grammar).synthesize(committee, _context(committee))
    noisy = CegisSynthesizer(grammar).synthesize(
        committee,
        _context(
            committee,
            noise_bound=1,
            minimum_pair_margin=1,
            maximum_bucket_size=8,
        ),
    )
    assert exact.score is not None and isinstance(exact.score.candidate, QueryCandidate)
    assert noisy.score is not None
    assert isinstance(noisy.score.candidate, RepeatAmplifyCandidate)
    assert noisy.score.candidate.repeats == 8
    assert noisy.score.minimum_margin >= 1


def test_fault_free_models_have_no_secret_discriminator() -> None:
    """The blind off-fault family makes every grammar signature secret-independent."""
    committee = _committee(fault=FaultVariant.OFF)
    result = CegisSynthesizer(
        BoundedRelationGrammar(lanes=(0,), tokens=(0, 1), epochs=(0, 1), pads=range(4))
    ).synthesize(committee, _context(committee))
    assert result.status is SynthesisStatus.UNSAT
    assert result.score is None
    assert not result.verification_complete


class _UnknownHoleFiller:
    def fill(
        self,
        skeleton: RelationSkeleton,
        candidates: tuple[TypedCandidate, ...],
        requirements: tuple[CounterexamplePair, ...],
        models: dict[str, SynthesisModel],
        context: SynthesisContext,
    ) -> HoleFillResult:
        del skeleton, candidates, requirements, models, context
        return HoleFillResult(SynthesisStatus.UNKNOWN, None, "injected solver timeout")


def test_solver_unknown_is_not_reinterpreted_as_no_discriminator() -> None:
    """A timed-out hole solver stays unknown rather than becoming unsat or success."""
    committee = _committee((0, 1))
    synthesizer = CegisSynthesizer(
        BoundedRelationGrammar(
            lanes=(0,), tokens=(0,), epochs=(0,), pads=(0,), include_repeat_amplify=False
        ),
        hole_filler=_UnknownHoleFiller(),
    )
    result = synthesizer.synthesize(committee, _context(committee, maximum_bucket_size=1))
    assert result.status is SynthesisStatus.UNKNOWN
    assert result.score is None
    assert "timeout" in result.reason


def test_symbolic_signatures_match_concrete_public_evaluator_exhaustively() -> None:
    """Both grammar productions agree for every nibble and public fault-family member."""
    candidates: tuple[TypedCandidate, ...] = (
        QueryCandidate(0, 0, 0, 0, 1, 0),
        QueryCandidate(0, 3, 1, 1, 3, 2),
        RepeatAmplifyCandidate(0, 0, 0, 0, 0, 8),
        RepeatAmplifyCandidate(0, 7, 1, 3, 2, 4),
    )
    for candidate in candidates:
        for secret in range(16):
            for fault in FaultVariant:
                model = SynthesisModel(f"{secret}-{fault.value}", (secret,), fault)
                assert symbolic_signature(
                    candidate, model, noise_bound=1, bucket_width=2
                ) == concrete_signature(candidate, model, noise_bound=1, bucket_width=2)


def test_interval_distance_is_closed_and_conservative() -> None:
    """Touching/overlapping nuisance intervals have zero claimed separation."""
    assert interval_distance(SignatureInterval(0, -1, 1), SignatureInterval(2, 1, 3)) == 0
    assert interval_distance(SignatureInterval(0, -1, 1), SignatureInterval(4, 3, 5)) == 2


def test_cache_key_and_frontier_adapter_persist_all_score_components(tmp_path: Path) -> None:
    """A cached synthesis result enters the M4 frontier with an auditable score."""
    committee = _committee((0, 4, 8, 12))
    context = _context(committee, maximum_bucket_size=2)
    synthesizer = CegisSynthesizer(
        BoundedRelationGrammar(
            lanes=(0,),
            tokens=(0,),
            epochs=(0,),
            pads=(0,),
            include_repeat_amplify=False,
        )
    )
    first = synthesizer.synthesize(committee, context)
    cached = synthesizer.synthesize(committee, context)
    assert not first.cache_hit
    assert cached.cache_hit
    assert cached.score == first.score

    repository = CampaignRepository.create(
        tmp_path / "run",
        CampaignManifest(
            campaign_id="m6-frontier",
            challenge_id="public-challenge",
            challenge_commitment="0" * 64,
            profile_name="tutorial",
            semantic_version="0.1.0",
            public_profile_sha256="1" * 64,
            seed=31,
            minimum_certificate_strength="exhaustive-enumeration",
            logical_query_budget=80,
            physical_execution_budget=240,
            hard_reset_budget=240,
        ),
    )
    candidate = cached.frontier_candidate(candidate_id="m6-synthesized", expires_after=4)
    assert isinstance(candidate, FrontierCandidate)
    decision = ActiveFrontier(repository).consider(candidate, logical_time=1)
    assert decision.status is NoveltyStatus.NOVEL
    selected = ActiveFrontier(repository).select(logical_time=1)
    assert selected is not None
    synthesis = selected.data["synthesis"]
    assert isinstance(synthesis, dict)
    score = synthesis["score"]
    assert isinstance(score, dict)
    assert score["partition_score_kind"] == "exact-information"
    assert score["worst_bucket_size"] == 2
    repository.close()


def test_synthesized_holes_materially_beat_seeded_random_holes_without_truth() -> None:
    """Committee-only selection halves the mean worst bucket on calibration subsets."""
    grammar = BoundedRelationGrammar(
        lanes=(0,),
        tokens=(0, 1, 2, 3),
        epochs=(0, 1),
        pads=(0, 1, 2, 3),
        include_repeat_amplify=False,
    )
    candidates = grammar.all_candidates()
    synthesized_worst = []
    random_worst = []
    for seed in range(20):
        generator = random.Random(seed)
        surviving = tuple(sorted(generator.sample(range(16), 8)))
        committee = _committee(surviving)
        context = _context(committee, maximum_bucket_size=4)
        result = CegisSynthesizer(grammar).synthesize(committee, context)
        assert result.score is not None
        synthesized_worst.append(result.score.worst_bucket_size)
        random_worst.append(
            score_candidate(generator.choice(candidates), committee, context).worst_bucket_size
        )
    assert sum(synthesized_worst) <= sum(random_worst) * 0.6
    assert (
        sum(left < right for left, right in zip(synthesized_worst, random_worst, strict=True)) >= 15
    )


def test_diverse_committee_accounts_for_fault_and_state_without_private_access() -> None:
    """Public solver hypotheses, including latent fields, drive deterministic diversity."""
    models = (
        SynthesisModel("a", (0,), FaultVariant.REFERENCE, MicroState()),
        SynthesisModel("b", (0,), FaultVariant.OFF, MicroState(phase=3)),
        SynthesisModel("c", (15,), FaultVariant.REFERENCE, MicroState()),
        SynthesisModel("d", (15,), FaultVariant.SIGNED, MicroState(phase=2)),
    )
    committee = DiverseCommittee.select(models, limit=3, complete=True)
    assert committee.models[0].model_id == "a"
    assert {model.model_id for model in committee.models} == {"a", "b", "d"}
    assert not committee.complete


def test_committee_is_generated_from_the_current_exact_hypothesis_store() -> None:
    """The M4 solver's correlated secret/fault models feed M6 without private state."""
    assignments = tuple(FiniteModelAssignment((secret,), "reference") for secret in range(8))
    constraint = FiniteModelConstraint(
        constraint_version="1.0",
        constraint_id="constraint:333333333333333333333333",
        lanes=(0,),
        allowed_models=assignments,
        approximation=ApproximationKind.EXACT,
        relation_instance_id="relation-current",
        certificate_id="certificate-current",
        decision_kind="exact_equal",
        source_request_ids=("request-a", "request-b"),
        assumptions=("hard reset",),
    )
    store = HypothesisStore()
    store.add(ConstraintGroup("current", finite_model_program(constraint, secret_cells=1)))
    committee = DiverseCommittee.from_store(store, secret_cells=1, limit=4, pool_limit=8)
    assert len(committee.models) == 4
    assert not committee.complete
    result = CegisSynthesizer(
        BoundedRelationGrammar(
            lanes=(0,),
            tokens=(0,),
            epochs=(0,),
            pads=(0,),
            include_repeat_amplify=False,
        )
    ).synthesize(committee, _context(committee, maximum_bucket_size=2))
    assert result.score is not None
    assert result.score.partition_score_kind == "committee-proxy"
