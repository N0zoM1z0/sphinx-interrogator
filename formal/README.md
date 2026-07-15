# Formal scaffold

This directory gives coding agents a small executable specification surface before the
full proof effort begins.

- `SphinxVM.tla` models the hidden scheduler state, reset semantics, pending probes,
  anchors, and guarded replay delta as a finite transition system.
- `SphinxVM.cfg` supplies a tiny TLC instance intended for rapid regression checks.
- `relation_contracts.smt2` checks the base architectural and fault-free obligations
  for an anchor-switch relation and a directional reference-fault lemma.

The files are deliberately smaller than the production semantics. They are not a
certificate for the final implementation. Milestones M1–M3 must connect these models
to the concrete Rust transition functions through differential/property tests and
record exact bounds for every bounded-completeness claim.

Run the structural and SMT checks with:

```bash
just verify-formal
```

When `tla2tools.jar` is available:

```bash
java -jar tla2tools.jar -config formal/SphinxVM.cfg formal/SphinxVM.tla
```
