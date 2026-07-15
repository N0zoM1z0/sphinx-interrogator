# Package manifest

This archive is a repository-ready design and implementation handoff.

## Core entry points

- `README.md`: project identity, goals, and navigation.
- `docs/PROJECT_BRIEF.md`: integrated technical proposal.
- `docs/FORMAL_MODEL.md`: transition-system and relational semantics.
- `docs/SYSTEM_A_SPHINX_VM.md`: target architecture and injected fault.
- `docs/SYSTEM_B_INTERROGATOR.md`: analysis/learning/synthesis architecture.
- `agent/CODEX_TASK_SPEC.md`: normative implementation requirements.
- `agent/CODEX_MASTER_PROMPT.md`: copy-paste launch prompt for Codex.
- `AGENTS.md`: repository-wide coding-agent instructions.
- `agent/plans/0001-full-system.md`: initial living execution plan.
- `docs/GITHUB_SETUP.md`: repository identity, labels, milestones, and first issues.
- `VALIDATION.md`: exact package checks, results, and unexecuted tool surfaces.
- `TREE.txt`: complete repository file inventory.
- `SHA256SUMS`: per-file integrity hashes for every packaged file except the checksum manifest itself.

## Scaffold

- Executable Rust JSONL/DSL/fault scaffold for SphinxVM under `crates/`.
- Typed Python relation, knowledge-base, solver, synthesis, statistics, learner, and campaign scaffold under `python/`.
- JSON Schemas and a probe-language grammar under `spec/`.
- TLA+ and SMT-LIB starting points under `formal/`.
- Benchmark profiles and example programs.
- CI, formatting, linting, and task-runner configuration.

The Python scaffold and bounded SMT contracts were executed as recorded in `VALIDATION.md`; Rust source was syntax-parsed but could not be compiled in the packaging environment. The repository is not represented as the completed research system. Completion criteria live in the Codex task specification.
