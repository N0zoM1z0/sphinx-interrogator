"""Crash, replay, migration, and provenance tests for durable campaign state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from sphinx_interrogator.persistence import (
    CampaignManifest,
    CampaignRepository,
    EventLog,
    PersistenceError,
)


def _manifest() -> CampaignManifest:
    return CampaignManifest(
        campaign_id="campaign-test",
        challenge_id="challenge-public",
        challenge_commitment="0" * 64,
        profile_name="tutorial",
        semantic_version="0.1.0",
        public_profile_sha256="1" * 64,
        seed=17,
        minimum_certificate_strength="exhaustive-enumeration",
        logical_query_budget=80,
        physical_execution_budget=240,
        hard_reset_budget=240,
    )


def _append_query_batch(repository: CampaignRepository) -> None:
    repository.append_event(
        event_id="query:q-source",
        kind="query_created",
        logical_time=0,
        payload={
            "query_id": "q-source",
            "program_sha256": hashlib.sha256(b"HALT\n").hexdigest(),
            "program_text": "HALT\n",
            "expires_after": None,
        },
    )
    repository.append_event(
        event_id="batch:b-1",
        kind="batch_scheduled",
        logical_time=0,
        payload={
            "batch_id": "b-1",
            "seed": 17,
            "schedule": ["q-source", "q-source"],
            "status": "scheduled",
        },
    )


def _wire_lines(request_id: str, bucket: int) -> tuple[str, str]:
    request = {
        "protocol_version": "1.0",
        "request_id": request_id,
        "kind": "execute",
        "session_id": "session-1",
        "reset": "hard",
        "program": "HALT\n",
        "logical_batch_id": "b-1",
    }
    response = {
        "protocol_version": "1.0",
        "request_id": request_id,
        "kind": "execute_result",
        "ok": True,
        "session_id": "session-1",
        "status": "halted",
        "public_digest": "0000000000000000",
        "observation": {"cycle_bucket": bucket, "bucket_width": 1, "samples_in_vm": 1},
        "public_metrics": {"retired_instructions": 1, "static_cycles": 1},
        "budget": {
            "physical_executions_used": 1,
            "physical_executions_remaining": 239,
            "logical_queries_used": 1,
            "logical_queries_remaining": 79,
            "hard_resets_used": 1,
            "hard_resets_remaining": 239,
        },
        "semantics": {"server_version": "0.1.0", "profile_version": "0.1.0"},
    }
    return (
        json.dumps(request, sort_keys=True, separators=(",", ":")),
        json.dumps(response, sort_keys=True, separators=(",", ":")),
    )


def test_manifest_is_immutable_and_event_log_detects_tampering(tmp_path: Path) -> None:
    """Stable campaign inputs and the event hash chain fail closed on disagreement."""
    repository = CampaignRepository.create(tmp_path / "run", _manifest())
    _append_query_batch(repository)
    repository.close()
    reopened = CampaignRepository.open(tmp_path / "run")
    assert reopened.manifest == _manifest()
    reopened.close()

    changed = replace(_manifest(), seed=18)
    with pytest.raises(PersistenceError, match="manifest conflicts"):
        CampaignRepository.create(tmp_path / "run", changed)

    event_path = tmp_path / "run/events.jsonl"
    lines = event_path.read_text(encoding="utf-8").splitlines()
    document = json.loads(lines[0])
    document["logical_time"] = 99
    lines[0] = json.dumps(document, sort_keys=True, separators=(",", ":"))
    event_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(PersistenceError, match="event hash"):
        EventLog(event_path)


def test_manifest_reads_version_one_runs_without_inventing_a_commitment(
    tmp_path: Path,
) -> None:
    """Version 1.0 remains inspectable, including the short-lived bound variant."""
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    legacy = _manifest().to_data()
    legacy["manifest_version"] = "1.0"
    legacy.pop("challenge_commitment")
    (legacy_root / "manifest.json").write_text(json.dumps(legacy), encoding="utf-8")
    repository = CampaignRepository.open(legacy_root)
    assert repository.manifest.challenge_commitment is None
    assert repository.manifest.to_data() == legacy
    repository.close()

    transitional_root = tmp_path / "transitional"
    transitional_root.mkdir()
    transitional = _manifest().to_data()
    transitional["manifest_version"] = "1.0"
    (transitional_root / "manifest.json").write_text(json.dumps(transitional), encoding="utf-8")
    reopened = CampaignRepository.open(transitional_root)
    assert reopened.manifest == _manifest()
    reopened.close()


def test_crash_after_raw_response_resumes_without_duplicate_evidence(tmp_path: Path) -> None:
    """A durable raw response is analyzed once after restart without re-execution."""
    root = tmp_path / "run"
    repository = CampaignRepository.create(root, _manifest())
    _append_query_batch(repository)
    request, response = _wire_lines("request-1", 7)

    def crash() -> None:
        raise RuntimeError("injected crash after raw fsync")

    with pytest.raises(RuntimeError, match="injected crash"):
        repository.record_raw_execution(
            execution_id="execution-1",
            query_id="q-source",
            batch_id="b-1",
            position=0,
            request_line=request,
            response_line=response,
            logical_time=1,
            after_raw=crash,
        )
    assert repository.raw.get("execution-1") is not None
    assert repository.database.table_count("executions") == 0
    repository.close()

    resumed = CampaignRepository.open(root)
    resumed.commit_raw_execution(
        execution_id="execution-1",
        query_id="q-source",
        batch_id="b-1",
        position=0,
        logical_time=1,
    )
    resumed.commit_raw_execution(
        execution_id="execution-1",
        query_id="q-source",
        batch_id="b-1",
        position=0,
        logical_time=1,
    )
    assert resumed.database.table_count("executions") == 1
    assert len(tuple(event for event in resumed.events if event.kind == "execution_recorded")) == 1
    resumed.close()


def test_constraint_provenance_requires_raw_requests_and_certificates(tmp_path: Path) -> None:
    """Every materialized hard constraint links to raw requests, relation, and proof."""
    repository = CampaignRepository.create(tmp_path / "run", _manifest())
    _append_query_batch(repository)
    for position, request_id in enumerate(("request-source", "request-follow-up")):
        request, response = _wire_lines(request_id, 8 + position)
        repository.record_raw_execution(
            execution_id=f"execution-{position}",
            query_id="q-source",
            batch_id="b-1",
            position=position,
            request_line=request,
            response_line=response,
            logical_time=1,
        )
    repository.append_event(
        event_id="certificate:cert-1",
        kind="certificate_registered",
        logical_time=2,
        payload={"certificate_id": "cert-1", "certificate": {"proof_method": "theorem"}},
    )
    repository.append_event(
        event_id="relation:relation-1",
        kind="relation_recorded",
        logical_time=2,
        payload={
            "relation_instance_id": "relation-1",
            "relation_id": "anchor-switch/v1",
            "certificate_id": "cert-1",
            "relation": {"instance_hash": "a" * 64},
        },
    )
    repository.append_event(
        event_id="decision:decision-1",
        kind="decision_recorded",
        logical_time=2,
        payload={
            "decision_id": "decision-1",
            "relation_instance_id": "relation-1",
            "kind": "exact_greater",
            "decision": {"delta": 1},
        },
    )
    repository.append_event(
        event_id="constraint:constraint-1",
        kind="constraint_added",
        logical_time=2,
        payload={
            "constraint_id": "constraint-1",
            "group_id": "evidence-1",
            "relation_instance_id": "relation-1",
            "certificate_id": "cert-1",
            "source_request_ids": ["request-source", "request-follow-up"],
            "approximation": "exact",
            "constraint": {"kind": "fixture"},
        },
    )
    assert repository.database.active_constraint_ids() == ("constraint-1",)
    before = len(repository.events)
    with pytest.raises(PersistenceError, match="missing raw execution"):
        repository.append_event(
            event_id="constraint:bad",
            kind="constraint_added",
            logical_time=3,
            payload={
                "constraint_id": "bad",
                "group_id": "bad",
                "relation_instance_id": "relation-1",
                "certificate_id": "cert-1",
                "source_request_ids": ["missing-request"],
                "approximation": "exact",
                "constraint": {},
            },
        )
    assert len(repository.events) == before
    repository.close()


def test_rebuild_and_reopen_reproduce_identical_materialized_state(tmp_path: Path) -> None:
    """SQLite is a deterministic disposable view of the authoritative event stream."""
    root = tmp_path / "run"
    repository = CampaignRepository.create(root, _manifest())
    _append_query_batch(repository)
    request, response = _wire_lines("request-1", 4)
    repository.record_raw_execution(
        execution_id="execution-1",
        query_id="q-source",
        batch_id="b-1",
        position=0,
        request_line=request,
        response_line=response,
        logical_time=1,
    )
    original_digest = repository.database.digest()
    report_before = repository.report()
    assert repository.rebuild() == original_digest
    assert repository.report() == report_before
    repository.close()
    reopened = CampaignRepository.open(root)
    assert reopened.database.digest() == original_digest
    reopened.close()


def test_empty_and_existing_v1_databases_migrate_but_future_version_fails(
    tmp_path: Path,
) -> None:
    """Schema migration is idempotent and never guesses about future formats."""
    run = tmp_path / "run"
    repository = CampaignRepository.create(run, _manifest())
    assert repository.database.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    repository.close()
    prior = sqlite3.connect(run / "campaign.sqlite3")
    prior.execute("DROP TABLE judge_submissions")
    prior.execute("PRAGMA user_version = 1")
    prior.close()
    reopened = CampaignRepository.open(run)
    assert reopened.database.table_count("events") == 0
    assert reopened.database.table_count("judge_submissions") == 0
    reopened.close()

    future_root = tmp_path / "future"
    future_root.mkdir()
    (future_root / "manifest.json").write_text(json.dumps(_manifest().to_data()), encoding="utf-8")
    connection = sqlite3.connect(future_root / "campaign.sqlite3")
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    with pytest.raises(PersistenceError, match="future database"):
        CampaignRepository.open(future_root)
