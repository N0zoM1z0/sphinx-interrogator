# Campaign persistence and hypotheses

## Authority order

An Interrogator run has four deliberately separate layers:

1. `manifest.json` freezes the public challenge/profile identity and challenge
   commitment, semantic version, seed, certificate policy, and budgets. Manifest
   version 1.1 added the commitment binding used by accepted-report resume. Readers
   retain strict support for version 1.0 inspection; an unbound version-1.0 run cannot
   be resumed as a bound challenge campaign.
2. `raw/` contains immutable, content-hashed public JSONL request/response pairs. The
   response is atomically written and `fsync`ed before protocol decoding or relation
   analysis.
3. `events.jsonl` is the authoritative append-only derived history. Stable event IDs
   make retries idempotent; a SHA-256 chain detects removal, reordering, or mutation.
4. `campaign.sqlite3` is a disposable materialized view. It can always be rebuilt from
   the event log and is never an independent source of truth.

The target's private challenge tree is outside this run directory and is never copied
into any of these layers.

## Crash and retry semantics

A stable physical `execution_id` is also used as its public protocol `request_id`.
Immediately after `VmClient` receives an execute response line, the recorder commits
the exact public request and response bytes. Only then does normal JSON/schema decoding
continue. If the process crashes after that commit, resume detects the raw record,
decodes it again, and appends/materializes the one stable execution event without
calling the target a second time.

Transport errors with no response produce neither a raw observation nor an oracle
decision. A malformed response may exist as raw diagnostic evidence, but cannot become
a typed execution event or solver constraint.

## Materialized graph

The version-1 SQLite migration materializes queries, balanced execution batches, raw
execution references, certificates, relation edges, decisions, constraints, candidate
snapshots, state-model versions, witnesses, and the active frontier. Foreign keys and
pre-append validation require every constraint to reference an existing relation,
certificate, and raw request IDs.

Migration version 2 adds the one-shot judge submission view. Judge output is appended
only after secret-projection uniqueness is proven; accepted report resume verifies the
challenge commitment, manifest, materialized digest, and exactly one judge event.

Frontier rows carry independent structural, relation, state, observation, partition,
and semantic keys plus TTL. Selection is ordered by score and then stable candidate ID.
An implication timeout returns `unknown`; it does not establish semantic novelty and
the candidate is deferred rather than appended.

## Constraint and solver persistence

The durable object is `constraint_ir.py` JSON, not a Z3 Python AST. The translator
preserves explicit bit-vector widths and signed/unsigned operators. Named assumptions
map unsat-core entries back to their constraint group, certificate, relation, and raw
request provenance.

Hard solving supports `sat|unsat|unknown`, exact blocking enumeration, diverse bounded
committees, labeled exact/sampled marginals, implication, and an explicit
alternative-model uniqueness query. A result is unique only when excluding the chosen
secret projection is `unsat`. Constraint groups can be quarantined, reactivated, or
retracted without deleting their append-only evidence. Grouped soft evidence is capped
and ranked with MaxSMT; statistical calibration of those weights remains M7.

## Inspection and replay

`sphinx-interrogate inspect --run RUN` prints the basic deterministic materialized
report. `sphinx-interrogate replay --run RUN` records the current view digest, rebuilds
SQLite solely from `events.jsonl`, and fails unless the digest is identical.
