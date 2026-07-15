# GitHub repository setup

## Recommended identity

- **Repository:** `sphinx-interrogator`
- **Display title:** Sphinx Interrogator
- **Description:** `A formal-methods playground for recovering hidden state from a deliberately leaky microcoded VM using relational oracles, interrogation testing, active automata learning, and CEGIS.`
- **Homepage:** leave blank until documentation or benchmark reports are published.
- **License:** Apache-2.0.
- **Visibility:** public is appropriate for the framework and generated challenges; private challenge secrets must never be committed.

Recommended topics:

```text
program-analysis
program-synthesis
formal-methods
metamorphic-testing
active-automata-learning
side-channel
cegis
smt
rust
python
```

Alternative names considered but not recommended as the canonical repository name:

- `oracle-vault`: memorable, but does not signal the interrogation-testing focus;
- `sphinxvm-lab`: emphasizes System A but undersells System B;
- `relational-riddle`: descriptive but less suitable as a durable research-project name.

## Initial repository settings

Protect `main` after the bootstrap commit. Require the GitHub Actions `rust` and `python` jobs, at least one approving review, resolution of review conversations, and linear history. Disallow force pushes and branch deletion. Enable Dependabot only after lockfiles exist and the first reproducible build passes.

Do not upload private challenge directories, raw secret material, benchmark answer keys, or diagnostic traces. The `.gitignore`, `SECURITY.md`, and boundary tests are defense in depth rather than permission to store those files locally inside the repository.

## Labels

Create a small, stable label vocabulary:

| Label | Meaning |
|---|---|
| `area/vm` | Rust target architecture, semantics, or protocol server |
| `area/interrogator` | Python analysis, inference, synthesis, or campaign code |
| `area/formal` | TLA+, SMT, relational proofs, or differential checks |
| `area/evaluation` | Benchmarks, calibration, statistics, or reports |
| `area/protocol` | Shared schema, DSL, compatibility, or boundary work |
| `type/bug` | Behavior contradicts the current specification |
| `type/research` | Hypothesis or experiment whose outcome is not yet known |
| `type/infrastructure` | CI, packaging, toolchain, or developer workflow |
| `priority/blocker` | Prevents the active milestone from completing |
| `good-first-relation` | A self-contained new relation template with a proof/test plan |

## Milestones

Mirror the implementation sequence in `agent/CODEX_TASK_SPEC.md`:

1. `M0 — Bootstrap and public protocol`
2. `M1 — DSL and architectural semantics`
3. `M2 — Microarchitecture, fault, and challenges`
4. `M3 — Relations and certificates`
5. `M4 — Harness, knowledge base, and solver`
6. `M5 — Deterministic tutorial recovery`
7. `M6 — CEGIS query synthesis`
8. `M7 — Noise and standard profile`
9. `M8 — Stateful learning`
10. `M9 — Reduction, evaluation, and release`

## First issues

Open these issues after the initial scaffold commit. Their acceptance criteria should reference the normative task specification rather than duplicate it.

1. **Make M0 checks green on a clean machine.** Generate lockfiles, compile the Rust server, validate all fixtures against both implementations, and record exact commands in the ExecPlan.
2. **Complete the version-1 DSL and canonicalizer.** Implement the remaining control-flow and memory instructions, bounded-loop validation, round-trip tests, and malformed-input tests.
3. **Implement a shared pure microstate transition function.** Use it from concrete execution, symbolic semantics, exhaustive reduced-domain tests, and mutation variants.
4. **Certify `anchor-switch/v1`.** Discharge architectural and fault-free obligations at declared bounds and connect violations to solver constraints with provenance tests.
5. **Land the deterministic tutorial campaign.** Recover generated 16-bit challenges through the public process boundary and prove uniqueness with an alternative-model query.

## Release policy

Use `0.x` releases while relation semantics, protocol messages, and benchmark profiles may change. Tag `v0.1.0` only when M0–M5 are reproducible on a clean checkout. Reserve `v1.0.0` for the complete definition in the task specification, including the fault-free negative control, stateful profile, benchmark evidence, formal checks, and archived machine-readable reports.
