# Executable formal model

This directory contains the finite scheduler model and bounded relation obligations used
alongside the concrete Rust/Python differential tests.

- `SphinxVM.tla` models the hidden scheduler state, reset semantics, pending probes,
  anchors, guarded replay delta, experiment architectural confinement, gas progress,
  and public static/normalized-cost accounting as a finite transition system.
- `SphinxVM.cfg` supplies a tiny TLC instance intended for rapid regression checks.
- `relation_contracts.smt2` checks the base architectural and fault-free obligations
  for an anchor-switch relation and a directional reference-fault lemma.

The TLA+ model remains an abstraction rather than a full implementation certificate. The
verification script additionally exhausts reset projections, gas/progress transitions,
architectural-digest confinement for experiment operations, fault-free normalized-cost
independence, and all 131,072 combinations of the two-bit phase, two-bit replay credit,
low lane bits, token, epoch, secret bank, and anchor bank. Shared golden vectors connect
the independent Python model to the concrete Rust transition.

Run the structural and SMT checks with:

```bash
just bootstrap-formal
just verify-formal
```

The verification command also runs an internal mutation self-test. To see the deliberate
replay-suppression defect rejected directly:

```bash
uv run --frozen python scripts/check_formal_scaffold.py --mutate-suppression
```

That command is expected to exit with status 1 and identify the first counterexample.

The bootstrap recipe downloads the pinned TLA+ 1.7.4 command-line artifact into the
ignored `.tools/` directory and verifies its SHA-256 checksum. To override that local
path, set `TLA2TOOLS_JAR`. The equivalent direct model-check command is:

```bash
java -XX:+UseParallelGC -jar .tools/tla2tools-1.7.4.jar -workers 1 \
  -metadir .cache/tlc \
  -config formal/SphinxVM.cfg formal/SphinxVM.tla
```
