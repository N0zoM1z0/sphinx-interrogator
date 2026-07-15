# Contributing

Contributions should preserve the research question: infer hidden state in a synthetic black-box transition system through relational experiments.

1. Start with an issue describing the hypothesis or engineering need.
2. For substantial work, add or update an ExecPlan under `agent/plans/`.
3. Include deterministic tests and a benchmark seed when behavior changes.
4. Update schemas and design documentation together with code.
5. State whether a result is exact, bounded, sampled, or heuristic.
6. Confirm that the black-box boundary audit and fault-free negative control still pass.

Code should be formatted and tested with `just fmt`, `just lint`, and `just test`. Formal-semantic changes also require `just verify-formal`.
