# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable scaffold:** present; intentionally incomplete.
- **Implementation:** active; verified baseline committed as `ab30e28`.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-15.

## Current milestone

Milestone 1 — complete probe DSL, validator, and architectural semantics. Milestone M0
is complete with locked dependencies, fail-closed checks, bounded JSONL handling, and
real Rust/Python process tests.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-15 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-15 |
| `just test` | pass | 10 Rust + 18 Python, including 2 live process tests; 2026-07-15 |
| `just schema-check` | pass | Draft 2020-12 schemas, fixtures, profiles; 2026-07-15 |
| `just verify-formal` | scaffold pass | Z3: `unsat` x3; TLC/full semantic proof remains later work |
| `just demo-tutorial` | intentionally not implemented | — |
| `just boundary-audit` | initial M0 pass | typed live public responses and static import scan |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None. A separate OpenVM Cargo build is active; Sphinx builds are isolated to this
repository and limited to two jobs rather than interrupting that work.

## Next concrete actions

1. Implement the complete Rust version-1 AST, label-aware parser, validator, and canonical formatter.
2. Implement architectural state/step semantics for registers, memory, flags, control flow, stack, gas, and digest.
3. Bring the independent Python AST/parser to canonical text/hash parity through golden fixtures.
4. Add generated secret-independence and malformed-program tests, then commit M1 evidence.

## Decision summary

- Rust target and Python interrogator remain separate processes.
- JSON Lines plus JSON Schema is the public boundary.
- Tutorial/standard use exact known fault family; research adds persistent state.
- Exact uniqueness requires an alternative-model unsatisfiability check.
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
