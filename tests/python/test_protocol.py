"""Unit tests for protocol correlation, bounds, and timeout handling."""

from __future__ import annotations

import subprocess
import sys

import pytest

from sphinx_interrogator.protocol import ProtocolError, VmClient


def fake_process(source: str) -> subprocess.Popen[str]:
    """Launch a tiny unbuffered protocol peer for negative client tests."""
    return subprocess.Popen(
        [sys.executable, "-u", "-c", source],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )


def test_client_rejects_mismatched_request_id() -> None:
    """A response for another request must never be accepted as evidence."""
    source = (
        "import json, sys; "
        "json.loads(sys.stdin.readline()); "
        "print(json.dumps({'protocol_version':'1.0','request_id':'wrong',"
        "'kind':'hello_result','ok':True,'server':{},'profile':{},'limits':{}}), flush=True)"
    )
    process = fake_process(source)
    client = VmClient(process, timeout_seconds=1.0)
    with pytest.raises(ProtocolError, match="request_id mismatch"):
        client.hello()
    client.abort()


def test_client_times_out_and_can_abort_target() -> None:
    """A silent target produces a bounded transport error rather than a hang."""
    process = fake_process("import sys, time; sys.stdin.readline(); time.sleep(60)")
    client = VmClient(process, timeout_seconds=0.1)
    with pytest.raises(ProtocolError, match="did not respond"):
        client.hello()
    client.abort()
    assert process.poll() is not None


def test_nested_private_response_field_is_rejected_before_recording() -> None:
    """A schema-invalid nested field cannot enter the durable raw transcript."""
    source = """
import json
import sys

request = json.loads(sys.stdin.readline())
print(json.dumps({
    "protocol_version": "1.0",
    "request_id": request["request_id"],
    "kind": "hello_result",
    "ok": True,
    "server": {"name": "sphinx-vm", "version": "0.1.0", "build_id": "test"},
    "profile": {
        "name": "tutorial",
        "semantic_version": "0.1.0",
        "bucket_width": 1,
        "lanes": 4,
        "hard_reset_available": True,
        "secret": "forbidden"
    },
    "capabilities": ["close", "execute", "hard_reset"],
    "limits": {
        "max_request_line_bytes": 131072,
        "max_program_bytes": 65536,
        "max_instructions": 256,
        "max_gas": 10000,
        "max_sessions": 8,
        "hard_resets": 240,
        "logical_queries": 80,
        "physical_executions": 240
    }
}), flush=True)
"""
    process = fake_process(source)
    recorded: list[tuple[str, str]] = []
    client = VmClient(
        process,
        timeout_seconds=1.0,
        exchange_recorder=lambda request, response: recorded.append((request, response)),
    )
    with pytest.raises(ProtocolError, match="profile fields"):
        client.hello()
    assert recorded == []
    client.abort()
