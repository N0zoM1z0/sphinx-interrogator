# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** M0 boundary, M1 language/architecture, M2 target/challenge, and M3 certified stateless relations are implemented; durable campaign and later research layers remain incomplete.
- **Implementation:** active; M2 is committed as `f14b407`, and the verified M3 checkpoint is ready to commit.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-16.

## Current milestone

Milestone 3 checkpoint — Interrogator now has nine typed hard-reset relation templates,
strict artifact-bound certificates, interval normalization, exact/bounded finite-model
extractors, and a solver-independent typed expression IR. Extracted constraints retain
the latent private fault variant and every public-bucket-consistent bounded-noise model.
Reduced exhaustive and live Rust-process tests pass. `soft-history-contrast/v1` remains
an explicit M8 state-learning deliverable. Formal milestone closure remains deferred
with M1/M2 because `just demo-tutorial` is the real M5 recovery flow and still exits 1.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-16 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-16 |
| `just test` | pass | 44 Rust + 99 Python, including 7 live process tests; 2026-07-16 |
| `just schema-check` | pass | Relation/constraint/expression-IR schemas, public protocol/challenge/judge fixtures, and profiles |
| `just verify-formal` | pass | Z3 `unsat` x3; TLC 70,557 generated/2,276 distinct states; 131,072-cell exhaustive check; mutation rejected |
| `just demo-tutorial` | fail as specified TODO | exit 1: generate/recover/judge/report belongs to M5 |
| `just boundary-audit` | M2 pass | public artifacts/modes and typed live responses; binary SHA-256 starts `628cf0df` |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None. Sphinx builds remain isolated to this repository and limited to two jobs. No
other Cargo process was active during the M3 command suite.

## Next concrete actions

1. Preserve the M3 implementation and evidence in a detailed English Git commit without pushing.
2. Implement M4 write-ahead raw transcripts, append-only events, migrations, and resumable materialized views.
3. Translate the project constraint IR to Z3 with named assumptions, exact model enumeration, implication, uniqueness, and honest timeout handling.
4. Add crash/resume/replay, provenance, frontier/novelty, quarantine, and retraction tests before tutorial recovery.

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
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
