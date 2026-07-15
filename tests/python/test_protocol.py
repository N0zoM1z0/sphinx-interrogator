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
