"""Black-box JSONL client for a local SphinxVM process."""

from __future__ import annotations

import json
import re
import selectors
import socket
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO, cast

from sphinx_interrogator.model import ExecutionObservation, ExecutionResult

_PROTOCOL_VERSION = "1.0"
_MAX_RESPONSE_LINE_BYTES = 131_072
_DEFAULT_TIMEOUT_SECONDS = 5.0
_PUBLIC_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

type ExchangeRecorder = Callable[[str, str], None]


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
    """Synchronous request/response client over a public stream or Unix socket."""

    def __init__(
        self,
        process: subprocess.Popen[str] | None,
        *,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
        transport_socket: socket.socket | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        exchange_recorder: ExchangeRecorder | None = None,
    ) -> None:
        """Wrap an already-started public transport without target-private capabilities."""
        if process is not None:
            if process.stdin is None or process.stdout is None:
                raise ValueError("process must have stdin and stdout pipes")
            if stdin is not None or stdout is not None or transport_socket is not None:
                raise ValueError("process transport cannot be combined with explicit streams")
            stdin = process.stdin
            stdout = process.stdout
        elif stdin is None or stdout is None or transport_socket is None:
            raise ValueError("socket transport requires streams and its owning socket")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._process = process
        self._stdin = stdin
        self._stdout = stdout
        self._transport_socket = transport_socket
        self._counter = 0
        self._timeout_seconds = timeout_seconds
        self._exchange_recorder = exchange_recorder
        self._closed = False

    @classmethod
    def connect_unix(
        cls,
        socket_path: str | Path,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        exchange_recorder: ExchangeRecorder | None = None,
    ) -> VmClient:
        """Connect to a VM launched by trusted orchestration under a separate identity."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        endpoint = str(socket_path)
        transport = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                transport.connect(endpoint)
                break
            except (FileNotFoundError, ConnectionRefusedError) as error:
                if time.monotonic() >= deadline:
                    transport.close()
                    raise ProtocolError(f"VM socket is unavailable: {endpoint}") from error
                time.sleep(0.01)
            except OSError:
                transport.close()
                raise
        stdin = transport.makefile("w", encoding="utf-8", newline="\n")
        stdout = transport.makefile("r", encoding="utf-8", newline="\n")
        return cls(
            None,
            stdin=stdin,
            stdout=stdout,
            transport_socket=transport,
            timeout_seconds=timeout_seconds,
            exchange_recorder=exchange_recorder,
        )

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
        memory: Mapping[int, int] | None = None,
        execution_seed_id: str | None = None,
        request_id: str | None = None,
    ) -> ExecutionResult:
        """Execute one public program and decode its aggregate observation."""
        resolved_request_id = self._next_request_id() if request_id is None else request_id
        if _PUBLIC_ID.fullmatch(resolved_request_id) is None:
            raise ValueError("request_id must be a valid public protocol identifier")
        request: dict[str, object] = {
            "protocol_version": _PROTOCOL_VERSION,
            "request_id": resolved_request_id,
            "kind": "execute",
            "session_id": session_id,
            "reset": reset,
            "program": program,
            "public_input": {
                "registers": list(registers),
                "memory": _encode_public_memory(memory),
            },
            "logical_batch_id": logical_batch_id,
        }
        if execution_seed_id is not None:
            request["execution_seed_id"] = execution_seed_id
        message = self._exchange(request, expected_kind="execute_result")
        return _execution_result(message)

    def close(self) -> None:
        """Request a clean shutdown and close the public transport."""
        if self._closed:
            return
        if self._process is not None and self._process.poll() is not None:
            self._closed = True
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
            self._stdout.close()
            if self._transport_socket is not None:
                self._transport_socket.close()
            self._closed = True
        if self._process is not None:
            try:
                self._process.wait(timeout=self._timeout_seconds)
            except subprocess.TimeoutExpired as error:
                self.abort()
                raise ProtocolError("target did not exit after close_result") from error

    def abort(self) -> None:
        """Close the endpoint or terminate an unresponsive test process."""
        if self._closed:
            return
        self._closed = True
        if self._transport_socket is not None:
            with suppress(OSError):
                self._transport_socket.shutdown(socket.SHUT_RDWR)
            self._transport_socket.close()
            self._stdin.close()
            self._stdout.close()
            return
        if self._process is None or self._process.poll() is not None:
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
        if self._closed:
            raise ProtocolError("target transport is closed")
        if self._process is not None and self._process.poll() is not None:
            raise ProtocolError("target process is not running")
        expected_request_id = _string(request, "request_id")
        serialized = json.dumps(request, separators=(",", ":"), sort_keys=True)
        self._stdin.write(serialized + "\n")
        self._stdin.flush()
        response_line = self._readline_with_timeout()
        if not response_line:
            stderr = ""
            if self._process is not None and self._process.stderr is not None:
                stderr = self._process.stderr.read()
            raise ProtocolError(f"target closed the protocol stream: {stderr.strip()}")
        if len(response_line.encode("utf-8")) > _MAX_RESPONSE_LINE_BYTES:
            raise ProtocolError("protocol response exceeds the configured line limit")
        message = _decode_response(response_line, expected_request_id, expected_kind)
        if self._exchange_recorder is not None:
            self._exchange_recorder(serialized, response_line.rstrip("\n"))
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


def submit_judge(
    socket_path: str | Path,
    *,
    campaign_token: str,
    guess: str,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> Mapping[str, object]:
    """Submit one guess to a separately launched one-shot judge endpoint."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    endpoint = str(socket_path)
    transport = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            transport.connect(endpoint)
            break
        except (FileNotFoundError, ConnectionRefusedError) as error:
            if time.monotonic() >= deadline:
                transport.close()
                raise ProtocolError(f"judge socket is unavailable: {endpoint}") from error
            time.sleep(0.01)
        except OSError:
            transport.close()
            raise
    try:
        request = json.dumps(
            {
                "judge_protocol_version": "1.0",
                "campaign_token": campaign_token,
                "guess": guess,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        transport.sendall((request + "\n").encode("utf-8"))
        transport.settimeout(timeout_seconds)
        response = bytearray()
        while b"\n" not in response:
            chunk = transport.recv(4096)
            if not chunk:
                raise ProtocolError("judge closed without a response")
            response.extend(chunk)
            if len(response) > _MAX_RESPONSE_LINE_BYTES:
                raise ProtocolError("judge response exceeds the configured line limit")
    except TimeoutError as error:
        raise ProtocolError("judge did not respond before the timeout") from error
    finally:
        transport.close()
    line = bytes(response).split(b"\n", maxsplit=1)[0]
    try:
        decoded: object = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("judge response is invalid JSON") from error
    if not isinstance(decoded, dict):
        raise ProtocolError("judge response is not a JSON object")
    message = cast("dict[str, object]", decoded)
    _validate_judge_response(message, campaign_token)
    return message


def decode_execute_response(response_line: str, *, expected_request_id: str) -> ExecutionResult:
    """Decode a previously write-ahead-recorded public execute response."""
    if len(response_line.encode("utf-8")) > _MAX_RESPONSE_LINE_BYTES:
        raise ProtocolError("protocol response exceeds the configured line limit")
    message = _decode_response(response_line, expected_request_id, "execute_result")
    return _execution_result(message)


def _decode_response(
    response_line: str,
    expected_request_id: str,
    expected_kind: str,
) -> Mapping[str, object]:
    """Validate one response independently of whether it came from a live stream or disk."""
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
    _validate_protocol_response(message)
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
    return message


def _execution_result(message: Mapping[str, object]) -> ExecutionResult:
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
    "error": frozenset({"protocol_version", "request_id", "kind", "ok", "error"}),
}


def _validate_protocol_response(message: Mapping[str, object]) -> None:
    """Enforce the complete public response shape before raw persistence or decoding."""
    kind = _string(message, "kind")
    expected = _EXPECTED_TOP_LEVEL_FIELDS.get(kind)
    if expected is None:
        raise ProtocolError(f"unknown public response kind: {kind!r}")
    _require_exact_fields(message, expected, "response")
    request_id = _string(message, "request_id")
    if _PUBLIC_ID.fullmatch(request_id) is None:
        raise ProtocolError("response request_id is not a valid public identifier")

    if kind == "hello_result":
        if message.get("ok") is not True:
            raise ProtocolError("hello_result must set ok=true")
        server = _mapping(message, "server")
        _require_exact_fields(server, {"name", "version", "build_id"}, "server")
        if _string(server, "name") != "sphinx-vm":
            raise ProtocolError("server name is not sphinx-vm")
        _require_bounded_string(server, "version", 1, 64)
        _require_bounded_string(server, "build_id", 1, 256)

        profile = _mapping(message, "profile")
        _require_exact_fields(
            profile,
            {"name", "semantic_version", "bucket_width", "lanes", "hard_reset_available"},
            "profile",
        )
        _require_bounded_string(profile, "name", 1, 128)
        _require_bounded_string(profile, "semantic_version", 1, 64)
        _require_integer_range(profile, "bucket_width", minimum=1)
        _require_integer_range(profile, "lanes", minimum=1, maximum=64)
        _boolean(profile, "hard_reset_available")

        capabilities = _string_tuple(message, "capabilities")
        allowed_capabilities = {"close", "execute", "hard_reset", "soft_reset"}
        if len(capabilities) != len(set(capabilities)) or not set(capabilities).issubset(
            allowed_capabilities
        ):
            raise ProtocolError("capabilities contain duplicates or unknown values")

        limits = _mapping(message, "limits")
        _require_exact_fields(
            limits,
            {
                "max_request_line_bytes",
                "max_program_bytes",
                "max_instructions",
                "max_gas",
                "max_sessions",
                "hard_resets",
                "logical_queries",
                "physical_executions",
            },
            "limits",
        )
        for key in (
            "max_request_line_bytes",
            "max_program_bytes",
            "max_instructions",
            "max_gas",
            "max_sessions",
        ):
            _require_integer_range(limits, key, minimum=1)
        for key in ("hard_resets", "logical_queries", "physical_executions"):
            _require_integer_range(limits, key, minimum=0)
        return

    if kind == "execute_result":
        if message.get("ok") is not True:
            raise ProtocolError("execute_result must set ok=true")
        session_id = _string(message, "session_id")
        if _PUBLIC_ID.fullmatch(session_id) is None:
            raise ProtocolError("response session_id is not a valid public identifier")
        if _string(message, "status") not in {"halted", "gas_exhausted"}:
            raise ProtocolError("execute_result status is invalid")
        if re.fullmatch(r"[0-9a-f]{16}", _string(message, "public_digest")) is None:
            raise ProtocolError("public_digest is not a lowercase 64-bit digest")

        observation = _mapping(message, "observation")
        _require_exact_fields(
            observation,
            {"cycle_bucket", "bucket_width", "samples_in_vm"},
            "observation",
        )
        _require_integer_range(observation, "cycle_bucket", minimum=0)
        _require_integer_range(observation, "bucket_width", minimum=1)
        if _integer(observation, "samples_in_vm") != 1:
            raise ProtocolError("samples_in_vm must equal one")

        metrics = _mapping(message, "public_metrics")
        _require_exact_fields(
            metrics,
            {"retired_instructions", "static_cycles"},
            "public_metrics",
        )
        _require_integer_range(metrics, "retired_instructions", minimum=0)
        _require_integer_range(metrics, "static_cycles", minimum=0)

        budget = _mapping(message, "budget")
        _require_exact_fields(
            budget,
            {
                "physical_executions_used",
                "physical_executions_remaining",
                "logical_queries_used",
                "logical_queries_remaining",
                "hard_resets_used",
                "hard_resets_remaining",
            },
            "budget",
        )
        for key in budget:
            _require_integer_range(budget, key, minimum=0)

        semantics = _mapping(message, "semantics")
        _require_exact_fields(
            semantics,
            {"server_version", "profile_version"},
            "semantics",
        )
        _require_bounded_string(semantics, "server_version", 1, 64)
        _require_bounded_string(semantics, "profile_version", 1, 64)
        return

    if kind == "close_result":
        if message.get("ok") is not True:
            raise ProtocolError("close_result must set ok=true")
        return

    if message.get("ok") is not False:
        raise ProtocolError("error response must set ok=false")
    details = _mapping(message, "error")
    _require_exact_fields(details, {"code", "message", "recoverable"}, "error")
    allowed_codes = {
        "invalid_json",
        "schema_error",
        "unsupported_version",
        "invalid_program",
        "budget_exhausted",
        "request_too_large",
        "session_limit",
        "internal_error",
    }
    if _string(details, "code") not in allowed_codes:
        raise ProtocolError("error response code is unknown")
    _require_bounded_string(details, "message", 0, 1024)
    _boolean(details, "recoverable")


def _validate_judge_response(
    message: Mapping[str, object],
    expected_campaign_token: str,
) -> None:
    _require_exact_fields(
        message,
        {
            "judge_version",
            "challenge_id",
            "campaign_token",
            "submission_recorded",
            "accepted",
        },
        "judge response",
    )
    if _string(message, "judge_version") != "1.0":
        raise ProtocolError("judge version mismatch")
    for key in ("challenge_id", "campaign_token"):
        value = _string(message, key)
        if _PUBLIC_ID.fullmatch(value) is None:
            raise ProtocolError(f"judge field {key} is not a valid public identifier")
    if _string(message, "campaign_token") != expected_campaign_token:
        raise ProtocolError("judge response campaign token mismatch")
    recorded = _boolean(message, "submission_recorded")
    accepted = _boolean(message, "accepted")
    if accepted and not recorded:
        raise ProtocolError("judge cannot accept an unrecorded submission")


def _require_exact_fields(
    value: Mapping[str, object],
    expected: set[str] | frozenset[str],
    role: str,
) -> None:
    actual = set(value)
    missing = set(expected).difference(actual)
    unexpected = actual.difference(expected)
    if missing or unexpected:
        raise ProtocolError(
            f"{role} fields do not match the public schema: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )


def _require_bounded_string(
    value: Mapping[str, object],
    key: str,
    minimum: int,
    maximum: int,
) -> str:
    item = _string(value, key)
    if not minimum <= len(item) <= maximum:
        raise ProtocolError(f"field {key} has an invalid string length")
    return item


def _require_integer_range(
    value: Mapping[str, object],
    key: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    item = _integer(value, key)
    if item < minimum or (maximum is not None and item > maximum):
        raise ProtocolError(f"field {key} is outside its public range")
    return item


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


def _encode_public_memory(memory: Mapping[int, int] | None) -> dict[str, int]:
    if memory is None:
        return {}
    entries: list[tuple[int, int]] = []
    for address, value in memory.items():
        if not isinstance(address, int) or isinstance(address, bool) or not 0 <= address <= 255:
            raise ValueError("public memory addresses must be integers in 0..255")
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 65_535:
            raise ValueError("public memory values must be integers in 0..65535")
        entries.append((address, value))
    encoded: dict[str, int] = {}
    for address, value in sorted(entries):
        encoded[str(address)] = value
    return encoded
