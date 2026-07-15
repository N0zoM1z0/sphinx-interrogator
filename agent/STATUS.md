# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** M0 boundary, M1 language/architecture, and the M2 target/challenge layer are implemented; later Interrogator research layers remain incomplete.
- **Implementation:** active; M1 is committed as `6f2b233`, and M2 is committed at the current `HEAD`.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-15.

## Current milestone

Milestone 2 checkpoint — SphinxVM now has explicit microcode, pure hidden-state
transitions, separate fault policies, seeded noise/quantization, strict public profiles,
private generated challenges, the challenge-backed server, and a one-shot judge. Rust
and independent Python models share only public golden vectors. All M2-specific
acceptance evidence passes. Formal milestone closure remains deferred with M1 because
the repository-wide semantic gate `just demo-tutorial` is the real M5 recovery flow and
still exits 1; no smoke-test substitute was introduced.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-15 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-15 |
| `just test` | pass | 44 Rust + 68 Python, including 6 live process tests; 2026-07-15 |
| `just schema-check` | pass | Draft 2020-12 schemas, fixtures, profiles; 2026-07-15 |
| `just verify-formal` | pass | Z3 `unsat` x3; TLC 70,557 generated/2,276 distinct states; 131,072-cell exhaustive check; mutation rejected |
| `just demo-tutorial` | fail as specified TODO | exit 1: generate/recover/judge/report belongs to M5 |
| `just boundary-audit` | M2 pass | public artifacts/modes and typed live responses; binary SHA-256 starts `628cf0df` |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None. Sphinx builds remain isolated to this repository and limited to two jobs. No
other Cargo process was active during the M2 command suites.

## Next concrete actions

1. Preserve the M2 implementation and evidence in a detailed English Git commit without pushing.
2. Implement the M3 typed relation/template/instance/certificate APIs and public normalizers.
3. Add every required core relation with architectural, fault-free, and extractor obligations.
4. Prove extractor soundness over reduced exhaustive domains before advancing to persistence/solver work.

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
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
