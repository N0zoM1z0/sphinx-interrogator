# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** M0–M4 are implemented through durable black-box execution, certified constraints, replayable campaign state, and exact Z3 hypotheses; recovery and later research layers remain incomplete.
- **Implementation:** active; M3 is committed as `40d63d7`, and the verified M4 checkpoint is ready to commit.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-16.

## Current milestone

Milestone 4 checkpoint — public response lines are write-ahead persisted before decode,
derived events form an idempotent hash chain, and a versioned SQLite view rebuilds from
that log. The durable graph covers queries, balanced batches, executions, certificates,
relations, decisions, constraints, snapshots, state models, witnesses, and TTL frontier
candidates. Project IR translates to Z3 with named cores, exact enumeration,
alternative-model uniqueness, implication, quarantine/retraction, diverse models, and
capped grouped MaxSMT. Formal closure remains deferred because `just demo-tutorial` is
the real M5 recovery flow and still exits 1.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-16 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-16 |
| `just test` | pass | 44 Rust + 125 Python, including 8 live process tests; 2026-07-16 |
| `just schema-check` | pass | Relation/constraint/expression-IR schemas, public protocol/challenge/judge fixtures, and profiles |
| `just verify-formal` | pass | Z3 `unsat` x3; TLC 70,557 generated/2,276 distinct states; 131,072-cell exhaustive check; mutation rejected |
| `just demo-tutorial` | fail as specified TODO | exit 1: generate/recover/judge/report belongs to M5 |
| `just boundary-audit` | pass | M4 System B modules plus typed public process responses; binary SHA-256 starts `628cf0df` |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None. Sphinx builds remain isolated to this repository and limited to two jobs. No
other Cargo process was active during the M4 command suite.

## Next concrete actions

1. Preserve the M4 implementation and evidence in a detailed English Git commit without pushing.
2. Replace the M5 tutorial TODO with a generated-challenge, persisted relation campaign, exact uniqueness proof, one-shot judge, and report.
3. Run every required tutorial seed and the fault-free negative-control matrix without selector access to private state.
4. Update CLI/docs/schemas and close the deferred M1–M4 tutorial gate only after the real flow passes.

## Decision summary

- Rust target and Python interrogator remain separate processes.
- JSON Lines plus JSON Schema is the public boundary.
- Tutorial/standard use exact known fault family; research adds persistent state.
- Exact uniqueness requires an alternative-model unsatisfiability check.
- CALL/JMP/conditional branches are forward-only; bounded `LOOP` is the sole backward edge.
- Canonical text, canonical typed-AST JSON, and SHA-256 are shared only through public fixtures.
- Encoded gas is explicitly not a dynamic path bound; runtime gas is authoritative.
- Public `standard.toml` and `fault_free.toml` are byte-identical; fault assignment exists only in private challenge configuration.
- All fault variants share one microcode and hidden transition; only the signed timing policy differs.
- Challenge generation roots are logged privately, and the commitment binds every runtime-private field.
- Relation extractors enumerate `(secret projection, latent fault variant)` models; public profiles never authorize assuming a private fault assignment.
- Quantization and bounded jitter are eliminated as integer feasibility sets; an interval crossing zero is inconclusive, never exact equality.
- Certificate artifact digests bind semantics, scope, claims, preconditions, and limitations and are recomputed on strict load.
- Solver-independent expression persistence uses explicit Boolean/integer/finite/bit-vector sorts; no Z3 object enters campaign storage.
- Raw public wire bytes precede every analysis event; stable execution IDs make crash resume idempotent.
- `events.jsonl` is authoritative and hash-chained; SQLite is a versioned disposable materialized view.
- Exact recovery requires an explicit alternative-model `unsat`; `unknown` never means unique, implied, or novel.
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
