# Codex master prompt

Use this prompt from the repository root after unpacking the archive.

---

Build the complete Sphinx Interrogator research system described in this repository.

Before editing code, read `AGENTS.md`, `README.md`, `docs/PROJECT_BRIEF.md`, `docs/FORMAL_MODEL.md`, `docs/EVALUATION.md`, `agent/CODEX_TASK_SPEC.md`, and `agent/PLANS.md` in full. Then inspect the entire scaffold and update `agent/plans/0001-full-system.md` into a fully current ExecPlan. Treat `agent/CODEX_TASK_SPEC.md` as the normative product specification and the active ExecPlan as the living implementation record.

The desired outcome is not a larger scaffold. It is an end-to-end, tested repository in which:

1. the Rust SphinxVM implements the architectural, fault-free, and faulty semantics behind the public JSONL process boundary;
2. the Python Interrogator uses only that public boundary;
3. certified relational experiments are translated into sound SMT/MaxSMT constraints;
4. a CEGIS-style grammar-guided selector recovers tutorial and standard secrets within the acceptance targets;
5. stateful research mode includes exact-history support and an AALpy-backed learned abstraction;
6. negative controls, boundary audits, formal checks, benchmarks, reports, and witness reduction work;
7. `just fmt`, `just lint`, `just test`, `just verify-formal`, `just demo-tutorial`, and the specified benchmark acceptance checks pass.

Preserve every hard boundary and safety restriction in the specification. System B must never import, link, read, or introspect private System A state. Do not weaken tests, expose diagnostic data, read challenge secrets, hard-code benchmark answers, or replace exact uniqueness checks with a best-effort guess.

Work milestone by milestone without asking for routine next-step confirmation. At every milestone, implement behavior, run the narrow tests, run the required repository checks, repair failures, and update the ExecPlan and `agent/STATUS.md` with exact command evidence and decisions. Use independent subagents/worktrees only for genuinely separable tasks, and integrate their work through the same tests and architectural review.

Prefer the smallest sound implementation that satisfies the current milestone. When an algorithmic choice is uncertain, build a reduced-domain prototype and measure it before committing to a large architecture. Preserve an auditable trail from every inference constraint to concrete protocol observations and relation certificates.

Do not mark the project complete until the “Definition of complete” section of `agent/CODEX_TASK_SPEC.md` is satisfied with recorded evidence. If a requirement is infeasible under the current environment, continue with every unblocked milestone, produce the strongest working partial result, and record the exact blocker, attempted paths, evidence, and what input would remove it.

Optional Codex Goal form:

    /goal Complete the Sphinx Interrogator repository according to agent/CODEX_TASK_SPEC.md, verified by all required formatting, lint, test, formal, boundary, tutorial-recovery, and standard-benchmark evidence, while preserving the strict black-box and synthetic-only safety boundaries. Use agent/plans/0001-full-system.md and agent/STATUS.md as living project memory. Between iterations, implement the highest-value unblocked milestone, run its verification surface, repair failures, and record evidence. If no defensible path remains for a requirement, finish all other requirements and report the precise blocker and the evidence needed to proceed.
