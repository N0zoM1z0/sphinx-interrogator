"""Cross-language tests for the release-shaped SphinxVM JSONL process."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sphinx_interrogator.ast import Program
from sphinx_interrogator.protocol import VmClient

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "benchmarks/profiles/tutorial.toml"
SCHEMA = json.loads((ROOT / "spec/protocol.schema.json").read_text(encoding="utf-8"))


def vm_binary() -> Path:
    """Return the separately built VM binary or skip direct pytest invocations."""
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        pytest.skip("SPHINX_VM_BINARY is set by `just test` after building the Rust target")
    binary = Path(configured).resolve()
    if not binary.is_file():
        pytest.fail(f"configured SphinxVM binary does not exist: {binary}")
    return binary


@pytest.mark.integration
def test_client_round_trip_tracks_public_budgets_and_versions() -> None:
    """Python must negotiate and execute only through the real process boundary."""
    with VmClient.start(vm_binary(), profile=PROFILE, timeout_seconds=2.0) as client:
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
def test_server_recovers_after_malformed_and_oversized_lines() -> None:
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
        [str(vm_binary()), "--profile", str(PROFILE)],
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
def test_python_canonical_program_and_sparse_memory_execute_in_rust() -> None:
    """The independent Python representation is accepted by the authoritative parser."""
    source = (ROOT / "tests/fixtures/programs/full-v1.source.spx").read_text(encoding="utf-8")
    canonical = Program.parse(source, lanes=4).render()
    with VmClient.start(vm_binary(), profile=PROFILE, timeout_seconds=2.0) as client:
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
