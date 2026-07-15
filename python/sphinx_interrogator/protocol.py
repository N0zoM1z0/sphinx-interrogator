"""Black-box JSONL client for a local SphinxVM process."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, cast

from sphinx_interrogator.model import ExecutionObservation, ExecutionResult

_PROTOCOL_VERSION = "1.0"


class ProtocolError(RuntimeError):
    """Raised when the target rejects a request or violates the public protocol."""


@dataclass(frozen=True, slots=True)
class HelloResult:
    """Public server capabilities returned by the handshake."""

    profile_name: str
    semantic_version: str
    bucket_width: int
    lanes: int
    max_program_bytes: int
    max_instructions: int
    max_gas: int
    logical_queries: int
    physical_executions: int


class VmClient:
    """Synchronous request/response client preserving the process boundary."""

    def __init__(self, process: subprocess.Popen[str]) -> None:
        """Wrap an already-started text-mode process."""
        if process.stdin is None or process.stdout is None:
            raise ValueError("process must have stdin and stdout pipes")
        self._process = process
        self._stdin: IO[str] = process.stdin
        self._stdout: IO[str] = process.stdout
        self._counter = 0

    @classmethod
    def start(
        cls,
        executable: str | Path,
        *,
        profile: str | Path,
        extra_args: Sequence[str] = (),
    ) -> VmClient:
        """Start the public VM binary without importing or linking its implementation."""
        command = [str(executable), "--profile", str(profile), *extra_args]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        return cls(process)

    def hello(self) -> HelloResult:
        """Perform a versioned protocol handshake."""
        message = self._exchange(
            {
                "protocol_version": _PROTOCOL_VERSION,
                "request_id": self._next_request_id(),
                "kind": "hello",
                "client": {"name": "sphinx-interrogator", "version": "0.1.0"},
            }
        )
        profile = _mapping(message, "profile")
        limits = _mapping(message, "limits")
        return HelloResult(
            profile_name=_string(profile, "name"),
            semantic_version=_string(profile, "semantic_version"),
            bucket_width=_integer(profile, "bucket_width"),
            lanes=_integer(profile, "lanes"),
            max_program_bytes=_integer(limits, "max_program_bytes"),
            max_instructions=_integer(limits, "max_instructions"),
            max_gas=_integer(limits, "max_gas"),
            logical_queries=_integer(limits, "logical_queries"),
            physical_executions=_integer(limits, "physical_executions"),
        )

    def execute(
        self,
        program: str,
        *,
        session_id: str,
        logical_batch_id: str,
        reset: str = "hard",
        registers: Sequence[int] = (),
        execution_seed_id: str | None = None,
    ) -> ExecutionResult:
        """Execute one public program and decode its aggregate observation."""
        request_id = self._next_request_id()
        request: dict[str, object] = {
            "protocol_version": _PROTOCOL_VERSION,
            "request_id": request_id,
            "kind": "execute",
            "session_id": session_id,
            "reset": reset,
            "program": program,
            "public_input": {"registers": list(registers), "memory": {}},
            "logical_batch_id": logical_batch_id,
        }
        if execution_seed_id is not None:
            request["execution_seed_id"] = execution_seed_id
        message = self._exchange(request)
        observation = _mapping(message, "observation")
        metrics = _mapping(message, "public_metrics")
        budget = _mapping(message, "budget")
        return ExecutionResult(
            request_id=_string(message, "request_id"),
            session_id=_string(message, "session_id"),
            status=_string(message, "status"),
            public_digest=_string(message, "public_digest"),
            observation=ExecutionObservation(
                cycle_bucket=_integer(observation, "cycle_bucket"),
                bucket_width=_integer(observation, "bucket_width"),
                samples_in_vm=_integer(observation, "samples_in_vm"),
            ),
            retired_instructions=_integer(metrics, "retired_instructions"),
            static_cycles=_integer(metrics, "static_cycles"),
            physical_executions_used=_integer(budget, "physical_executions_used"),
            physical_executions_remaining=_integer(budget, "physical_executions_remaining"),
        )

    def close(self) -> None:
        """Request a clean shutdown and wait for the local process."""
        if self._process.poll() is not None:
            return
        self._exchange(
            {
                "protocol_version": _PROTOCOL_VERSION,
                "request_id": self._next_request_id(),
                "kind": "close",
            }
        )
        self._stdin.close()
        self._process.wait(timeout=5)

    def __enter__(self) -> VmClient:
        """Return this client for context-manager use."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close the process when leaving a context manager."""
        self.close()

    def _next_request_id(self) -> str:
        self._counter += 1
        return f"py-{self._counter}"

    def _exchange(self, request: Mapping[str, object]) -> Mapping[str, object]:
        if self._process.poll() is not None:
            raise ProtocolError("target process is not running")
        serialized = json.dumps(request, separators=(",", ":"), sort_keys=True)
        self._stdin.write(serialized + "\n")
        self._stdin.flush()
        response_line = self._stdout.readline()
        if not response_line:
            stderr = ""
            if self._process.stderr is not None:
                stderr = self._process.stderr.read()
            raise ProtocolError(f"target closed the protocol stream: {stderr.strip()}")
        decoded: object = json.loads(response_line)
        if not isinstance(decoded, dict):
            raise ProtocolError("protocol response is not a JSON object")
        message = cast("dict[str, object]", decoded)
        if message.get("kind") == "error":
            error = _mapping(message, "error")
            raise ProtocolError(f"{_string(error, 'code')}: {_string(error, 'message')}")
        if message.get("protocol_version") != _PROTOCOL_VERSION:
            raise ProtocolError("protocol version mismatch")
        return message


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ProtocolError(f"field {key} is not an object")
    return cast("dict[str, object]", item)


def _string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ProtocolError(f"field {key} is not a string")
    return item


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ProtocolError(f"field {key} is not an integer")
    return item
