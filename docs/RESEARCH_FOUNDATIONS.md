# Research foundations

This document maps the project design to established methods. It is a rationale, not a claim that each cited system is directly reusable.

## 1. Oracle problem, metamorphic testing, and relations

The test-oracle problem concerns deciding whether an execution result is correct when a trusted expected output is unavailable or impractical. Surveys by Barr et al. and Segura et al. organize approaches including metamorphic testing, where several executions are related by a necessary property rather than checked independently [R3, R4].

Sphinx Interrogator uses this pattern at two levels:

- architectural outputs of related programs must satisfy a proved relation;
- normalized observations of the fault-free model must satisfy a second relation.

A deviation from the second relation is not immediately called “the secret.” It becomes evidence only after a sound extractor maps it into a logical condition.

## 2. Interrogation testing

Kaindlstorfer et al. introduced interrogation testing for program analyzers. The method uses richer verification responses and a knowledge base of past queries to construct transformations that can expose soundness and precision contradictions [R1]. Their Sherlock artifact provides a concrete implementation for reachability analyzers [R2].

The present project borrows the following concepts:

- preserve query-response history;
- select and transform earlier queries rather than mutate only a fresh seed;
- retain diverse queries;
- define expected relations for strengthening, weakening, and even transformations;
- minimize relation-violating witnesses.

The adaptation is substantial. The target is a stateful machine rather than an analyzer; responses are quantitative and noisy; and a violation is compiled into hidden-state constraints rather than only reported as a bug.

## 3. Hyperproperties and relational verification

Information-flow properties such as noninterference compare multiple traces, so they are naturally hyperproperties rather than single-trace properties [R5]. Relational symbolic execution similarly reasons about two runs or two programs under related inputs [R6].

This motivates the explicit self-composed view:

```text
run P and P' from related states
prove architectural relation
prove fault-free observation relation
compare faulty public observations
```

The relation-template certificate is a small product-program proof obligation. This prevents a common testing error: treating an empirically plausible transform as semantically valid.

## 4. Leakage models and observation refinement

Formal side-channel work often defines an observation model or leakage contract and validates implementations against it. Observation refinement explores progressively more discriminating observations, and black-box model-validation systems generate related experiments to find hidden microarchitectural behavior [R14, R15, R26].

SphinxVM adopts the methodological shape, not a concrete hardware target:

- a fault-free contract declares normalized secret independence;
- a faulty scheduler violates it under a narrow condition;
- experiments refine which secret/state configurations explain the deviation;
- controls check whether the model is too permissive or too precise.

The synthetic setting makes the ground truth and exact transition system available for research evaluation while retaining a strict black-box boundary for System B.

## 5. Active automata learning

Angluin's L* framework learns regular behavior using membership and equivalence queries [R7]. Modern libraries extend active learning to Mealy machines and practical conformance-testing approximations; AALpy is a Python library supporting deterministic, nondeterministic, and stochastic formalisms [R8].

Sphinx Interrogator maps:

- membership query → execute a macro-command sequence and observe discretized outputs;
- equivalence query → conformance/random/solver-guided search for a counterexample sequence;
- learned state → observational summary of persistent scheduler/cache state;
- distinguishing/homing sequence → identify or reach a useful state before measurement.

The active learner is an untrusted abstraction. Counterexamples can invalidate it, and state-conditioned secret constraints are versioned and retractable.

## 6. CEGIS and syntax-guided synthesis

CEGIS alternates between synthesizing a candidate that satisfies a finite set of examples and verifying it against the full or larger specification, adding counterexamples when it fails [R9]. Syntax-guided synthesis constrains candidates with a grammar [R10], while sketching and solver-aided languages provide related mechanisms for filling holes under semantic constraints [R11, R12].

Here, a candidate is an experiment. Examples/counterexamples are secret-state models that should be separated. The grammar guarantees that candidates are typed relation instances, not arbitrary instruction strings. A verifier searches for surviving models that the proposed query fails to separate or for noise/state choices that collapse the margin.

Z3 is suitable for finite bit-vector/state encodings and supports optimization and soft constraints [R13]. The project keeps a backend interface to allow later comparison with SyGuS solvers or Rosette.

## 7. Information-theoretic adaptive querying

Adaptive side-channel analysis can be viewed in terms of remaining uncertainty and information gained by each query [R18]. This project uses that view conservatively:

- exact entropy only when a finite candidate set and justified prior are available;
- worst-partition size for prior-free splitting;
- committee disagreement as a labeled proxy when samples are solver-diverse rather than uniform;
- explicit query cost and noise margin.

The evaluation should distinguish true information estimates from heuristics.

## 8. Test-case reduction

C-Reduce demonstrates the power of layered domain-independent and domain-specific transformations [R16]. The Hypothesis reducer shows how reduction can be integrated into generation so candidates remain valid by construction [R17].

The proposed reducer works over relation grammars and transformation traces. Validity is preserved because it regenerates typed families. Its predicate also checks proof certificates and logical consequence, which ordinary single-input reducers do not address.

## 9. Robust and sequential statistics

Repeated timing observations need robust estimation, treatment of correlation, and predeclared stopping rules. Median-of-means gives a robust location-estimation pattern; sequential probability ratio testing offers a principled way to stop once enough evidence accumulates [R19, R20].

These are design options rather than mandatory algorithms for every profile. Exact and bounded profiles should avoid unnecessary statistics. Stochastic profiles must validate their chosen test by simulation before using it for soft evidence.

## 10. Agent-oriented repository design

OpenAI's Codex documentation describes repository-level instructions through `AGENTS.md` and recommends execution plans for complex, long-horizon work [R22, R23]. It also emphasizes clear goals, verification surfaces, constraints, and continuous status/decision tracking [R24].

This package therefore includes:

- a concise root `AGENTS.md`;
- a self-contained Codex task specification;
- an ExecPlan standard and initial plan;
- milestone-level acceptance criteria;
- a status/audit file;
- commands that provide objective verification surfaces.

## 11. What is novel in the combination

The individual ingredients are established, but the proposed combination creates several interesting technical questions:

- relation violations are simultaneously tests and symbolic observations;
- query synthesis operates over a knowledge graph and a current hypothesis formula;
- active learning tracks hidden state that mediates side-channel constraints;
- reduction must preserve a relational proof and an inferred formula;
- calibration seeks a fault regime where adaptive relational methods help while trivial querying does not.

These are the project's primary research contributions if the implementation and evaluation support them.
