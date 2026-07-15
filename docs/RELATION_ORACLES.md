# Relation oracles

## 1. Role

A relation oracle decides whether a family of executions satisfies a relation that is known independently of the hidden secret. In this project, an oracle has two responsibilities:

1. validate or refute the expected relation at the public-observation level;
2. translate a sufficiently informative outcome into a sound constraint over secret and latent state.

The first responsibility is testing. The second turns testing into inference.

## 2. Relation-template interface

A template implementation should expose the following logical interface:

```python
class RelationTemplate(Protocol):
    id: RelationId
    version: SemVer

    def applicable(self, source: Query, profile: PublicProfile) -> Applicability: ...
    def instantiate(self, source: Query, holes: HoleAssignment) -> RelationInstance: ...
    def prove_arch(self, instance: RelationInstance) -> Certificate: ...
    def prove_fault_free(self, instance: RelationInstance) -> Certificate: ...
    def normalize(self, execution: ExecutionRecord) -> NormalizedObservation: ...
    def decide(self, batch: RelationBatch) -> OracleDecision: ...
    def extract(self, instance: RelationInstance, decision: OracleDecision) -> ConstraintArtifact: ...
    def reduction_rules(self) -> tuple[ReductionRule, ...]: ...
```

`applicable` returns either a proof-producing precondition result or a structured rejection. A relation cannot be executed for inference merely because its constructor can generate syntax.

## 3. Oracle taxonomy

Interrogation testing uses transformations analogous to strengthening, weakening, and preserving a query [R1]. Sphinx Interrogator generalizes them to execution relations.

### 3.1 Even relations

The transformed program is architecturally equivalent and has equal normalized fault-free cost.

\[
N(O_0(P))=N(O_0(P')).
\]

Examples: register alpha-renaming, independent instruction swapping, anchor substitution, and phase-shift with static-cost subtraction.

### 3.2 Strengthening relations

The follow-up introduces additional opportunities for the fault while preserving a known lower bound:

\[
N(O_0(P'))\ge N(O_0(P)) + c.
\]

A repeat-amplification relation can be written as a known linear equality in the fault-free model and a monotonic relation for selected fault mutations.

### 3.3 Weakening relations

The follow-up removes a context or event. If a violation remains, the reduced program is a stronger minimal witness. These relations are central to reduction.

### 3.4 Stateful relations

Two query sequences start from related microstates rather than identical resets. A certificate includes a pre-state relation \(R_M\) and shows that it is preserved or transformed predictably.

## 4. Required template set

### 4.1 `anchor-switch/v1`

Source shape:

```text
prefix;
PROBE lane, token, epoch;
ANCHOR bank_a, epoch;
suffix;
```

Follow-up changes `bank_a` to `bank_b`, with `bank_a != bank_b`.

- Architectural relation: final states and public output equal.
- Fault-free relation: normalized observations equal.
- Fault signal in exact reset mode:

\[
D=\delta_K(e,b_b,z_0)-\delta_K(e,b_a,z_0).
\]

Possible exact outcomes are `-1`, `0`, or `+1`. With a known active guard, `+1` implies the secret bank equals `bank_b`; `-1` implies it equals `bank_a`; zero excludes both only when suppression and noise are ruled out.

This is the foundational tutorial relation.

### 4.2 `token-switch/v1`

Keep the anchor fixed and change the probe token.

- Architectural relation: equal.
- Fault-free relation: equal.
- Constraint: compares two S-box projections for the same secret cell.

It is useful when candidate models agree on one token but disagree on another.

### 4.3 `epoch-switch/v1`

Change epoch and adjust any epoch-dependent static cost.

- Architectural relation: equal.
- Fault-free relation: equal after normalization.
- Constraint: couples low and high projections of the transformed nibble.

This relation should be used with care: epoch also changes phase transition, so a hard reset or certified context is required.

### 4.4 `phase-shift/v1`

Insert `PAD n` symmetrically or asymmetrically with a normalizer that subtracts `n`.

- Architectural relation: equal.
- Fault-free relation: equal after subtracting static pad cost.
- Fault signal: turns a guard on or off without changing the target bank equation.

This is an interrogation-style trick query: the relation is known, but its response reveals whether a prior interpretation of phase is consistent.

### 4.5 `repeat-amplify/v1`

Replace one certified cell with `r` repetitions, optionally separated by a drain sequence.

- Architectural relation: equal because cells are silent.
- Fault-free relation: known linear cost.
- Fault relation: exact linearity only if the precondition proves replay-state independence; otherwise use a symbolic recurrence.

The constructor must reject naive repetition when hidden replay credit would invalidate the assumed amplification.

### 4.6 `independent-swap/v1`

Swap two independent, architecturally silent cells.

- Architectural relation: equal.
- Fault-free relation: equal.
- Fault signal: exposes order-sensitive phase or replay transitions.

This relation is especially useful for diagnosing a wrong stateless model.

### 4.7 `context-lift/v1`

Given an already certified pair `(P,P')`, embed both in the same context `C[·]`.

- Architectural relation: follows from a frame condition.
- Fault-free relation: follows if the context has equal entry/exit scheduling state or a certified normalization.
- Use: amplify, move across quantization boundaries, or reach a learned state.

Context composition requires explicit entry and exit summaries; arbitrary prefixing is not sound.

### 4.8 `register-rename/v1`

Alpha-rename general registers in ordinary setup/output code.

- Architectural relation: equality up to the renaming, projected to public output.
- Fault-free relation: equal static cost.
- Use: negative control and structural diversity. It should not produce secret information in the reference fault.

If it does, the machine model or fault confinement is wrong.

### 4.9 `hard-replay/v1`

Execute the identical query after hard reset several times.

- Expected relation in deterministic profiles: identical observations.
- Use: check harness determinism, seeded noise policy, and witness reproducibility.

This relation validates the experimental apparatus rather than separating secrets.

### 4.10 `soft-history-contrast/v1`

Compare the same measurement suffix after two different certified history prefixes.

- Architectural relation: equal at suffix entry.
- Fault-free observation relation: depends on a state abstraction or exact transition proof.
- Use: produce counterexamples for the active learner and identify replay/cache state.

It cannot emit a hard secret constraint solely from a learned-state guess.

## 5. Certificates

A certificate includes:

```text
certificate id and version
relation instance hash
semantic version of VM model
precondition result
architectural claim
fault-free observation claim
proof method
proof artifact digest
scope/limitations
```

Recommended proof-strength lattice:

1. `theorem`: mechanically checked general proof;
2. `smt-bounded-complete`: exhaustive for declared finite bounds;
3. `exhaustive-enumeration`: all relevant finite inputs/configurations tested;
4. `differential-property`: generated tests, useful during development;
5. `empirical-only`: not allowed to emit hard inference constraints.

A campaign policy declares the minimum proof strength. Tutorial mode may accept bounded-complete certificates. Release benchmarks should not rely on empirical-only relations.

## 6. Composition

For relation instances \(P\sim_\rho Q\) and \(Q\sim_\sigma R\), transitive composition is allowed only if:

- architectural relations compose over the same projection;
- reset/history contexts line up;
- normalizers share units and baselines;
- latent-state postcondition of \(\rho\) implies precondition of \(\sigma\);
- uncertainty intervals are propagated correctly.

The composed extractor must be derived from the composed symbolic observation, not by blindly conjoining local signs.

## 7. Decision semantics

The oracle returns a structured decision:

```text
kind: equal | less | greater | violation | inconclusive | invalid
confidence/evidence: optional, method-specific
normalized samples and intervals
assumptions
candidate outcome set
```

- `invalid`: architectural relation, protocol, reset, or certificate failed.
- `inconclusive`: evidence is insufficient; no hard constraint.
- `equal/less/greater`: a declared outcome under exact/bounded semantics.
- `violation`: generic result for a relation not represented by order.

An outcome set can contain several symbolic possibilities under quantization. The extractor should emit their disjunction rather than forcing one sign.

## 8. Sound extraction example

Suppose `anchor-switch` uses hard reset, exact cycles, active guard, and no suppression. Let source anchor be 0 and follow-up anchor be 2. Then:

\[
D=[\beta_K(e)=2]-[\beta_K(e)=0].
\]

- `D=1` gives \(\beta_K(e)=2\).
- `D=-1` gives \(\beta_K(e)=0\).
- `D=0` gives \(\beta_K(e)\notin\{0,2\}\).

With bucket width 4 and bounded noise 1, equal buckets might be consistent with all three values. The correct extractor emits the disjunction of feasible values. It does not reuse the exact-cycle rule.

## 9. Relation soundness tests

Every template requires:

- parser/typechecker tests;
- precondition positive and negative tests;
- exhaustive architectural equivalence on a reduced machine;
- exhaustive fault-free observation relation on a reduced machine;
- concrete-versus-symbolic extractor differential tests;
- mutation tests that deliberately break the transform or normalizer;
- reducer-preservation tests;
- serialization/version compatibility tests.

The highest-value property test generates a secret, initial state, relation instance, and bounded noise choices, executes concrete semantics, extracts a formula, and checks that the true secret/state satisfies it.
