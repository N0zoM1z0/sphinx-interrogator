# Implementation status

This file is a concise, living project checkpoint. The active ExecPlan contains the detailed history.

## Overall state

- **Specification/design package:** complete.
- **Executable system:** M0–M9 are implemented through deterministic recovery, grammar-guided CEGIS, robust bounded/statistical evidence handling, the published standard benchmark, active state-learning abstractions, relation-aware witness reduction, and release artifact packaging.
- **Implementation:** complete through M9; release evidence is committed locally and not pushed.
- **Current active plan:** `agent/plans/0001-full-system.md`.
- **Last updated:** 2026-07-16.

## Current milestone

Milestone 9 complete — relation-aware best-first witness reduction now preserves
typed/certified relation instances, architectural and fault-free prechecks, strict
lexicographic cost improvement, and finite public-model implication/equivalence
predicates without using hidden challenge state. The release includes minimized
witness artifacts for all ten enabled relation families, schema-covered reducer
reports, CLI `doctor/reduce/benchmark` coverage, release notes, a review checklist,
and an ignored run manifest with artifact hashes.

## Verification dashboard

| Check | Last result | Evidence |
|---|---|---|
| `just fmt` | pass | Rustfmt and Ruff; 2026-07-16 |
| `just lint` | pass | Clippy `-D warnings`, Ruff, strict mypy; 2026-07-16 |
| `just test` | pass | 44 Rust + 162 Python, including M9 reducer and CLI tests; 2026-07-16 |
| `just schema-check` | pass | All public fixtures, including tutorial, standard recovery, standard benchmark, and reduced-witness reports |
| `just docs-check` | pass | Repository-relative Markdown links valid; 2026-07-16 |
| `just verify-formal` | pass | Z3 `unsat` x3; TLC 70,557 generated/2,276 distinct states; 131,072-cell exhaustive check; mutation rejected |
| `just demo-tutorial` | pass | `unique_exact`, secret `e905`, judge accepted, 16 logical/32 physical executions; verified idempotent rerun |
| `just boundary-audit` | pass | System B public-boundary audit; binary SHA-256 `628cf0df3268710b9109e328ea72c854c3a506f4c2159837638e9645d2f64e4b` |
| tutorial reference matrix | pass | 100/100 exact and accepted; median/max 16 logical families |
| tutorial off-fault matrix | pass | 100/100 inconclusive, zero exact declarations, zero judge submissions |
| M6 selector calibration | pass | mean worst bucket 3.00 vs random 7.15; strict win on 19/20 public model subsets |
| standard benchmark | pass | `runs/standard-benchmark-v1/standard-benchmark-report.json`: 600 campaigns, targets met, full/reference 100/100 exact, off 100/100 inconclusive |
| standard profile audit | pass | `runs/standard-profile-audit-m7/standard-profile-audit.json`: max one-shot 1.5 bits, blind scan <=64 logical, oracle path 16 logical |
| state-learning evaluation | pass | `runs/state-learning-m8/state-learning-report.json`: no-learner accuracy 0.133; exact-history 1.0; AALpy learned-state 1.0 |
| reduced-witness report | pass | `runs/reduced-witnesses-m9/reduced-witnesses-report.json`: 10/10 enabled relation families minimized; artifact SHA-256 `3558973ce4005e6cf2e478ffa44c23b2531e395860bb08dd92e6ff395c418434` |
| release manifest | pass | `runs/release-m9/release-manifest.json`: 5 public artifacts hashed, no missing artifacts; pre-commit manifest SHA-256 `9b05653db1954b434a870295acda8dc5338b36b31ec5e92a873ffe6ca814667f` |

## Active blockers

None. Sphinx builds remain isolated to this repository and limited to two jobs. No
other Cargo process was active during the M9 Cargo-bearing command suite.

## Next concrete actions

1. Rerun `just release-manifest` after any new commit if a refreshed ignored manifest for that revision is needed.
2. Push/tag only if explicitly requested.

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
- Sequential statistical decisions are probabilistic soft evidence only; bounded hard equality still requires exact interval proof.
- Standard recovery reuses two stable public sessions (`standard-source` and `standard-follow_up`) so it stays below the protocol session limit while preserving hard-reset pairing.
- The M7 drained hard-reset grammar intentionally leaves `reference`, `weak`, and `signed` latent-equivalent; the off variant is the required negative control.
- Standard selector baselines are reported fairly: every reference selector mode reached 100/100 exact on the published seeds, so M7 does not claim a large selector gap for the frozen standard profile.
- State-learning membership queries are ordinary public macro words; model artifacts bind alphabet/discretizer versions and membership-cache digests.
- Learned-state constraints carry `state-model:<id>` provenance and are retracted by append-only state events after conformance counterexamples.
- `soft-history-contrast/v1` is enabled only as state-conditioned research evidence and cannot emit hard secret constraints by itself.
- Witness reduction is a public-model optimizer: accepted candidates must remain typed/certified, lower cost, and preserve configured finite public-family implication/equivalence; it never compares against the hidden challenge secret.
- The M9 release manifest is an ignored generated artifact under `runs/`; tracked source records schemas, scripts, docs, review checklist, and reproducible commands.
- The repository remains synthetic-only; no real-target adapters.

## How to update

After each milestone, record:

- current milestone and outcome;
- exact commands run and result;
- benchmark/recovery evidence paths;
- active blockers;
- material decisions with a link to the ExecPlan entry.
