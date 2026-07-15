# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** M0 boundary and M1 language/architecture implemented; later research layers remain incomplete.
- **Implementation:** active; M0 is committed as `5daa8bf`, with the M1 code checkpoint ready.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-15.

## Current milestone

Milestone 1 — the complete probe DSL, validator, architectural semantics, canonical
cross-language representation, sparse public memory, and noninterference tests are
implemented. All M1-specific acceptance evidence passes. M1 is not yet declared
closed because the repository-wide semantic gate `just demo-tutorial` is intentionally
an M5 TODO and still exits 1; no smoke-test substitute was introduced.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-15 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-15 |
| `just test` | pass | 24 Rust + 62 Python, including 3 live process tests; 2026-07-15 |
| `just schema-check` | pass | Draft 2020-12 schemas, fixtures, profiles; 2026-07-15 |
| `just verify-formal` | scaffold pass | Z3: `unsat` x3; M2 concrete/model and TLC work remains |
| `just demo-tutorial` | fail as specified TODO | exit 1: generate/recover/judge/report belongs to M5 |
| `just boundary-audit` | M1 pass | typed live responses; binary SHA-256 starts `77112409` |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None. Sphinx builds remain isolated to this repository and limited to two jobs. No
other Cargo process was active during the final M1 command suite.

## Next concrete actions

1. Preserve the M1 implementation and evidence in a detailed English Git commit without pushing.
2. Split microcode, fault-free scheduling, faulty scheduling, noise, and reset state into distinct M2 modules/types.
3. Separate public profiles from private challenge configuration and add generated challenge/judge isolation.
4. Add concrete/model differential, reset, mutation, and private-boundary tests before the M2 checkpoint.

## Decision summary

- Rust target and Python interrogator remain separate processes.
- JSON Lines plus JSON Schema is the public boundary.
- Tutorial/standard use exact known fault family; research adds persistent state.
- Exact uniqueness requires an alternative-model unsatisfiability check.
- CALL/JMP/conditional branches are forward-only; bounded `LOOP` is the sole backward edge.
- Canonical text, canonical typed-AST JSON, and SHA-256 are shared only through public fixtures.
- Encoded gas is explicitly not a dynamic path bound; runtime gas is authoritative.
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
