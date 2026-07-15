"""Black-box JSONL client for a local SphinxVM process."""

from __future__ import annotations

import json
import selectors
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, cast

from sphinx_interrogator.model import ExecutionObservation, ExecutionResult

_PROTOCOL_VERSION = "1.0"
_MAX_RESPONSE_LINE_BYTES = 131_072
_DEFAULT_TIMEOUT_SECONDS = 5.0


class ProtocolError(RuntimeError):
    """Raised when the target rejects a request or violates the public protocol."""


@dataclass(frozen=True, slots=True)
class HelloResult:
    """Public server capabilities returned by the handshake."""

    server_version: str
    build_id: str
    profile_name: str
    semantic_version: str
    bucket_width: int
    lanes: int
    hard_reset_available: bool
    capabilities: tuple[str, ...]
    max_request_line_bytes: int
    max_program_bytes: int
    max_instructions: int
    max_gas: int
    max_sessions: int
    hard_resets: int
    logical_queries: int
    physical_executions: int


class VmClient:
    """Synchronous request/response client preserving the process boundary."""

    def __init__(
        self,
        process: subprocess.Popen[str],
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Wrap an already-started text-mode process."""
        if process.stdin is None or process.stdout is None:
            raise ValueError("process must have stdin and stdout pipes")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._process = process
        self._stdin: IO[str] = process.stdin
        self._stdout: IO[str] = process.stdout
        self._counter = 0
        self._timeout_seconds = timeout_seconds

    @classmethod
    def start(
        cls,
        executable: str | Path,
        *,
        profile: str | Path,
        extra_args: Sequence[str] = (),
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
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
        return cls(process, timeout_seconds=timeout_seconds)

    def hello(self) -> HelloResult:
        """Perform a versioned protocol handshake."""
        message = self._exchange(
            {
                "protocol_version": _PROTOCOL_VERSION,
                "request_id": self._next_request_id(),
                "kind": "hello",
                "client": {"name": "sphinx-interrogator", "version": "0.1.0"},
            },
            expected_kind="hello_result",
        )
        server = _mapping(message, "server")
        profile = _mapping(message, "profile")
        limits = _mapping(message, "limits")
        return HelloResult(
            server_version=_string(server, "version"),
            build_id=_string(server, "build_id"),
            profile_name=_string(profile, "name"),
            semantic_version=_string(profile, "semantic_version"),
            bucket_width=_integer(profile, "bucket_width"),
            lanes=_integer(profile, "lanes"),
            hard_reset_available=_boolean(profile, "hard_reset_available"),
            capabilities=_string_tuple(message, "capabilities"),
            max_request_line_bytes=_integer(limits, "max_request_line_bytes"),
            max_program_bytes=_integer(limits, "max_program_bytes"),
            max_instructions=_integer(limits, "max_instructions"),
            max_gas=_integer(limits, "max_gas"),
            max_sessions=_integer(limits, "max_sessions"),
            hard_resets=_integer(limits, "hard_resets"),
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
        message = self._exchange(request, expected_kind="execute_result")
        observation = _mapping(message, "observation")
        metrics = _mapping(message, "public_metrics")
        budget = _mapping(message, "budget")
        semantics = _mapping(message, "semantics")
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
            logical_queries_used=_integer(budget, "logical_queries_used"),
            logical_queries_remaining=_integer(budget, "logical_queries_remaining"),
            hard_resets_used=_integer(budget, "hard_resets_used"),
            hard_resets_remaining=_integer(budget, "hard_resets_remaining"),
            server_version=_string(semantics, "server_version"),
            profile_version=_string(semantics, "profile_version"),
        )

    def close(self) -> None:
        """Request a clean shutdown and wait for the local process."""
        if self._process.poll() is not None:
            return
        try:
            self._exchange(
                {
                    "protocol_version": _PROTOCOL_VERSION,
                    "request_id": self._next_request_id(),
                    "kind": "close",
                },
                expected_kind="close_result",
            )
        except ProtocolError:
            self.abort()
            raise
        finally:
            self._stdin.close()
        try:
            self._process.wait(timeout=self._timeout_seconds)
        except subprocess.TimeoutExpired as error:
            self.abort()
            raise ProtocolError("target did not exit after close_result") from error

    def abort(self) -> None:
        """Terminate an unresponsive target without waiting indefinitely."""
        if self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=self._timeout_seconds)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=self._timeout_seconds)

    def __enter__(self) -> VmClient:
        """Return this client for context-manager use."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close the process when leaving a context manager."""
        try:
            self.close()
        except ProtocolError:
            if exc is None:
                raise
            self.abort()

    def _next_request_id(self) -> str:
        self._counter += 1
        return f"py-{self._counter}"

    def _exchange(
        self,
        request: Mapping[str, object],
        *,
        expected_kind: str,
    ) -> Mapping[str, object]:
        if self._process.poll() is not None:
            raise ProtocolError("target process is not running")
        expected_request_id = _string(request, "request_id")
        serialized = json.dumps(request, separators=(",", ":"), sort_keys=True)
        self._stdin.write(serialized + "\n")
        self._stdin.flush()
        response_line = self._readline_with_timeout()
        if not response_line:
            stderr = ""
            if self._process.stderr is not None:
                stderr = self._process.stderr.read()
            raise ProtocolError(f"target closed the protocol stream: {stderr.strip()}")
        if len(response_line.encode("utf-8")) > _MAX_RESPONSE_LINE_BYTES:
            raise ProtocolError("protocol response exceeds the configured line limit")
        try:
            decoded: object = json.loads(response_line)
        except json.JSONDecodeError as error:
            raise ProtocolError(f"protocol response is invalid JSON: {error}") from error
        if not isinstance(decoded, dict):
            raise ProtocolError("protocol response is not a JSON object")
        message = cast("dict[str, object]", decoded)
        if message.get("protocol_version") != _PROTOCOL_VERSION:
            raise ProtocolError("protocol version mismatch")
        if message.get("request_id") != expected_request_id:
            raise ProtocolError("protocol response request_id mismatch")
        if message.get("kind") == "error":
            error_details = _mapping(message, "error")
            raise ProtocolError(
                f"{_string(error_details, 'code')}: {_string(error_details, 'message')}"
            )
        if message.get("kind") != expected_kind:
            raise ProtocolError(
                f"expected response kind {expected_kind}, received {message.get('kind')!r}"
            )
        if message.get("ok") is not True:
            raise ProtocolError("successful protocol response must set ok=true")
        _reject_unexpected_top_level_fields(message, expected_kind)
        return message

    def _readline_with_timeout(self) -> str:
        selector = selectors.DefaultSelector()
        try:
            selector.register(self._stdout, selectors.EVENT_READ)
            if not selector.select(self._timeout_seconds):
                raise ProtocolError(
                    f"target did not respond within {self._timeout_seconds:.3f} seconds"
                )
            return self._stdout.readline(_MAX_RESPONSE_LINE_BYTES + 1)
        finally:
            selector.close()


_EXPECTED_TOP_LEVEL_FIELDS: dict[str, frozenset[str]] = {
    "hello_result": frozenset(
        {
            "protocol_version",
            "request_id",
            "kind",
            "ok",
            "server",
            "profile",
            "capabilities",
            "limits",
        }
    ),
    "execute_result": frozenset(
        {
            "protocol_version",
            "request_id",
            "kind",
            "ok",
            "session_id",
            "status",
            "public_digest",
            "observation",
            "public_metrics",
            "budget",
            "semantics",
        }
    ),
    "close_result": frozenset({"protocol_version", "request_id", "kind", "ok"}),
}


def _reject_unexpected_top_level_fields(message: Mapping[str, object], kind: str) -> None:
    unexpected = set(message).difference(_EXPECTED_TOP_LEVEL_FIELDS[kind])
    if unexpected:
        raise ProtocolError(f"unexpected public response fields: {sorted(unexpected)}")


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


def _boolean(value: Mapping[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ProtocolError(f"field {key} is not a boolean")
    return item


def _string_tuple(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or any(not isinstance(entry, str) for entry in item):
        raise ProtocolError(f"field {key} is not an array of strings")
    return tuple(item)
