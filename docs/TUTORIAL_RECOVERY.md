# Exact tutorial recovery

## Public assumptions

The tutorial flow accepts only the public version-1 tutorial contract: four identity
mapped nibble lanes, exact width-one observations, no jitter, hard reset, and semantic
version `0.1.0`. The concrete challenge fault member remains private. Interrogator
models `off`, `reference`, `weak`, and `signed` as one shared latent campaign variable.

Python reads only `public/challenge.json`, `public/profile.toml`, and typed process
responses. Challenge creation and the final judge are separate Rust CLI operations.
Neither selection nor solving reads the private challenge tree or compares candidates
with the generated secret.

## Deterministic selector

For each lane and each epoch, the campaign uses token zero and two certified
`anchor-switch/v1` families:

```text
(anchor 0, anchor 1)
(anchor 2, anchor 3)
```

Padding is `(lane XOR epoch) mod 4`, which activates the documented public guard after
hard reset. In an active non-off fault member, exactly one of the four anchors collides
with the hidden two-bit S-box projection. One pair therefore has signed delta `-1` or
`+1`; the other is equal. The exact extractor retains every secret/fault assignment
that reproduces both raw buckets. Across both pairs it fixes that epoch's projection;
the two epochs reconstruct `SBOX4[secret]`, whose public permutation is invertible.

There are four lanes, two epochs, and two pairs: 16 logical relation families and 32
physical executions. This fixed correctness baseline deliberately precedes adaptive
CEGIS (M6). It requires no white-box selection oracle.

## Exact recovery criterion

The full model usually retains three behaviorally equivalent non-off fault members,
so uniqueness is checked over `secret_0..secret_3`, not over private fault identity.
After obtaining one satisfying model, the solver adds a disjunction requiring at least
one secret nibble to differ. Only `unsat` permits `unique_exact`; `unknown` or a second
model is non-unique. The inferred hexadecimal secret is then submitted once to the
Rust judge. Acceptance, the uniqueness result, public costs, and artifact digest are
written to schema-valid `report.json`.

Under `off`, all relation deltas are equal. Because the extractor retains the latent
off model, all 65,536 secrets remain possible. The alternative-model query is `sat`,
the report is `inconclusive`, and the judge is never invoked.

## Commands and measured M5 result

```bash
just demo-tutorial
just test-tutorial-matrix
just test-tutorial-fault-free
```

The published seeds are `benchmarks/seeds/tutorial-evaluation.txt`. On 2026-07-16 the
reference matrix recovered and judge-accepted 100/100 generated challenges. Median and
maximum logical relation families were both 16, versus targets of at most 48 and 80.
The paired off-fault matrix produced 100/100 `inconclusive` reports and zero exact
declarations or judge submissions. Aggregate summaries are generated under
`runs/tutorial-evaluation-v2/summary.json` and
`runs/tutorial-fault-free-v2/summary.json`; the directory is intentionally ignored by
Git while exact command evidence is recorded in `VALIDATION.md`.
