#!/usr/bin/env python3
"""Generate minimized release witness artifacts for every core relation family."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from sphinx_interrogator.ast import Program
from sphinx_interrogator.normalization import decide_pair
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.reducer import (
    MeasuredReplay,
    ReductionConfig,
    ReductionMode,
    RelationReducer,
    ReplayComparison,
    SignatureKind,
    default_model_committee,
    report_digest,
)
from sphinx_interrogator.relations import (
    AnchorSwitchTemplate,
    Cell,
    ContextLiftTemplate,
    EpochSwitchTemplate,
    HardReplayTemplate,
    IndependentSwapTemplate,
    PhaseShiftTemplate,
    RegisterRenameTemplate,
    RelationInstance,
    RepeatAmplifyTemplate,
    SoftHistoryContrastTemplate,
    TokenSwitchTemplate,
)
from sphinx_trusted_runtime import (
    ChallengeBundle,
    create_challenge,
    create_private_root,
    launch_endpoints,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "benchmarks/profiles/reducer.toml"


@dataclass(frozen=True, slots=True)
class WitnessSeed:
    """One generated starting relation plus known primitive relations."""

    family: str
    relation: RelationInstance
    known_relations: dict[str, RelationInstance]


@dataclass(frozen=True, slots=True)
class PublicReplayContext:
    """Public metadata for the replay campaign."""

    challenge_id: str
    commitment: str
    profile_sha256: str
    public_directory: str

    def provenance(self) -> tuple[str, ...]:
        """Return stable public replay provenance markers."""
        return (
            "measured-profile:reducer@0.1.0",
            f"challenge:{self.challenge_id}",
            f"commitment:{self.commitment}",
        )

    def to_data(self) -> dict[str, object]:
        """Return report-safe context data."""
        return {
            "profile_name": "reducer",
            "challenge_id": self.challenge_id,
            "commitment": self.commitment,
            "profile_sha256": self.profile_sha256,
            "public_directory": self.public_directory,
        }


class VmReplayOracle:
    """Measured replay oracle backed by a real public SphinxVM process."""

    def __init__(self, client: VmClient, context: PublicReplayContext) -> None:
        self.client = client
        self.context = context
        self._counter = 0
        self._cache: dict[str, MeasuredReplay] = {}

    def compare(
        self,
        original: RelationInstance,
        candidate: RelationInstance,
    ) -> ReplayComparison:
        """Preserve measured decision and confidence across a candidate replay."""
        original_replay = self.replay(original)
        candidate_replay = self.replay(candidate)
        accepted = (
            candidate_replay.decision == original_replay.decision
            and candidate_replay.confidence >= original_replay.confidence
        )
        if accepted:
            reason = "candidate preserved measured decision and confidence"
        else:
            reason = (
                f"decision/confidence changed from "
                f"{original_replay.decision}@{original_replay.confidence:.3f} to "
                f"{candidate_replay.decision}@{candidate_replay.confidence:.3f}"
            )
        return ReplayComparison(
            accepted=accepted,
            original=original_replay,
            candidate=candidate_replay,
            reason=reason,
        )

    def replay(self, relation: RelationInstance) -> MeasuredReplay:
        """Execute source/follow-up programs and classify public pair decisions."""
        cached = self._cache.get(relation.instance_hash)
        if cached is not None:
            return cached
        self._counter += 1
        batch_id = f"m9-replay-{self._counter:05d}"
        results = []
        resets = _reset_sequence(relation)
        for position, (program, reset) in enumerate(zip(relation.programs, resets, strict=True)):
            request_id = f"{batch_id}-arm-{position:02d}"
            results.append(
                self.client.execute(
                    program.render(),
                    session_id="m9-replay-session",
                    logical_batch_id=batch_id,
                    reset=reset,
                    execution_seed_id=request_id,
                    request_id=request_id,
                )
            )
        source = results[0]
        decisions = tuple(
            decide_pair(
                source,
                follow_up,
                expected_source_static=relation.source_program.static_cycles(),
                expected_follow_up_static=program.static_cycles(),
                noise_bound=0,
                assumptions=("measured tutorial replay",),
            )
            for follow_up, program in zip(
                results[1:],
                relation.follow_up_programs,
                strict=True,
            )
        )
        confidence = 1.0 if all(decision.hard_eligible for decision in decisions) else 0.0
        replay = MeasuredReplay(
            relation_hash=relation.instance_hash,
            decision="|".join(decision.kind.value for decision in decisions),
            confidence=confidence,
            request_ids=tuple(result.request_id for result in results),
            reset_policy=relation.reset_policy,
            resets=resets,
            provenance=self.context.provenance(),
        )
        self._cache[relation.instance_hash] = replay
        return replay

    def measured_replay_count(self) -> int:
        """Return the number of relation instances actually replayed."""
        return len(self._cache)


def parse_args() -> argparse.Namespace:
    """Parse noninteractive reducer options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "runs/reduced-witnesses-m9",
        help="directory for JSON/Markdown witness artifacts",
    )
    parser.add_argument(
        "--socket-root",
        type=Path,
        help="short runtime directory for replay VM Unix sockets",
    )
    parser.add_argument(
        "--require-all-minimized",
        action="store_true",
        help="exit nonzero unless every generated family has a smaller witness",
    )
    return parser.parse_args()


def main() -> int:
    """Generate release witness artifacts and return a process status."""
    args = parse_args()
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        print("SPHINX_VM_BINARY is required", file=sys.stderr)
        return 2
    binary = Path(configured).resolve()
    if not binary.is_file():
        print(f"SphinxVM binary does not exist: {binary}", file=sys.stderr)
        return 2
    output: Path = args.output
    witnesses_dir = output / "witnesses"
    witnesses_dir.mkdir(parents=True, exist_ok=True)
    trusted_root = ROOT / "runs/.trusted-reducer-m9"
    trusted_root.mkdir(parents=True, exist_ok=True)
    socket_root = (args.socket_root if args.socket_root is not None else trusted_root).resolve()
    socket_root.mkdir(parents=True, exist_ok=True)
    private_root = trusted_root / "private-root.bin"
    if not private_root.exists():
        create_private_root(binary, private_root)
    bundle = _ensure_challenge(
        binary,
        output=trusted_root / "challenge-reducer-profile",
        private_root_file=private_root,
    )
    public = _load_public_challenge(bundle.public_directory)
    replay_context = PublicReplayContext(
        challenge_id=_string(public, "challenge_id"),
        commitment=_string(public, "commitment"),
        profile_sha256=_string(public, "profile_sha256"),
        public_directory=_portable_path(bundle.public_directory, ROOT),
    )

    config = ReductionConfig(
        mode=ReductionMode.IMPLIES_CORE,
        signature_kind=SignatureKind.SIGN,
        max_predicate_evaluations=1_024,
        max_generated_candidates=4_096,
    )
    witness_reports: list[dict[str, object]] = []
    with (
        launch_endpoints(
            binary,
            bundle,
            socket_directory=socket_root / "sockets",
            with_judge=False,
        ) as endpoints,
        VmClient.connect_unix(endpoints.vm_socket, timeout_seconds=5.0) as client,
    ):
        hello = client.hello()
        if hello.profile_name != "reducer":
            raise RuntimeError(f"expected reducer replay profile, got {hello.profile_name}")
        replay_oracle = VmReplayOracle(client, replay_context)
        for seed in _witness_seeds():
            reducer = RelationReducer(
                models=default_model_committee(seed.relation.involved_lanes),
                known_relations=seed.known_relations,
                config=config,
                replay_oracle=replay_oracle,
            )
            result = reducer.reduce(seed.relation)
            data = result.to_data()
            data["family"] = seed.family
            data["artifact_sha256"] = report_digest(data)
            witness_path = witnesses_dir / f"{_slug(seed.family)}.json"
            _write_json(witness_path, data)
            data["path"] = str(witness_path.relative_to(output))
            witness_reports.append(data)

    report = {
        "report_version": "1.0",
        "kind": "reduced-witnesses",
        "schema_version": "1.0",
        "generated_by": "scripts/reduce_witnesses.py",
        "preservation": {
            "mode": config.mode.value,
            "signature_kind": config.signature_kind.value,
            "model_scope": "finite-public-family-committee",
            "uses_true_secret": False,
            "result_label": (
                "bounded public-model implication plus measured public VM replay; "
                "not a hidden-secret comparison"
            ),
            "measured_replay": replay_context.to_data(),
        },
        "families": witness_reports,
        "summary": {
            "family_count": len(witness_reports),
            "minimized_count": sum(item["status"] == "minimized" for item in witness_reports),
            "partial_count": sum(item["status"] == "partial" for item in witness_reports),
            "blocked_count": sum(item["status"] == "blocked" for item in witness_reports),
            "unchanged_count": sum(item["status"] == "unchanged" for item in witness_reports),
            "all_minimized": all(item["status"] == "minimized" for item in witness_reports),
            "all_replay_paths_valid": all(
                _family_replay_path_valid(item) for item in witness_reports
            ),
            "reset_policy_honored": all(
                _family_reset_policy_honored(item) for item in witness_reports
            ),
        },
    }
    report["artifact_sha256"] = report_digest(report)
    schema = json.loads((ROOT / "spec/reduced-witnesses-report.schema.json").read_text("utf-8"))
    jsonschema.Draft202012Validator(schema).validate(report)
    _write_json(output / "reduced-witnesses-report.json", report)
    _write_markdown(output / "reduced-witnesses-report.md", report)

    all_minimized = bool(report["summary"]["all_minimized"])  # type: ignore[index]
    if args.require_all_minimized and not all_minimized:
        return 1
    return 0


def _reset_sequence(relation: RelationInstance) -> tuple[str, ...]:
    """Return the reset sequence used to replay one relation instance."""
    if relation.reset_policy == "hard":
        return tuple("hard" for _ in relation.programs)
    return ("hard", *(relation.reset_policy for _ in relation.follow_up_programs))


def _family_replay_path_valid(item: Mapping[str, object]) -> bool:
    """Check that serialized accepted steps form one continuous parent path."""
    path = item.get("replay_path")
    if not isinstance(path, dict):
        return False
    return (
        path.get("continuous") is True
        and path.get("starts_at_original") is True
        and path.get("ends_at_reduced") is True
    )


def _family_reset_policy_honored(item: Mapping[str, object]) -> bool:
    """Check every measured replay entry carries the reset sequence it claims."""
    entries = item.get("measured_replay")
    if not isinstance(entries, list) or not entries:
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            return False
        for side in ("original", "candidate"):
            replay = entry.get(side)
            if replay is None and side == "candidate":
                continue
            if not isinstance(replay, dict):
                return False
            reset_policy = replay.get("reset_policy")
            resets = replay.get("resets")
            request_ids = replay.get("request_ids")
            if reset_policy not in {"hard", "soft", "none"}:
                return False
            if not isinstance(resets, list) or not isinstance(request_ids, list):
                return False
            if len(resets) != len(request_ids):
                return False
            if reset_policy == "hard":
                if any(reset != "hard" for reset in resets):
                    return False
            else:
                if not resets or resets[0] != "hard":
                    return False
                if any(reset != reset_policy for reset in resets[1:]):
                    return False
    return True


def _witness_seeds() -> tuple[WitnessSeed, ...]:
    anchor = AnchorSwitchTemplate().instantiate(
        instance_id="m9-anchor",
        lane=0,
        token=0,
        epoch=0,
        bank_a=3,
        bank_b=2,
        pad=8,
        repeats=4,
    )
    token = TokenSwitchTemplate().instantiate(
        instance_id="m9-token",
        lane=0,
        token_a=0,
        token_b=1,
        epoch=0,
        anchor=2,
        pad=8,
    )
    epoch = EpochSwitchTemplate().instantiate(
        instance_id="m9-epoch",
        lane=0,
        token=0,
        epoch_a=0,
        epoch_b=1,
        anchor=2,
        pad_a=8,
        pad_b=9,
    )
    phase = PhaseShiftTemplate().instantiate(
        instance_id="m9-phase",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad_a=8,
        pad_b=9,
    )
    repeat = RepeatAmplifyTemplate().instantiate(
        instance_id="m9-repeat",
        lane=0,
        token=0,
        epoch=0,
        anchor=2,
        pad=8,
        repeats=6,
    )
    swap = IndependentSwapTemplate().instantiate(
        instance_id="m9-swap",
        first=Cell(0, 0, 0, 2, 8),
        second=Cell(1, 1, 1, 3, 10),
    )
    context = ContextLiftTemplate().instantiate(
        instance_id="m9-context",
        base=anchor,
        prefix_pad=8,
        suffix_fence=True,
    )
    register = RegisterRenameTemplate().instantiate(
        instance_id="m9-register",
        source=Program.parse(
            "MOVI r0, 7\nMOV r1, r0\nADD r2, r0, r1\nMIXOUT r2\nHALT\n",
            lanes=2,
        ),
        permutation=(1, 2, 0, 3, 4, 5, 6, 7),
    )
    hard_replay = HardReplayTemplate().instantiate(
        instance_id="m9-hard-replay",
        program=anchor.source_program,
        repetitions=5,
        deterministic_observation=True,
    )
    measurement = AnchorSwitchTemplate().instantiate(
        instance_id="m9-soft-measurement",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    soft_history = SoftHistoryContrastTemplate().instantiate(
        instance_id="m9-soft-history",
        history_a=Program.parse("PAD 4\nFENCE\nHALT\n", lanes=2),
        history_b=Program.parse("PAD 8\nFENCE\nHALT\n", lanes=2),
        measurement=measurement,
        state_model_id="m9-state-model",
        source_state="q0",
        follow_up_state="q1",
    )
    return (
        WitnessSeed("anchor-switch/v1", anchor, {}),
        WitnessSeed("token-switch/v1", token, {}),
        WitnessSeed("epoch-switch/v1", epoch, {}),
        WitnessSeed("phase-shift/v1", phase, {}),
        WitnessSeed("repeat-amplify/v1", repeat, {}),
        WitnessSeed("independent-swap/v1", swap, {}),
        WitnessSeed("context-lift/v1", context, {anchor.instance_hash: anchor}),
        WitnessSeed("register-rename/v1", register, {}),
        WitnessSeed("hard-replay/v1", hard_replay, {}),
        WitnessSeed(
            "soft-history-contrast/v1",
            soft_history,
            {measurement.instance_hash: measurement},
        ),
    )


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _write_markdown(path: Path, report: dict[str, object]) -> None:
    summary = report["summary"]
    if not isinstance(summary, dict):
        raise TypeError("report summary must be a dictionary")
    lines = [
        "# Reduced relation witnesses",
        "",
        f"- Families: {summary['family_count']}",
        f"- Minimized: {summary['minimized_count']}",
        f"- Partial: {summary['partial_count']}",
        f"- Blocked: {summary['blocked_count']}",
        f"- All minimized: {summary['all_minimized']}",
        f"- Predicate: {report['preservation']}",
        "",
        "| family | status | original static | reduced static | steps | artifact |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    families = report["families"]
    if not isinstance(families, list):
        raise TypeError("report families must be a list")
    for item in families:
        if not isinstance(item, dict):
            raise TypeError("witness entry must be a dictionary")
        original = item["original"]
        reduced = item["reduced"]
        if not isinstance(original, dict) or not isinstance(reduced, dict):
            raise TypeError("witness costs must be dictionaries")
        original_cost = original["cost"]
        reduced_cost = reduced["cost"]
        if not isinstance(original_cost, dict) or not isinstance(reduced_cost, dict):
            raise TypeError("witness cost entries must be dictionaries")
        steps = item["steps"]
        if not isinstance(steps, list):
            raise TypeError("witness steps must be a list")
        row_template = (
            "| {family} | {status} | {original_static} | {reduced_static} | {steps} | `{digest}` |"
        )
        lines.append(
            row_template.format(
                family=item["family"],
                status=item["status"],
                original_static=original_cost["static_cycles"],
                reduced_static=reduced_cost["static_cycles"],
                steps=len(steps),
                digest=str(item["artifact_sha256"])[:16],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    return value.replace("/", "-").replace("_", "-")


def _ensure_challenge(
    binary: Path,
    *,
    output: Path,
    private_root_file: Path,
) -> ChallengeBundle:
    if (output / "public/challenge.json").is_file():
        return ChallengeBundle(output / "public", output / "private", private_root_file)
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"challenge directory is partial or incompatible: {output}")
    if output.exists():
        output.rmdir()
    return create_challenge(
        binary,
        profile=PROFILE,
        root=output,
        private_root_file=private_root_file,
        challenge_id="challenge-0001",
        campaign_label="campaign-reducer-m9",
        fault="reference",
    )


def _load_public_challenge(public_directory: Path) -> Mapping[str, object]:
    decoded = json.loads((public_directory / "challenge.json").read_text("utf-8"))
    if not isinstance(decoded, dict):
        raise TypeError("public challenge must be an object")
    return decoded


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


if __name__ == "__main__":
    raise SystemExit(main())
