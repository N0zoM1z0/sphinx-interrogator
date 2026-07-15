# Agent instructions

## Mission

Build the synthetic SphinxVM/Interrogator research system specified in `agent/CODEX_TASK_SPEC.md`. Preserve the hard black-box boundary: Python code must never import the Rust VM implementation or read private challenge state.

## First actions

1. Read `README.md`, `docs/PROJECT_BRIEF.md`, `docs/FORMAL_MODEL.md`, and `agent/CODEX_TASK_SPEC.md`.
2. Read `agent/PLANS.md` in full.
3. Use and continuously update `agent/plans/0001-full-system.md` as the ExecPlan for substantial work.
4. Record current status, test evidence, blockers, and important decisions in `agent/STATUS.md` and the ExecPlan.

Do not ask for the next milestone. Work through the plan until the acceptance criteria pass or a concrete external blocker remains.

## Repository boundaries

- `crates/sphinx-vm/`: System A; Rust; private secret and microarchitectural implementation.
- `python/sphinx_interrogator/`: System B; Python; black-box client, relations, learning, inference, and synthesis.
- `spec/`: language and wire contracts shared by both sides.
- `formal/`: executable or checkable formal models.
- `docs/`: rationale and research documentation.
- `tests/`: cross-language integration and adversarial boundary tests.

System B may depend only on the schemas, the documented public protocol, and returned observations. A test-only judge may compare a submitted guess with the hidden secret after a campaign; it must not reveal intermediate secret data.

## Engineering rules

- Prefer explicit immutable data models and pure transition functions at semantic boundaries.
- Keep architectural semantics, fault-free microarchitectural semantics, and faulty semantics separate.
- Every relation template needs: preconditions, a program transformation, an architectural proof/test, a fault-free observation oracle, and a secret-constraint extractor.
- Every nondeterministic component receives an explicit seed and logs it.
- No flaky statistical assertions: use deterministic fake samplers for unit tests and confidence-bounded tests for stochastic integration cases.
- No silent approximation. Label exact, sampled, heuristic, and probabilistic results in APIs and reports.
- Avoid `unwrap`, broad exception catches, hidden global state, and unbounded solver calls.
- Keep generated artifacts out of source control except small golden fixtures.

## Required checks

Before declaring a milestone complete, run the narrowest relevant tests and then:

```bash
just fmt
just lint
just test
```

For changes to semantics or relations, also run:

```bash
just verify-formal
just demo-tutorial
```

Document commands and outcomes in the active ExecPlan. Never claim a check passed without running it.

## Definition of done

A change is done only when behavior is implemented, tests cover success and failure paths, public schemas/docs match the code, the black-box boundary still passes its audit, and the active ExecPlan reflects reality.

## Safety constraints

Implement only the synthetic VM and its local protocol. Do not add real-hardware timing collectors, privileged instructions, victim integrations, network scanners, production target adapters, or exploit deployment features. Keep all examples generated and self-contained.
