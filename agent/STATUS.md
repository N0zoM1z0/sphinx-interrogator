# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable scaffold:** present; intentionally incomplete.
- **Implementation:** not started in this archive.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-15.

## Current milestone

Milestone 0 — bootstrap and public protocol. A coding agent should first inspect the scaffold, run available checks, and update the active ExecPlan with actual environment evidence.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | not run by implementation agent | — |
| `just lint` | not run by implementation agent | — |
| `just test` | not run by implementation agent | — |
| `just schema-check` | scaffold validation pending | — |
| `just verify-formal` | scaffold validation pending | — |
| `just demo-tutorial` | intentionally not implemented | — |
| boundary audit | intentionally not implemented | — |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None known at design time. Toolchain/dependency availability must be checked locally.

## Next concrete actions

1. Run the scaffold checks and repair any packaging issues.
2. Complete schemas and a versioned `hello`/`execute` target-client round trip.
3. Implement typed DSL/architectural semantics and tests.
4. Continue through the active ExecPlan without waiting for routine confirmation.

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
