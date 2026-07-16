# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** M0–M6 are implemented through deterministic recovery and grammar-guided CEGIS experiment synthesis; M7–M9 noise, learning, reduction, and release layers remain incomplete.
- **Implementation:** active; M5 is committed as `666ae7d`, and the verified M6 checkpoint is ready to commit.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-16.

## Current milestone

Milestone 6 complete — two versioned typed skeletons enumerate finite hole domains and
lower only through certified relation constructors. Z3 fills holes against surviving
model pairs with bounded lexicographic resources; a deterministic diverse committee
scores worst bucket, conservative interval margin, executions/resets, AST cost, and a
canonical tie-break. Oversized buckets produce real counterexample-pair refinements.
Exact and sampled committees are labeled separately, solver `unknown` remains unknown,
and off-fault committees have no discriminator. Successful results cache on every
semantic input and persist all score/refinement components through the M4 frontier.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-16 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-16 |
| `just test` | pass | 44 Rust + 141 Python, including 11 live process tests; 2026-07-16 |
| `just schema-check` | pass | All public fixtures, including campaign manifest 1.1 and recovery report 1.0 |
| `just verify-formal` | pass | Z3 `unsat` x3; TLC 70,557 generated/2,276 distinct states; 131,072-cell exhaustive check; mutation rejected |
| `just demo-tutorial` | pass | `unique_exact`, secret `e905`, judge accepted, 16 logical/32 physical executions; verified idempotent rerun |
| `just boundary-audit` | pass | System B public-boundary audit; binary SHA-256 `628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b` |
| tutorial reference matrix | pass | 100/100 exact and accepted; median/max 16 logical families |
| tutorial off-fault matrix | pass | 100/100 inconclusive, zero exact declarations, zero judge submissions |
| M6 selector calibration | pass | mean worst bucket 3.00 vs random 7.15; strict win on 19/20 public model subsets |
| standard benchmark | intentionally not implemented | — |

## Active blockers

None. Sphinx builds remain isolated to this repository and limited to two jobs. No
other Cargo process was active during the M6 command suite.

## Next concrete actions

1. Preserve the M6 implementation and evidence in a detailed English Git commit without pushing.
2. Implement M7 balanced robust sampling, explicit sequential decisions, calibrated/capped grouped soft weights, and contradiction quarantine/repair.
3. Integrate bounded/statistical evidence with the CEGIS margin objective and run deterministic false-positive/inconclusive calibration.
4. Execute the published standard/reference and blind fault-free matrices, diagnose misses, and meet the declared acceptance thresholds without private selector access.

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
- M6 grammar assignments are typed relation ASTs; Z3 fills finite holes but never emits assembly text directly.
- Committee entropy is called exact only for complete finite enumeration; bounded diverse solver models are labeled a partition proxy.
- CEGIS objectives are lexicographic and deterministic: worst bucket, interval margin, executions, resets, static/AST cost, then canonical key.
- A synthesis timeout remains `unknown`, and off-fault secret hypotheses yield no discriminator.
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
