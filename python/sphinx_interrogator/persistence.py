"""Crash-safe campaign manifests, raw transcripts, events, and SQLite views."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sphinx_interrogator.certificates import ProofMethod

_EVENT_VERSION = "1.0"
_MANIFEST_VERSION = "1.0"
_RAW_VERSION = "1.0"
_DATABASE_VERSION = 1
_MATERIALIZED_TABLES = (
    "events",
    "queries",
    "batches",
    "executions",
    "certificates",
    "relations",
    "decisions",
    "constraints",
    "candidate_snapshots",
    "state_models",
    "witnesses",
    "frontier",
)


class PersistenceError(RuntimeError):
    """Raised when durable campaign state is malformed or conflicting."""


@dataclass(frozen=True, slots=True)
class CampaignManifest:
    """Immutable public inputs needed to resume one campaign reproducibly."""

    campaign_id: str
    challenge_id: str
    profile_name: str
    semantic_version: str
    public_profile_sha256: str
    seed: int
    minimum_certificate_strength: str
    logical_query_budget: int
    physical_execution_budget: int
    hard_reset_budget: int

    def __post_init__(self) -> None:
        for name, value in (
            ("campaign_id", self.campaign_id),
            ("challenge_id", self.challenge_id),
            ("profile_name", self.profile_name),
            ("semantic_version", self.semantic_version),
            ("minimum_certificate_strength", self.minimum_certificate_strength),
        ):
            if not value:
                raise ValueError(f"{name} must not be empty")
        _require_digest(self.public_profile_sha256, "public_profile_sha256")
        try:
            ProofMethod(self.minimum_certificate_strength)
        except ValueError as error:
            raise ValueError("unknown minimum certificate strength") from error
        if self.seed < 0:
            raise ValueError("campaign seed must be nonnegative")
        if (
            min(
                self.logical_query_budget,
                self.physical_execution_budget,
                self.hard_reset_budget,
            )
            < 0
        ):
            raise ValueError("campaign budgets must be nonnegative")

    def to_data(self) -> dict[str, object]:
        """Return the strict public campaign manifest document."""
        return {
            "manifest_version": _MANIFEST_VERSION,
            "campaign_id": self.campaign_id,
            "challenge_id": self.challenge_id,
            "profile_name": self.profile_name,
            "semantic_version": self.semantic_version,
            "public_profile_sha256": self.public_profile_sha256,
            "seed": self.seed,
            "minimum_certificate_strength": self.minimum_certificate_strength,
            "budgets": {
                "logical_queries": self.logical_query_budget,
                "physical_executions": self.physical_execution_budget,
                "hard_resets": self.hard_reset_budget,
            },
        }

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> CampaignManifest:
        """Strictly decode a persisted campaign manifest."""
        _reject_extra(
            data,
            {
                "manifest_version",
                "campaign_id",
                "challenge_id",
                "profile_name",
                "semantic_version",
                "public_profile_sha256",
                "seed",
                "minimum_certificate_strength",
                "budgets",
            },
            "campaign manifest",
        )
        if _string(data, "manifest_version") != _MANIFEST_VERSION:
            raise PersistenceError("unsupported campaign manifest version")
        budgets = _mapping(data, "budgets")
        _reject_extra(
            budgets,
            {"logical_queries", "physical_executions", "hard_resets"},
            "campaign budgets",
        )
        return cls(
            campaign_id=_string(data, "campaign_id"),
            challenge_id=_string(data, "challenge_id"),
            profile_name=_string(data, "profile_name"),
            semantic_version=_string(data, "semantic_version"),
            public_profile_sha256=_string(data, "public_profile_sha256"),
            seed=_integer(data, "seed"),
            minimum_certificate_strength=_string(data, "minimum_certificate_strength"),
            logical_query_budget=_integer(budgets, "logical_queries"),
            physical_execution_budget=_integer(budgets, "physical_executions"),
            hard_reset_budget=_integer(budgets, "hard_resets"),
        )


@dataclass(frozen=True, slots=True)
class CampaignEvent:
    """One hash-chained append-only derived campaign event."""

    sequence: int
    event_id: str
    kind: str
    logical_time: int
    payload: Mapping[str, object]
    previous_hash: str
    event_hash: str

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.logical_time < 0:
            raise PersistenceError("event sequence/logical time must be nonnegative")
        if not self.event_id or not self.kind:
            raise PersistenceError("event ID and kind must not be empty")
        if self.sequence == 0:
            if self.previous_hash != "0" * 64:
                raise PersistenceError("first event must use the zero previous hash")
        else:
            _require_digest(self.previous_hash, "previous_hash")
        _require_digest(self.event_hash, "event_hash")
        if self.event_hash != _event_hash(self.unsigned_data()):
            raise PersistenceError("event hash does not match its contents")

    def unsigned_data(self) -> dict[str, object]:
        """Return fields covered by the event hash."""
        return {
            "event_version": _EVENT_VERSION,
            "sequence": self.sequence,
            "event_id": self.event_id,
            "kind": self.kind,
            "logical_time": self.logical_time,
            "payload": dict(self.payload),
            "previous_hash": self.previous_hash,
        }

    def to_data(self) -> dict[str, object]:
        """Return the canonical JSON event object."""
        return {**self.unsigned_data(), "event_hash": self.event_hash}

    @classmethod
    def build(
        cls,
        *,
        sequence: int,
        event_id: str,
        kind: str,
        logical_time: int,
        payload: Mapping[str, object],
        previous_hash: str,
    ) -> CampaignEvent:
        """Construct and hash one event."""
        unsigned = {
            "event_version": _EVENT_VERSION,
            "sequence": sequence,
            "event_id": event_id,
            "kind": kind,
            "logical_time": logical_time,
            "payload": dict(payload),
            "previous_hash": previous_hash,
        }
        return cls(
            sequence,
            event_id,
            kind,
            logical_time,
            dict(payload),
            previous_hash,
            _event_hash(unsigned),
        )

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> CampaignEvent:
        """Strictly decode and verify one event object."""
        _reject_extra(
            data,
            {
                "event_version",
                "sequence",
                "event_id",
                "kind",
                "logical_time",
                "payload",
                "previous_hash",
                "event_hash",
            },
            "campaign event",
        )
        if _string(data, "event_version") != _EVENT_VERSION:
            raise PersistenceError("unsupported campaign event version")
        return cls(
            sequence=_integer(data, "sequence"),
            event_id=_string(data, "event_id"),
            kind=_string(data, "kind"),
            logical_time=_integer(data, "logical_time"),
            payload=dict(_mapping(data, "payload")),
            previous_hash=_string(data, "previous_hash"),
            event_hash=_string(data, "event_hash"),
        )


class EventLog:
    """Single-writer hash-chained JSONL event log with idempotent stable IDs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events = list(self._read_all())
        self._by_id = {event.event_id: event for event in self._events}

    def __iter__(self) -> Iterator[CampaignEvent]:
        return iter(tuple(self._events))

    def __len__(self) -> int:
        return len(self._events)

    def get(self, event_id: str) -> CampaignEvent | None:
        """Return an event by stable ID without mutating the log."""
        return self._by_id.get(event_id)

    def preview(
        self,
        *,
        event_id: str,
        kind: str,
        payload: Mapping[str, object],
        logical_time: int,
    ) -> CampaignEvent:
        """Build the next event for pre-append materialization validation."""
        previous_hash = self._events[-1].event_hash if self._events else "0" * 64
        return CampaignEvent.build(
            sequence=len(self._events),
            event_id=event_id,
            kind=kind,
            logical_time=logical_time,
            payload=payload,
            previous_hash=previous_hash,
        )

    def append(
        self,
        *,
        event_id: str,
        kind: str,
        payload: Mapping[str, object],
        logical_time: int,
    ) -> CampaignEvent:
        """Append once, or return an identical event already committed."""
        existing = self._by_id.get(event_id)
        if existing is not None:
            if (
                existing.kind != kind
                or existing.logical_time != logical_time
                or dict(existing.payload) != dict(payload)
            ):
                raise PersistenceError(f"event ID {event_id} was reused with different data")
            return existing
        event = self.preview(
            event_id=event_id,
            kind=kind,
            payload=payload,
            logical_time=logical_time,
        )
        line = _canonical_json(event.to_data()).encode("utf-8") + b"\n"
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            written = os.write(descriptor, line)
            if written != len(line):
                raise PersistenceError("short write while appending campaign event")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(self.path.parent)
        self._events.append(event)
        self._by_id[event_id] = event
        return event

    def _read_all(self) -> Iterator[CampaignEvent]:
        if not self.path.exists():
            return
        expected_previous = "0" * 64
        with self.path.open("rb") as handle:
            for expected_sequence, raw_line in enumerate(handle):
                if not raw_line.endswith(b"\n"):
                    raise PersistenceError("campaign event log has a partial final record")
                try:
                    decoded: object = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise PersistenceError("campaign event log contains invalid JSON") from error
                if not isinstance(decoded, dict):
                    raise PersistenceError("campaign event must be a JSON object")
                event = CampaignEvent.from_data(cast("dict[str, object]", decoded))
                if event.sequence != expected_sequence:
                    raise PersistenceError("campaign event sequence is not contiguous")
                if event.previous_hash != expected_previous:
                    raise PersistenceError("campaign event hash chain is broken")
                expected_previous = event.event_hash
                yield event


@dataclass(frozen=True, slots=True)
class RawExchange:
    """Immutable exact public request/response lines persisted before analysis."""

    execution_id: str
    request_line: str
    response_line: str
    content_sha256: str

    def __post_init__(self) -> None:
        if not self.execution_id:
            raise PersistenceError("raw execution ID must not be empty")
        _require_digest(self.content_sha256, "raw content_sha256")
        if self.content_sha256 != _raw_digest(
            self.execution_id, self.request_line, self.response_line
        ):
            raise PersistenceError("raw exchange digest does not match its contents")

    def to_data(self) -> dict[str, object]:
        """Return the exact wire transcript wrapper."""
        return {
            "raw_version": _RAW_VERSION,
            "execution_id": self.execution_id,
            "request_line": self.request_line,
            "response_line": self.response_line,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> RawExchange:
        """Strictly decode and hash-check a raw transcript."""
        _reject_extra(
            data,
            {
                "raw_version",
                "execution_id",
                "request_line",
                "response_line",
                "content_sha256",
            },
            "raw exchange",
        )
        if _string(data, "raw_version") != _RAW_VERSION:
            raise PersistenceError("unsupported raw transcript version")
        return cls(
            _string(data, "execution_id"),
            _string(data, "request_line"),
            _string(data, "response_line"),
            _string(data, "content_sha256"),
        )


class RawTranscriptStore:
    """Atomically persist exact public exchanges under content-checked stable IDs."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, execution_id: str) -> RawExchange | None:
        """Load an exchange by logical execution ID."""
        path = self._path(execution_id)
        if not path.exists():
            return None
        try:
            decoded: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersistenceError(f"cannot read raw exchange {execution_id}") from error
        if not isinstance(decoded, dict):
            raise PersistenceError("raw exchange document must be an object")
        exchange = RawExchange.from_data(cast("dict[str, object]", decoded))
        if exchange.execution_id != execution_id:
            raise PersistenceError("raw exchange path/ID mismatch")
        return exchange

    def write(self, execution_id: str, request_line: str, response_line: str) -> RawExchange:
        """Atomically commit raw lines before any decision/constraint analysis."""
        exchange = RawExchange(
            execution_id,
            request_line,
            response_line,
            _raw_digest(execution_id, request_line, response_line),
        )
        existing = self.get(execution_id)
        if existing is not None:
            if existing != exchange:
                raise PersistenceError(
                    f"raw execution ID {execution_id} was reused with different bytes"
                )
            return existing
        path = self._path(execution_id)
        temporary = path.with_suffix(f".tmp-{os.getpid()}")
        encoded = (_canonical_json(exchange.to_data()) + "\n").encode("utf-8")
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        failed = False
        try:
            written = os.write(descriptor, encoded)
            if written != len(encoded):
                raise PersistenceError("short write while persisting raw exchange")
            os.fsync(descriptor)
        except BaseException:
            failed = True
            raise
        finally:
            os.close(descriptor)
            if failed:
                temporary.unlink(missing_ok=True)
        os.replace(temporary, path)
        _fsync_directory(self.directory)
        return exchange

    def _path(self, execution_id: str) -> Path:
        digest = hashlib.sha256(execution_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"


class CampaignDatabase:
    """Disposable SQLite materialized view rebuilt deterministically from events."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self) -> None:
        """Close the SQLite view."""
        self.connection.close()

    def apply(self, event: CampaignEvent) -> None:
        """Materialize one event transactionally and idempotently."""
        with self.connection:
            inserted = self.connection.execute(
                """
                INSERT OR IGNORE INTO events
                    (sequence, event_id, kind, logical_time, payload_json, event_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.sequence,
                    event.event_id,
                    event.kind,
                    event.logical_time,
                    _canonical_json(dict(event.payload)),
                    event.event_hash,
                ),
            )
            if inserted.rowcount == 0:
                return
            self._apply_payload(event)

    def apply_all(self, events: Iterator[CampaignEvent]) -> None:
        """Apply an ordered event stream."""
        for event in events:
            self.apply(event)

    def validate(self, event: CampaignEvent) -> None:
        """Check payload shape and references in a rollback-only savepoint."""
        self.connection.execute("SAVEPOINT validate_event")
        try:
            self._apply_payload(event)
        except (PersistenceError, sqlite3.DatabaseError) as error:
            self.connection.execute("ROLLBACK TO validate_event")
            self.connection.execute("RELEASE validate_event")
            if isinstance(error, PersistenceError):
                raise
            raise PersistenceError(f"event {event.event_id} violates database contracts") from error
        self.connection.execute("ROLLBACK TO validate_event")
        self.connection.execute("RELEASE validate_event")

    def table_count(self, table: str) -> int:
        """Return a count from one known materialized table."""
        if table not in _MATERIALIZED_TABLES:
            raise ValueError(f"unknown materialized table {table}")
        row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        assert row is not None
        return cast("int", row["count"])

    def active_constraint_ids(self) -> tuple[str, ...]:
        """Return active hard/soft constraint IDs deterministically."""
        rows = self.connection.execute(
            "SELECT constraint_id FROM constraints WHERE active = 1 ORDER BY constraint_id"
        )
        return tuple(cast("str", row["constraint_id"]) for row in rows)

    def active_frontier(self, logical_time: int) -> tuple[sqlite3.Row, ...]:
        """Return unexpired frontier rows in deterministic selection order."""
        rows = self.connection.execute(
            """
            SELECT * FROM frontier
            WHERE active = 1 AND (expires_after IS NULL OR expires_after >= ?)
            ORDER BY score DESC, candidate_id ASC
            """,
            (logical_time,),
        )
        return tuple(rows)

    def digest(self) -> str:
        """Hash all materialized rows in stable table/row order for replay checks."""
        materialized: dict[str, list[dict[str, object]]] = {}
        for table in _MATERIALIZED_TABLES:
            rows = self.connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            materialized[table] = [dict(row) for row in rows]
        return hashlib.sha256(_canonical_json(materialized).encode("utf-8")).hexdigest()

    def _migrate(self) -> None:
        version = cast("int", self.connection.execute("PRAGMA user_version").fetchone()[0])
        if version > _DATABASE_VERSION:
            raise PersistenceError(f"unsupported future database version {version}")
        if version == 0:
            with self.connection:
                self.connection.executescript(_SCHEMA_V1)
                self.connection.execute(f"PRAGMA user_version = {_DATABASE_VERSION}")
        version = cast("int", self.connection.execute("PRAGMA user_version").fetchone()[0])
        if version != _DATABASE_VERSION:
            raise PersistenceError(f"database migration stopped at version {version}")

    def _apply_payload(self, event: CampaignEvent) -> None:
        payload = event.payload
        if event.kind == "query_created":
            self.connection.execute(
                "INSERT INTO queries VALUES (?, ?, ?, ?, ?)",
                (
                    _string(payload, "query_id"),
                    _string(payload, "program_sha256"),
                    _string(payload, "program_text"),
                    event.logical_time,
                    _optional_integer(payload, "expires_after"),
                ),
            )
        elif event.kind == "batch_scheduled":
            self.connection.execute(
                "INSERT INTO batches VALUES (?, ?, ?, ?, ?)",
                (
                    _string(payload, "batch_id"),
                    _integer(payload, "seed"),
                    _canonical_json(_list(payload, "schedule")),
                    _string(payload, "status"),
                    event.logical_time,
                ),
            )
        elif event.kind == "execution_recorded":
            self.connection.execute(
                "INSERT INTO executions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    _string(payload, "execution_id"),
                    _string(payload, "query_id"),
                    _string(payload, "batch_id"),
                    _integer(payload, "position"),
                    _string(payload, "request_id"),
                    _string(payload, "raw_digest"),
                    _canonical_json(_mapping(payload, "response")),
                ),
            )
        elif event.kind == "certificate_registered":
            self.connection.execute(
                "INSERT INTO certificates VALUES (?, ?)",
                (
                    _string(payload, "certificate_id"),
                    _canonical_json(_mapping(payload, "certificate")),
                ),
            )
        elif event.kind == "relation_recorded":
            self.connection.execute(
                "INSERT INTO relations VALUES (?, ?, ?, ?)",
                (
                    _string(payload, "relation_instance_id"),
                    _string(payload, "relation_id"),
                    _string(payload, "certificate_id"),
                    _canonical_json(_mapping(payload, "relation")),
                ),
            )
        elif event.kind == "decision_recorded":
            self.connection.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?)",
                (
                    _string(payload, "decision_id"),
                    _string(payload, "relation_instance_id"),
                    _string(payload, "kind"),
                    _canonical_json(_mapping(payload, "decision")),
                ),
            )
        elif event.kind == "constraint_added":
            source_request_ids = _string_list(payload, "source_request_ids")
            known = {
                cast("str", row["request_id"])
                for row in self.connection.execute(
                    "SELECT request_id FROM executions WHERE request_id IN ({})".format(
                        ",".join("?" for _ in source_request_ids)
                    ),
                    source_request_ids,
                )
            }
            if set(source_request_ids) != known:
                raise PersistenceError("constraint references a missing raw execution request")
            self.connection.execute(
                "INSERT INTO constraints VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active')",
                (
                    _string(payload, "constraint_id"),
                    _string(payload, "group_id"),
                    _string(payload, "relation_instance_id"),
                    _string(payload, "certificate_id"),
                    _canonical_json(source_request_ids),
                    _string(payload, "approximation"),
                    _canonical_json(_mapping(payload, "constraint")),
                ),
            )
        elif event.kind == "constraint_state_changed":
            state = _string(payload, "state")
            if state not in {"active", "quarantined", "retracted"}:
                raise PersistenceError("unknown constraint state")
            updated = self.connection.execute(
                "UPDATE constraints SET active = ?, state = ? WHERE constraint_id = ?",
                (
                    int(state == "active"),
                    state,
                    _string(payload, "constraint_id"),
                ),
            )
            if updated.rowcount != 1:
                raise PersistenceError("constraint state event references a missing constraint")
        elif event.kind == "candidate_snapshot":
            self.connection.execute(
                "INSERT INTO candidate_snapshots VALUES (?, ?, ?, ?, ?)",
                (
                    _string(payload, "snapshot_id"),
                    _string(payload, "solver_status"),
                    _optional_integer(payload, "exact_count"),
                    _optional_string(payload, "unique_secret_hex"),
                    _canonical_json(_mapping(payload, "snapshot")),
                ),
            )
        elif event.kind == "state_model_recorded":
            self.connection.execute(
                "INSERT INTO state_models VALUES (?, ?, ?, ?)",
                (
                    _string(payload, "state_model_id"),
                    _string(payload, "status"),
                    _string(payload, "artifact_digest"),
                    _canonical_json(_mapping(payload, "model")),
                ),
            )
        elif event.kind == "witness_recorded":
            self.connection.execute(
                "INSERT INTO witnesses VALUES (?, ?, ?, ?)",
                (
                    _string(payload, "witness_id"),
                    _string(payload, "relation_instance_id"),
                    _string(payload, "status"),
                    _canonical_json(_mapping(payload, "witness")),
                ),
            )
        elif event.kind == "frontier_candidate":
            self.connection.execute(
                "INSERT INTO frontier VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    _string(payload, "candidate_id"),
                    _string(payload, "structural_key"),
                    _string(payload, "relation_key"),
                    _string(payload, "state_key"),
                    _string(payload, "observation_key"),
                    _string(payload, "partition_key"),
                    _string(payload, "semantic_key"),
                    _number(payload, "score"),
                    event.logical_time,
                    _optional_integer(payload, "expires_after"),
                    _canonical_json(_mapping(payload, "candidate")),
                ),
            )
        else:
            raise PersistenceError(f"cannot materialize unknown event kind {event.kind}")


class CampaignRepository:
    """Own one immutable manifest, raw store, event log, and derived database."""

    def __init__(self, root: Path, manifest: CampaignManifest) -> None:
        self.root = root
        self.manifest = manifest
        self.raw = RawTranscriptStore(root / "raw")
        self.events = EventLog(root / "events.jsonl")
        self.database = CampaignDatabase(root / "campaign.sqlite3")
        self.recover()

    @classmethod
    def create(cls, root: Path, manifest: CampaignManifest) -> CampaignRepository:
        """Create or idempotently reopen a campaign with identical public inputs."""
        root.mkdir(parents=True, exist_ok=True)
        path = root / "manifest.json"
        if path.exists():
            loaded = cls._load_manifest(path)
            if loaded != manifest:
                raise PersistenceError("campaign manifest conflicts with existing run")
        else:
            _atomic_json_write(path, manifest.to_data())
        return cls(root, manifest)

    @classmethod
    def open(cls, root: Path) -> CampaignRepository:
        """Open and recover an existing campaign directory."""
        return cls(root, cls._load_manifest(root / "manifest.json"))

    def close(self) -> None:
        """Close the materialized database."""
        self.database.close()

    def append_event(
        self,
        *,
        event_id: str,
        kind: str,
        payload: Mapping[str, object],
        logical_time: int,
    ) -> CampaignEvent:
        """Write the authoritative event first, then update the disposable view."""
        existing = self.events.get(event_id)
        if existing is None:
            self.database.validate(
                self.events.preview(
                    event_id=event_id,
                    kind=kind,
                    payload=payload,
                    logical_time=logical_time,
                )
            )
        event = self.events.append(
            event_id=event_id,
            kind=kind,
            payload=payload,
            logical_time=logical_time,
        )
        self.database.apply(event)
        return event

    def recover(self) -> None:
        """Apply events that survived a crash after log append but before SQLite commit."""
        self.database.apply_all(iter(self.events))

    def rebuild(self) -> str:
        """Recreate the materialized database solely from the append-only log."""
        self.database.close()
        self.database.path.unlink(missing_ok=True)
        self.database = CampaignDatabase(self.root / "campaign.sqlite3")
        self.recover()
        return self.database.digest()

    def record_raw_execution(
        self,
        *,
        execution_id: str,
        query_id: str,
        batch_id: str,
        position: int,
        request_line: str,
        response_line: str,
        logical_time: int,
        after_raw: Callable[[], None] | None = None,
    ) -> RawExchange:
        """Write raw bytes, optionally crash, then commit one derived execution event."""
        exchange = self.raw.write(execution_id, request_line, response_line)
        if after_raw is not None:
            after_raw()
        self.commit_raw_execution(
            execution_id=execution_id,
            query_id=query_id,
            batch_id=batch_id,
            position=position,
            logical_time=logical_time,
        )
        return exchange

    def commit_raw_execution(
        self,
        *,
        execution_id: str,
        query_id: str,
        batch_id: str,
        position: int,
        logical_time: int,
    ) -> CampaignEvent:
        """Analyze only enough raw JSON to index an already durable public response."""
        exchange = self.raw.get(execution_id)
        if exchange is None:
            raise PersistenceError("cannot commit an execution before its raw transcript")
        request = _json_object(exchange.request_line, "raw request")
        response = _json_object(exchange.response_line, "raw response")
        request_id = _string(request, "request_id")
        if _string(response, "request_id") != request_id:
            raise PersistenceError("raw request/response correlation mismatch")
        return self.append_event(
            event_id=f"execution:{execution_id}",
            kind="execution_recorded",
            logical_time=logical_time,
            payload={
                "execution_id": execution_id,
                "query_id": query_id,
                "batch_id": batch_id,
                "position": position,
                "request_id": request_id,
                "raw_digest": exchange.content_sha256,
                "response": response,
            },
        )

    def report(self) -> dict[str, object]:
        """Return a deterministic basic campaign report derived from materialized state."""
        return {
            "report_version": "1.0",
            "campaign_id": self.manifest.campaign_id,
            "profile_name": self.manifest.profile_name,
            "seed": self.manifest.seed,
            "event_count": len(self.events),
            "query_count": self.database.table_count("queries"),
            "execution_count": self.database.table_count("executions"),
            "relation_count": self.database.table_count("relations"),
            "active_constraint_count": len(self.database.active_constraint_ids()),
            "candidate_snapshot_count": self.database.table_count("candidate_snapshots"),
            "materialized_digest": self.database.digest(),
        }

    @staticmethod
    def _load_manifest(path: Path) -> CampaignManifest:
        try:
            decoded: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersistenceError("cannot load campaign manifest") from error
        if not isinstance(decoded, dict):
            raise PersistenceError("campaign manifest must be an object")
        return CampaignManifest.from_data(cast("dict[str, object]", decoded))


_SCHEMA_V1 = """
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    logical_time INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE queries (
    query_id TEXT PRIMARY KEY,
    program_sha256 TEXT NOT NULL,
    program_text TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_after INTEGER
);
CREATE TABLE batches (
    batch_id TEXT PRIMARY KEY,
    seed INTEGER NOT NULL,
    schedule_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE executions (
    execution_id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL REFERENCES queries(query_id),
    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
    position INTEGER NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    raw_digest TEXT NOT NULL,
    response_json TEXT NOT NULL,
    UNIQUE(batch_id, position)
);
CREATE TABLE certificates (
    certificate_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL
);
CREATE TABLE relations (
    relation_instance_id TEXT PRIMARY KEY,
    relation_id TEXT NOT NULL,
    certificate_id TEXT NOT NULL REFERENCES certificates(certificate_id),
    data_json TEXT NOT NULL
);
CREATE TABLE decisions (
    decision_id TEXT PRIMARY KEY,
    relation_instance_id TEXT NOT NULL REFERENCES relations(relation_instance_id),
    kind TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE constraints (
    constraint_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    relation_instance_id TEXT NOT NULL REFERENCES relations(relation_instance_id),
    certificate_id TEXT NOT NULL REFERENCES certificates(certificate_id),
    source_request_ids_json TEXT NOT NULL,
    approximation TEXT NOT NULL,
    data_json TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1)),
    state TEXT NOT NULL CHECK(state IN ('active', 'quarantined', 'retracted'))
);
CREATE TABLE candidate_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    solver_status TEXT NOT NULL,
    exact_count INTEGER,
    unique_secret_hex TEXT,
    data_json TEXT NOT NULL
);
CREATE TABLE state_models (
    state_model_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    artifact_digest TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE witnesses (
    witness_id TEXT PRIMARY KEY,
    relation_instance_id TEXT NOT NULL REFERENCES relations(relation_instance_id),
    status TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE frontier (
    candidate_id TEXT PRIMARY KEY,
    structural_key TEXT NOT NULL,
    relation_key TEXT NOT NULL,
    state_key TEXT NOT NULL,
    observation_key TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    semantic_key TEXT NOT NULL,
    score REAL NOT NULL,
    created_at INTEGER NOT NULL,
    expires_after INTEGER,
    data_json TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1))
);
CREATE INDEX frontier_live ON frontier(active, expires_after, score, candidate_id);
"""


def _event_hash(data: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(dict(data)).encode("utf-8")).hexdigest()


def _raw_digest(execution_id: str, request_line: str, response_line: str) -> str:
    encoded = _canonical_json(
        {
            "execution_id": execution_id,
            "request_line": request_line,
            "response_line": response_line,
        }
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _atomic_json_write(path: Path, data: Mapping[str, object]) -> None:
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    encoded = (_canonical_json(dict(data)) + "\n").encode("utf-8")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    failed = False
    try:
        written = os.write(descriptor, encoded)
        if written != len(encoded):
            raise PersistenceError("short write while persisting JSON document")
        os.fsync(descriptor)
    except BaseException:
        failed = True
        raise
    finally:
        os.close(descriptor)
        if failed:
            temporary.unlink(missing_ok=True)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json_object(source: str, context: str) -> dict[str, object]:
    try:
        decoded: object = json.loads(source)
    except json.JSONDecodeError as error:
        raise PersistenceError(f"{context} is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise PersistenceError(f"{context} must be a JSON object")
    return cast("dict[str, object]", decoded)


def _require_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _reject_extra(data: Mapping[str, object], allowed: set[str], context: str) -> None:
    extras = sorted(set(data) - allowed)
    if extras:
        raise PersistenceError(f"{context} contains unknown fields: {', '.join(extras)}")


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise PersistenceError(f"{key} must be a string")
    return value


def _optional_string(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise PersistenceError(f"{key} must be a string or null")
    return value


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise PersistenceError(f"{key} must be an integer")
    return value


def _optional_integer(data: Mapping[str, object], key: str) -> int | None:
    value = data.get(key)
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise PersistenceError(f"{key} must be an integer or null")
    return value


def _number(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PersistenceError(f"{key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PersistenceError(f"{key} must be finite")
    return result


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise PersistenceError(f"{key} must be an object")
    return cast("dict[str, object]", value)


def _list(data: Mapping[str, object], key: str) -> list[object]:
    value = data.get(key)
    if not isinstance(value, list):
        raise PersistenceError(f"{key} must be a list")
    return cast("list[object]", value)


def _string_list(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = _list(data, key)
    if not values or any(not isinstance(value, str) for value in values):
        raise PersistenceError(f"{key} must be a nonempty string list")
    return tuple(cast("list[str]", values))
