"""Deterministic paired schedules and write-ahead public execution harnesses."""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from sphinx_interrogator.model import ExecutionResult
from sphinx_interrogator.persistence import CampaignRepository, PersistenceError
from sphinx_interrogator.protocol import VmClient, decode_execute_response


@dataclass(frozen=True, slots=True)
class ScheduledArm:
    """One balanced physical execution with explicit correlation provenance."""

    position: int
    pair_id: str
    arm: str
    repetition: int
    correlation_group: str

    def __post_init__(self) -> None:
        if self.position < 0 or self.repetition < 0 or self.arm not in {"source", "follow_up"}:
            raise ValueError("scheduled arm contains an invalid position/repetition/arm")
        if not self.pair_id or not self.correlation_group:
            raise ValueError("scheduled arm IDs must not be empty")

    def to_data(self) -> dict[str, object]:
        """Return stable schedule data."""
        return {
            "position": self.position,
            "pair_id": self.pair_id,
            "arm": self.arm,
            "repetition": self.repetition,
            "correlation_group": self.correlation_group,
        }


def balanced_pair_schedule(
    pair_ids: Sequence[str],
    *,
    repetitions: int,
    seed: int,
) -> tuple[ScheduledArm, ...]:
    """Randomize pair blocks and within-pair order while retaining exact balance."""
    if not pair_ids or len(set(pair_ids)) != len(pair_ids):
        raise ValueError("pair_ids must be nonempty and unique")
    if any(not pair_id for pair_id in pair_ids):
        raise ValueError("pair IDs must not be empty")
    if repetitions < 1 or seed < 0:
        raise ValueError("repetitions must be positive and seed nonnegative")
    generator = random.Random(seed)
    unpositioned: list[tuple[str, str, int, str]] = []
    for repetition in range(repetitions):
        blocks = []
        for pair_id in pair_ids:
            arms = ["source", "follow_up"]
            generator.shuffle(arms)
            correlation_group = f"pair:{pair_id}:repetition:{repetition}"
            blocks.append([(pair_id, arm, repetition, correlation_group) for arm in arms])
        generator.shuffle(blocks)
        unpositioned.extend(item for block in blocks for item in block)
    return tuple(
        ScheduledArm(position, pair_id, arm, repetition, correlation_group)
        for position, (pair_id, arm, repetition, correlation_group) in enumerate(unpositioned)
    )


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """Complete public inputs for one stable logical physical execution."""

    execution_id: str
    query_id: str
    batch_id: str
    position: int
    program: str
    session_id: str
    reset: str
    logical_time: int
    registers: tuple[int, ...] = ()
    memory: Mapping[int, int] | None = None
    execution_seed_id: str | None = None

    def __post_init__(self) -> None:
        if not self.execution_id or not self.query_id or not self.batch_id or not self.session_id:
            raise ValueError("execution/query/batch/session IDs must not be empty")
        if self.position < 0 or self.logical_time < 0:
            raise ValueError("execution position/logical time must be nonnegative")
        if self.reset not in {"hard", "soft", "none"}:
            raise ValueError("unknown execution reset policy")


class ExecutionClient(Protocol):
    """Public client surface shared by the subprocess client and deterministic fake."""

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
        """Execute through the public protocol."""
        ...


class RepositoryWireRecorder:
    """Persist only execute exchanges immediately after the public line is read."""

    def __init__(
        self,
        repository: CampaignRepository,
        *,
        after_raw: Callable[[], None] | None = None,
    ) -> None:
        self._repository = repository
        self._after_raw = after_raw

    def __call__(self, request_line: str, response_line: str) -> None:
        """Write raw execute bytes before the protocol layer parses the response."""
        try:
            request: object = json.loads(request_line)
        except json.JSONDecodeError as error:
            raise PersistenceError("client generated an invalid raw request") from error
        if not isinstance(request, dict):
            raise PersistenceError("client generated a non-object raw request")
        request_data = cast("dict[str, object]", request)
        if request_data.get("kind") != "execute":
            return
        request_id = request_data.get("request_id")
        if not isinstance(request_id, str):
            raise PersistenceError("execute request is missing its public request ID")
        self._repository.raw.write(request_id, request_line, response_line)
        if self._after_raw is not None:
            self._after_raw()


class DurableExecutionHarness:
    """Resume physical executions from raw bytes and commit each derived event once."""

    def __init__(self, repository: CampaignRepository, client: ExecutionClient) -> None:
        self.repository = repository
        self.client = client

    @classmethod
    def connect_unix(
        cls,
        repository: CampaignRepository,
        *,
        socket_path: str | Path,
        timeout_seconds: float = 5.0,
        after_raw: Callable[[], None] | None = None,
    ) -> tuple[DurableExecutionHarness, VmClient]:
        """Connect to a broker-launched VM with write-ahead recording installed."""
        recorder = RepositoryWireRecorder(repository, after_raw=after_raw)
        client = VmClient.connect_unix(
            socket_path,
            timeout_seconds=timeout_seconds,
            exchange_recorder=recorder,
        )
        return cls(repository, client), client

    def execute(self, spec: ExecutionSpec) -> ExecutionResult:
        """Return a recorded result or execute once and require its raw write-ahead."""
        raw = self.repository.raw.get(spec.execution_id)
        if raw is None:
            result = self.client.execute(
                spec.program,
                session_id=spec.session_id,
                logical_batch_id=spec.batch_id,
                reset=spec.reset,
                registers=spec.registers,
                memory=spec.memory,
                execution_seed_id=spec.execution_seed_id,
                request_id=spec.execution_id,
            )
            raw = self.repository.raw.get(spec.execution_id)
            if raw is None:
                raise PersistenceError(
                    "execution client returned without write-ahead raw transcript"
                )
            if result.request_id != spec.execution_id:
                raise PersistenceError("execution result does not match its stable ID")
        result = decode_execute_response(
            raw.response_line,
            expected_request_id=spec.execution_id,
        )
        self.repository.commit_raw_execution(
            execution_id=spec.execution_id,
            query_id=spec.query_id,
            batch_id=spec.batch_id,
            position=spec.position,
            logical_time=spec.logical_time,
        )
        return result


class FakeEndpoint:
    """Deterministic public endpoint for harness unit tests without subprocesses."""

    def __init__(
        self,
        recorder: Callable[[str, str], None],
        *,
        buckets: Sequence[int],
        bucket_width: int = 1,
    ) -> None:
        if not buckets or bucket_width < 1:
            raise ValueError("fake endpoint needs buckets and a positive width")
        self._recorder = recorder
        self._buckets = tuple(buckets)
        self._bucket_width = bucket_width
        self.calls: list[str] = []

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
        """Emit one schema-shaped public response and invoke the real recorder path."""
        del registers, memory, execution_seed_id
        if request_id is None:
            raise ValueError("fake durable endpoint requires a stable request ID")
        index = len(self.calls)
        if index >= len(self._buckets):
            raise RuntimeError("fake endpoint response sequence exhausted")
        self.calls.append(request_id)
        request = {
            "protocol_version": "1.0",
            "request_id": request_id,
            "kind": "execute",
            "session_id": session_id,
            "reset": reset,
            "program": program,
            "public_input": {"registers": [], "memory": {}},
            "logical_batch_id": logical_batch_id,
        }
        response = _fake_response(
            request_id,
            session_id,
            self._buckets[index],
            self._bucket_width,
        )
        request_line = json.dumps(request, sort_keys=True, separators=(",", ":"))
        response_line = json.dumps(response, sort_keys=True, separators=(",", ":"))
        self._recorder(request_line, response_line)
        return decode_execute_response(response_line, expected_request_id=request_id)


def _fake_response(
    request_id: str,
    session_id: str,
    bucket: int,
    bucket_width: int,
) -> dict[str, object]:
    return {
        "protocol_version": "1.0",
        "request_id": request_id,
        "kind": "execute_result",
        "ok": True,
        "session_id": session_id,
        "status": "halted",
        "public_digest": "0000000000000000",
        "observation": {
            "cycle_bucket": bucket,
            "bucket_width": bucket_width,
            "samples_in_vm": 1,
        },
        "public_metrics": {"retired_instructions": 1, "static_cycles": 1},
        "budget": {
            "physical_executions_used": 1,
            "physical_executions_remaining": 999,
            "logical_queries_used": 1,
            "logical_queries_remaining": 999,
            "hard_resets_used": 1,
            "hard_resets_remaining": 999,
        },
        "semantics": {"server_version": "0.1.0", "profile_version": "0.1.0"},
    }
