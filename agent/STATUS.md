# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** M0–M5 are implemented through deterministic black-box tutorial recovery, one-shot judging, replay, and the blind fault-free negative control; M6–M9 research layers remain incomplete.
- **Implementation:** active; M4 is committed as `2a9af4a`, and the verified M5 checkpoint is ready to commit.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-16.

## Current milestone

Milestone 5 complete — the public-only tutorial campaign uses 16 certified relation
families and 32 physical executions to recover the 16-bit secret projection. Exact
status requires an alternative-secret exclusion query to return `unsat`; the one-shot
Rust judge is invoked only after that proof. The published reference matrix recovered
and judged 100/100 deterministic seeds, while 100/100 otherwise-identical off-fault
controls remained inconclusive and never invoked the judge. Accepted runs resume from
their manifest, hash-chained events, SQLite view, and schema-valid report without a
second submission. Milestone 6 grammar-guided CEGIS is now next.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-16 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-16 |
| `just test` | pass | 44 Rust + 128 Python, including 10 live process tests; 2026-07-16 |
| `just schema-check` | pass | All public fixtures, including campaign manifest 1.1 and recovery report 1.0 |
| `just verify-formal` | pass | Z3 `unsat` x3; TLC 70,557 generated/2,276 distinct states; 131,072-cell exhaustive check; mutation rejected |
| `just demo-tutorial` | pass | `unique_exact`, secret `e905`, judge accepted, 16 logical/32 physical executions; verified idempotent rerun |
| `just boundary-audit` | pass | System B public-boundary audit; binary SHA-256 `628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b` |
| tutorial reference matrix | pass | 100/100 exact and accepted; median/max 16 logical families |
| tutorial off-fault matrix | pass | 100/100 inconclusive, zero exact declarations, zero judge submissions |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None. Sphinx builds remain isolated to this repository and limited to two jobs. No
other Cargo process was active during the M5 command suite.

## Next concrete actions

1. Preserve the M5 implementation and evidence in a detailed English Git commit without pushing.
2. Implement M6 typed grammar skeletons, SMT hole filling, model-pair separation, deterministic committee scoring, and CEGIS refinement.
3. Prove M6 on tiny optimum/no-discriminator cases and through a live integration campaign without changing architecture or accepting fault-free false discriminators.
4. Continue into M7 robust noise calibration and the standard benchmark after the synthesis checkpoint passes all repository gates.

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
- Tutorial uniqueness is over the 16-bit secret projection, not the still-ambiguous latent fault member; three full models can share the one exact secret.
- Campaign manifest 1.1 binds the public challenge commitment, and SQLite migration 2 materializes the sole judge submission.
- The fixed tutorial schedule is intentionally deterministic: 16 logical relation families and 32 physical executions for every seed and both fault assignments.
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
