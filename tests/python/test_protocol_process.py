"""Cross-language tests for the release-shaped SphinxVM JSONL process."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sphinx_interrogator.ast import Program
from sphinx_interrogator.harness import DurableExecutionHarness, ExecutionSpec
from sphinx_interrogator.persistence import CampaignManifest, CampaignRepository
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.relations import (
    AnchorSwitchTemplate,
    Cell,
    ContextLiftTemplate,
    EpochSwitchTemplate,
    HardReplayTemplate,
    IndependentSwapTemplate,
    PhaseShiftTemplate,
    RegisterRenameTemplate,
    RepeatAmplifyTemplate,
    TokenSwitchTemplate,
)
from sphinx_interrogator.synthesis import (
    BoundedRelationGrammar,
    CegisSynthesizer,
    DiverseCommittee,
    QueryCandidate,
    SynthesisContext,
    SynthesisModel,
    SynthesisStatus,
)
from sphinx_interrogator.tutorial import recover_tutorial

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "benchmarks/profiles/tutorial.toml"
SCHEMA = json.loads((ROOT / "spec/protocol.schema.json").read_text(encoding="utf-8"))
CHALLENGE_SCHEMA = json.loads((ROOT / "spec/challenge.schema.json").read_text(encoding="utf-8"))
JUDGE_SCHEMA = json.loads((ROOT / "spec/judge.schema.json").read_text(encoding="utf-8"))
RECOVERY_REPORT_SCHEMA = json.loads(
    (ROOT / "spec/recovery-report.schema.json").read_text(encoding="utf-8")
)


def vm_binary() -> Path:
    """Return the separately built VM binary or skip direct pytest invocations."""
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        pytest.skip("SPHINX_VM_BINARY is set by `just test` after building the Rust target")
    binary = Path(configured).resolve()
    if not binary.is_file():
        pytest.fail(f"configured SphinxVM binary does not exist: {binary}")
    return binary


@pytest.fixture
def challenge(tmp_path: Path) -> Path:
    """Create one isolated deterministic tutorial challenge through the real CLI."""
    output = tmp_path / "challenge"
    completed = subprocess.run(
        [
            str(vm_binary()),
            "challenge",
            "create",
            "--profile",
            str(PROFILE),
            "--output",
            str(output),
            "--challenge-id",
            "pytest-challenge",
            "--seed",
            "20260715",
            "--fault",
            "reference",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert completed.returncode == 0, completed.stderr
    generated = json.loads(completed.stdout)
    public = json.loads((output / "public/challenge.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(CHALLENGE_SCHEMA).validate(generated)
    jsonschema.Draft202012Validator(CHALLENGE_SCHEMA).validate(public)
    assert generated == public
    with (output / "public/profile.toml").open("rb") as handle:
        public_profile = tomllib.load(handle)
    assert not {
        "fault_variant",
        "generation_root_seed",
        "noise_key",
        "commitment_nonce",
        "secret",
    }.intersection(public_profile)
    if os.name == "posix":
        assert (output / "private").stat().st_mode & 0o777 == 0o700
        assert (output / "private/secret.bin").stat().st_mode & 0o777 == 0o600
    return output


@pytest.mark.integration
def test_client_round_trip_tracks_public_budgets_and_versions(challenge: Path) -> None:
    """Python must negotiate and execute only through the real process boundary."""
    with VmClient.start(vm_binary(), challenge=challenge, timeout_seconds=2.0) as client:
        hello = client.hello()
        assert hello.profile_name == "tutorial"
        assert hello.capabilities == ("close", "execute", "hard_reset", "soft_reset")
        assert hello.max_request_line_bytes == 131_072
        first = client.execute(
            "HALT\n",
            session_id="integration-session",
            logical_batch_id="integration-batch",
            reset="hard",
        )
        second = client.execute(
            "HALT\n",
            session_id="integration-session",
            logical_batch_id="integration-batch",
            reset="soft",
        )

    assert first.status == "halted"
    assert first.logical_queries_used == 1
    assert first.hard_resets_used == 1
    assert second.logical_queries_used == 1
    assert second.hard_resets_used == 1
    assert second.physical_executions_used == 2
    assert second.server_version == "0.1.0"
    assert second.profile_version == "0.1.0"


@pytest.mark.integration
def test_server_recovers_after_malformed_and_oversized_lines(challenge: Path) -> None:
    """Transport errors are bounded, schema-valid, and do not kill the server loop."""
    requests = [
        "{not-json}",
        "x" * 131_073,
        json.dumps(
            {
                "protocol_version": "1.0",
                "request_id": "hello-after-errors",
                "kind": "hello",
                "client": {"name": "integration", "version": "0"},
            }
        ),
        json.dumps(
            {
                "protocol_version": "1.0",
                "request_id": "close-after-errors",
                "kind": "close",
            }
        ),
    ]
    completed = subprocess.run(
        [str(vm_binary()), "serve", "--challenge", str(challenge)],
        input="\n".join(requests) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    responses: list[Any] = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [response["kind"] for response in responses] == [
        "error",
        "error",
        "hello_result",
        "close_result",
    ]
    assert responses[0]["error"]["code"] == "invalid_json"
    assert responses[1]["error"]["code"] == "request_too_large"
    for response in responses:
        jsonschema.Draft202012Validator(SCHEMA).validate(response)


@pytest.mark.integration
def test_python_canonical_program_and_sparse_memory_execute_in_rust(challenge: Path) -> None:
    """The independent Python representation is accepted by the authoritative parser."""
    source = (ROOT / "tests/fixtures/programs/full-v1.source.spx").read_text(encoding="utf-8")
    canonical = Program.parse(source, lanes=4).render()
    with VmClient.start(vm_binary(), challenge=challenge, timeout_seconds=2.0) as client:
        client.hello()
        golden = client.execute(
            canonical,
            session_id="golden-session",
            logical_batch_id="golden-batch",
        )
        memory = client.execute(
            "LOAD r0, [r1]\nMIXOUT r0\nHALT\n",
            session_id="memory-session",
            logical_batch_id="memory-batch",
            registers=(0, 7),
            memory={7: 0x1234},
        )

    assert golden.status == "halted"
    assert golden.retired_instructions > len(Program.parse(source, lanes=4).instructions)
    assert memory.status == "halted"
    assert memory.static_cycles == 5
    assert memory.public_digest != "0000000000000000"


@pytest.mark.integration
def test_fault_assignment_changes_only_aggregate_observation(tmp_path: Path) -> None:
    """Off/reference challenges share architecture while one guarded bank gets one cycle."""
    challenges: dict[str, Path] = {}
    for variant in ("off", "reference"):
        output = tmp_path / variant
        completed = subprocess.run(
            [
                str(vm_binary()),
                "challenge",
                "create",
                "--profile",
                str(PROFILE),
                "--output",
                str(output),
                "--challenge-id",
                f"process-{variant}",
                "--seed",
                "314159",
                "--fault",
                variant,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        assert completed.returncode == 0, completed.stderr
        challenges[variant] = output

    outcomes: dict[str, list[tuple[int, str]]] = {}
    for variant, challenge_path in challenges.items():
        variant_outcomes: list[tuple[int, str]] = []
        with VmClient.start(vm_binary(), challenge=challenge_path, timeout_seconds=2.0) as client:
            client.hello()
            for bank in range(4):
                result = client.execute(
                    f"PROBE 0, 0, 0\nANCHOR {bank}, 0\nHALT\n",
                    session_id="fault-confinement",
                    logical_batch_id=f"anchor-{bank}",
                    reset="hard",
                )
                variant_outcomes.append(
                    (result.observation.cycle_bucket - result.static_cycles, result.public_digest)
                )
        outcomes[variant] = variant_outcomes

    assert [delta for delta, _ in outcomes["off"]] == [0, 0, 0, 0]
    assert sorted(delta for delta, _ in outcomes["reference"]) == [0, 0, 0, 1]
    assert [digest for _, digest in outcomes["reference"]] == [
        digest for _, digest in outcomes["off"]
    ]


@pytest.mark.integration
def test_judge_records_only_one_schema_valid_submission(challenge: Path) -> None:
    """A campaign token cannot turn the final Boolean judge into a guess oracle."""
    public = json.loads((challenge / "public/challenge.json").read_text(encoding="utf-8"))
    command = [
        str(vm_binary()),
        "judge",
        "--challenge",
        str(challenge),
        "--campaign-token",
        public["campaign_token"],
        "--guess",
        "0000",
    ]
    first = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    second = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_response = json.loads(first.stdout)
    second_response = json.loads(second.stdout)
    jsonschema.Draft202012Validator(JUDGE_SCHEMA).validate(first_response)
    jsonschema.Draft202012Validator(JUDGE_SCHEMA).validate(second_response)
    assert first_response["submission_recorded"] is True
    assert second_response["submission_recorded"] is False
    assert second_response["accepted"] is False


@pytest.mark.integration
def test_seeded_standard_transcript_replays_across_fresh_processes(tmp_path: Path) -> None:
    """A fixed challenge and public schedule reproduce seeded jitter exactly."""
    output = tmp_path / "standard"
    completed = subprocess.run(
        [
            str(vm_binary()),
            "challenge",
            "create",
            "--profile",
            str(ROOT / "benchmarks/profiles/standard.toml"),
            "--output",
            str(output),
            "--challenge-id",
            "standard-replay",
            "--seed",
            "271828",
            "--fault",
            "reference",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert completed.returncode == 0, completed.stderr

    def transcript() -> list[tuple[int, int, str]]:
        observations: list[tuple[int, int, str]] = []
        with VmClient.start(vm_binary(), challenge=output, timeout_seconds=2.0) as client:
            client.hello()
            for repetition in range(3):
                result = client.execute(
                    "PROBE 0, 0, 0\nANCHOR 0, 0\nHALT\n",
                    session_id="deterministic-transcript",
                    logical_batch_id="deterministic-transcript",
                    reset="hard",
                    execution_seed_id=f"repetition-{repetition}",
                )
                observations.append(
                    (
                        result.observation.cycle_bucket,
                        result.static_cycles,
                        result.public_digest,
                    )
                )
        return observations

    assert transcript() == transcript()


@pytest.mark.integration
def test_certified_relation_arms_match_authoritative_rust_semantics(challenge: Path) -> None:
    """Every M3 family preserves its claimed public architecture and static metric in Rust."""
    anchor = AnchorSwitchTemplate().instantiate(
        instance_id="live-anchor",
        lane=0,
        token=0,
        epoch=0,
        bank_a=0,
        bank_b=2,
        pad=0,
    )
    relations = [
        anchor,
        TokenSwitchTemplate().instantiate(
            instance_id="live-token",
            lane=0,
            token_a=0,
            token_b=1,
            epoch=0,
            anchor=2,
            pad=0,
        ),
        EpochSwitchTemplate().instantiate(
            instance_id="live-epoch",
            lane=0,
            token=0,
            epoch_a=0,
            epoch_b=1,
            anchor=2,
            pad_a=0,
            pad_b=1,
        ),
        PhaseShiftTemplate().instantiate(
            instance_id="live-phase",
            lane=0,
            token=0,
            epoch=0,
            anchor=2,
            pad_a=0,
            pad_b=1,
        ),
        RepeatAmplifyTemplate().instantiate(
            instance_id="live-repeat",
            lane=0,
            token=0,
            epoch=0,
            anchor=2,
            pad=0,
            repeats=3,
        ),
        IndependentSwapTemplate().instantiate(
            instance_id="live-swap",
            first=Cell(0, 0, 0, 2),
            second=Cell(1, 1, 1, 3, 2),
        ),
        ContextLiftTemplate().instantiate(
            instance_id="live-context",
            base=anchor,
            prefix_pad=3,
        ),
    ]
    register_program = Program.parse(
        "MOVI r0, 7\nMOV r1, r0\nADD r2, r0, r1\nMIXOUT r2\nHALT\n",
        lanes=4,
    )
    relations.append(
        RegisterRenameTemplate().instantiate(
            instance_id="live-register",
            source=register_program,
            permutation=(1, 2, 0, 3, 4, 5, 6, 7),
        )
    )
    relations.append(
        HardReplayTemplate().instantiate(
            instance_id="live-replay",
            program=anchor.source_program,
            repetitions=3,
            deterministic_observation=True,
        )
    )

    with VmClient.start(vm_binary(), challenge=challenge, timeout_seconds=2.0) as client:
        client.hello()
        for relation_index, relation in enumerate(relations):
            results = []
            for arm_index, program in enumerate(relation.programs):
                result = client.execute(
                    program.render(),
                    session_id=f"relation-{relation_index}-{arm_index}",
                    logical_batch_id=f"relation-{relation_index}",
                    reset="hard",
                )
                assert result.static_cycles == program.static_cycles()
                assert result.status == "halted"
                results.append(result)
            assert {result.public_digest for result in results} == {results[0].public_digest}
            if relation.relation_id == "hard-replay/v1":
                assert len({result.observation.cycle_bucket for result in results}) == 1


@pytest.mark.integration
def test_durable_harness_records_real_wire_bytes_before_materialization(
    challenge: Path,
    tmp_path: Path,
) -> None:
    """The authoritative process uses stable IDs and replayable write-ahead evidence."""
    profile_bytes = (challenge / "public/profile.toml").read_bytes()
    repository = CampaignRepository.create(
        tmp_path / "durable-run",
        CampaignManifest(
            campaign_id="live-durable",
            challenge_id="pytest-challenge",
            challenge_commitment=json.loads(
                (challenge / "public/challenge.json").read_text(encoding="utf-8")
            )["commitment"],
            profile_name="tutorial",
            semantic_version="0.1.0",
            public_profile_sha256=hashlib.sha256(profile_bytes).hexdigest(),
            seed=20260716,
            minimum_certificate_strength="exhaustive-enumeration",
            logical_query_budget=80,
            physical_execution_budget=240,
            hard_reset_budget=240,
        ),
    )
    program = "PROBE 0, 0, 0\nANCHOR 0, 0\nHALT\n"
    repository.append_event(
        event_id="query:live-query",
        kind="query_created",
        logical_time=0,
        payload={
            "query_id": "live-query",
            "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
            "program_text": program,
            "expires_after": None,
        },
    )
    repository.append_event(
        event_id="batch:live-batch",
        kind="batch_scheduled",
        logical_time=0,
        payload={
            "batch_id": "live-batch",
            "seed": 20260716,
            "schedule": ["live-execution"],
            "status": "scheduled",
        },
    )
    harness, client = DurableExecutionHarness.start_process(
        repository,
        vm_binary(),
        challenge=challenge,
        timeout_seconds=2.0,
    )
    try:
        client.hello()
        result = harness.execute(
            ExecutionSpec(
                execution_id="live-execution",
                query_id="live-query",
                batch_id="live-batch",
                position=0,
                program=program,
                session_id="live-session",
                reset="hard",
                logical_time=1,
                execution_seed_id="live-seed",
            )
        )
    finally:
        client.close()
    assert result.request_id == "live-execution"
    raw = repository.raw.get("live-execution")
    assert raw is not None
    assert json.loads(raw.request_line)["request_id"] == "live-execution"
    assert json.loads(raw.response_line)["kind"] == "execute_result"
    assert repository.database.table_count("executions") == 1
    digest = repository.database.digest()
    assert repository.rebuild() == digest
    repository.close()


@pytest.mark.integration
def test_tutorial_campaign_recovers_uniquely_judges_once_and_resumes(
    challenge: Path,
    tmp_path: Path,
) -> None:
    """The complete M5 flow recovers through relations and reuses its accepted report."""
    run = tmp_path / "tutorial-run"
    first = recover_tutorial(
        vm_binary=vm_binary(),
        challenge=challenge,
        run_directory=run,
        campaign_seed=53,
        submit_judge=True,
    )
    assert first.status == "unique_exact"
    jsonschema.Draft202012Validator(RECOVERY_REPORT_SCHEMA).validate(first.report)
    assert first.report["uniqueness"]["alternative_model_unsat"] is True
    assert first.report["cost"]["logical_relation_families"] == 16
    assert first.report["cost"]["physical_executions"] == 32
    assert first.report["judge"]["submission_recorded"] is True
    assert first.report["judge"]["accepted"] is True
    repository = CampaignRepository.open(run)
    assert repository.database.table_count("judge_submissions") == 1
    digest = repository.database.digest()
    assert repository.rebuild() == digest
    repository.close()

    resumed = recover_tutorial(
        vm_binary=vm_binary(),
        challenge=challenge,
        run_directory=run,
        campaign_seed=53,
        submit_judge=True,
    )
    assert resumed.report == first.report


@pytest.mark.integration
def test_fault_free_tutorial_control_never_declares_exact_recovery(tmp_path: Path) -> None:
    """All equal off-fault observations retain every secret and never invoke the judge."""
    challenge = tmp_path / "fault-free-challenge"
    created = subprocess.run(
        [
            str(vm_binary()),
            "challenge",
            "create",
            "--profile",
            str(PROFILE),
            "--output",
            str(challenge),
            "--challenge-id",
            "tutorial-fault-free",
            "--seed",
            "59",
            "--fault",
            "off",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert created.returncode == 0, created.stderr
    result = recover_tutorial(
        vm_binary=vm_binary(),
        challenge=challenge,
        run_directory=tmp_path / "fault-free-run",
        campaign_seed=61,
        submit_judge=False,
    )
    jsonschema.Draft202012Validator(RECOVERY_REPORT_SCHEMA).validate(result.report)
    assert result.status == "inconclusive"
    assert result.report["unique_secret_hex"] is None
    assert result.report["uniqueness"]["alternative_model_unsat"] is False
    assert result.report["judge"] is None


@pytest.mark.integration
def test_synthesized_typed_relation_executes_through_public_process(challenge: Path) -> None:
    """M6 committee synthesis lowers to a certified pair accepted by the real VM."""
    models = tuple(SynthesisModel(f"survivor-{value:02d}", (value,)) for value in range(16))
    committee = DiverseCommittee.select(models, limit=16, complete=True)
    grammar = BoundedRelationGrammar(
        lanes=(0,),
        tokens=(0, 1),
        epochs=(0, 1),
        pads=(0, 1, 2, 3),
        include_repeat_amplify=False,
    )
    synthesized = CegisSynthesizer(grammar).synthesize(
        committee,
        SynthesisContext(hypothesis_fingerprint=committee.fingerprint(), maximum_bucket_size=8),
    )
    assert synthesized.status is SynthesisStatus.SAT
    assert synthesized.score is not None
    assert isinstance(synthesized.score.candidate, QueryCandidate)
    relation = synthesized.score.candidate.lower("live-synthesized")
    assert relation.architectural_precheck()
    assert relation.fault_free_precheck()

    with VmClient.start(vm_binary(), challenge=challenge, timeout_seconds=2.0) as client:
        hello = client.hello()
        source = client.execute(
            relation.source_program.render(),
            session_id="m6-source",
            logical_batch_id="m6-synthesized",
            reset="hard",
            execution_seed_id="m6-correlated",
        )
        follow_up = client.execute(
            relation.follow_up_programs[0].render(),
            session_id="m6-follow-up",
            logical_batch_id="m6-synthesized",
            reset="hard",
            execution_seed_id="m6-correlated",
        )
    assert hello.profile_name == "tutorial"
    assert source.public_digest == follow_up.public_digest
    assert source.static_cycles == relation.source_program.static_cycles()
    assert follow_up.static_cycles == relation.follow_up_programs[0].static_cycles()
    decision = AnchorSwitchTemplate().decide(relation, source, follow_up, noise_bound=0)
    assert decision.kind.value.startswith("exact_")
