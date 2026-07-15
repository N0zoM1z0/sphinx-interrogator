# Project brief

## 1. Thesis

Sphinx Interrogator is an executable research environment for the following problem:

> Given black-box access to a stateful transition system whose public semantics do not expose a hidden secret, recover the secret by constructing related programs, observing weak violations of an intended relational leakage contract, and synthesizing the next experiment from the constraints learned so far.

The target, **SphinxVM**, is intentionally complex enough to support meaningful program-analysis techniques but small enough to model exactly. The learner, **Interrogator**, is not given a direct oracle for the secret. It obtains evidence only from the public protocol and must establish why each comparison is legitimate.

The project deliberately joins five lines of work:

1. **Metamorphic and relational testing.** When no single-run expected output is available, compare several executions whose outputs should satisfy a known relation [R3, R4].
2. **Interrogation testing.** Retain rich responses and a diverse history of past queries; use transformations designed to force contradictions rather than generate isolated random tests [R1, R2].
3. **Relational verification and hyperproperties.** Architectural equivalence and non-leakage are relations across runs, not ordinary properties of a single trace [R5, R6].
4. **Active learning.** Choose queries adaptively and learn an observational model of persistent hidden state [R7, R8].
5. **Program synthesis.** Search a typed grammar for experiments that separate remaining hypotheses; refine the search with counterexamples in a CEGIS loop [R9–R13].

## 2. Systems

### 2.1 System A: SphinxVM

SphinxVM is a 16-bit, cycle-accurate, microcoded VM with separate architectural and microarchitectural state.

Architectural state contains registers, flags, RAM, a program counter, and a bounded call stack. Its ISA supports ordinary arithmetic, memory, and control flow plus three architecturally silent experiment instructions:

- `PROBE lane, token, epoch`: issue a secret-indexed vault access;
- `ANCHOR bank, epoch`: issue a public-bank access;
- `PAD n`: consume a statically known number of cycles while changing a scheduler phase.

Every accepted experiment must have secret-independent public output. The hidden secret is never loaded into an architectural register or memory location.

Microarchitectural state contains a four-bank vault scratchpad, a replay latch, a phase register, a small micro-op cache, and optional persistent state. A correct scheduler reserves a fixed envelope for vault operations. The injected defect incorrectly inserts or removes a replay bubble for a narrow secret-dependent bank-conflict condition. Only an aggregate, quantized timing observation is returned.

The design is inspired by formal leakage contracts and iterative model validation, but it is not intended to reproduce a real processor [R14, R15].

### 2.2 System B: Interrogator

Interrogator is a black-box experimental agent with these components:

- a parser and typed AST for the probe DSL;
- a library of relation templates with proof obligations;
- a harness for paired, randomized, repeated executions;
- a knowledge base storing queries, transformations, observations, and solver consequences;
- an exact/soft SMT secret model;
- a grammar-guided query synthesizer;
- an active learner for persistent hidden states;
- a robust statistical decision layer;
- a relational witness reducer;
- campaign and evaluation tooling.

Interrogator may know the public machine family and the mathematical form of the configurable fault. It does not know the challenge secret, hidden lane mapping, current microstate, jitter samples, or private simulator state.

## 3. The injected fault

Let the secret be a vector of four-bit cells

\[
K = (k_0,\ldots,k_{L-1}), \qquad k_i \in \{0,\ldots,15\}.
\]

A profile may also contain a hidden permutation \(\pi\) and fixed hidden lane salts \(\sigma_i\). For a probe event

\[
e = \operatorname{probe}(i,q,p),
\]

where \(i\) is a lane, \(q\) a four-bit token, and \(p\in\{0,1\}\) an epoch, define the secret bank

\[
\beta_K(e) = \operatorname{slice}_p
  \left(S\left[k_{\pi(i)} \oplus q \oplus \sigma_i\right]\right)
  \in \{0,1,2,3\}.
\]

`S` is a public four-bit permutation. `slice_0` returns the low two bits and `slice_1` the high two bits. An anchor event declares a public bank \(b\).

In the fault-free machine every probe-anchor cell has normalized cost \(c_0\), independent of \(K\). In the faulty machine, a guarded replay term is added:

\[
\delta_K(e,b,z) =
  [\beta_K(e)=b]\,[g(e,z)]\,[\neg\operatorname{suppress}(z)],
\]

where \(z\) is hidden scheduler state and brackets denote Boolean indicators. A second branch may elide a reserved bubble, yielding a signed contribution in advanced profiles. The hidden-state transition records conflict history, updates a replay credit, and changes phase.

The public observation is not \(\delta\) itself. It is

\[
y = Q_h\left(c_{\text{static}}(P)+\sum_j \delta_K(e_j,b_j,z_j)+\eta\right),
\]

where \(Q_h\) quantizes to buckets of width \(h\) and \(\eta\) is seeded bounded or stochastic jitter. Repetition can amplify a weak term, but query length and execution budgets make indiscriminate amplification expensive.

### Why this fault is neither too strong nor too weak

It is not too strong because:

- no architectural value depends on the secret;
- the interface returns only an aggregate bucket, not an event trace;
- the leak is guarded by phase and hidden replay state;
- a single observation is confounded by static cost, quantization, and jitter;
- the bank function exposes only a projection of one transformed nibble per epoch;
- research mode hides lane correspondence and preserves state across queries.

It is not too weak because:

- related programs can cancel static cost and common structure;
- two epochs jointly distinguish all four-bit values;
- bounded repetition can move a one-cycle effect across a bucket boundary;
- hard-reset profiles make the latent state exact;
- soft-reset profiles remain learnable through state identification sequences;
- the fault model can be compiled into bit-vector constraints.

## 4. Relation oracle

A query is

\[
q=(r,P,x),
\]

where \(r\) is reset policy, \(P\) a program, and \(x\) public input. Executing a secret-parameterized machine returns architectural output \(a\), observation \(o\), and a public execution descriptor \(d\):

\[
\operatorname{run}(A_K,q)=(a,o,d).
\]

A relation template is a tuple

\[
\rho=(\operatorname{pre},T,R_A,N,R_O^0,E),
\]

with:

- precondition `pre` on a source query;
- transformation \(T\) that constructs one or more follow-up queries;
- architectural relation \(R_A\);
- observation normalizer \(N\);
- fault-free relation \(R_O^0\) over normalized observations;
- extractor \(E\) that translates a measured relation into constraints on the secret and latent state.

Before a relation can be used for inference, Interrogator must establish

\[
\forall K,x.\ R_A(\alpha(A_K^0(q)),\alpha(A_K^0(T(q))))
\]

and

\[
\forall K,x.\ R_O^0(N(\omega(A_K^0(q))),N(\omega(A_K^0(T(q)))))
\]

for the fault-free semantics \(A^0\). In practice, templates receive a proof certificate produced by symbolic execution, exhaustive checking over bounded operands, or a trusted handwritten lemma backed by property tests. Merely observing equal public output in one run is not enough.

An actual violation is useful only after the extractor derives a satisfiable secret constraint. This makes the relation oracle a bridge from testing to inference.

## 5. Interrogation testing adaptation

Traditional metamorphic testing often begins with a seed, creates follow-ups, and checks a local relation. The proposed loop adopts the richer interrogation model [R1]:

1. Maintain a **knowledge base** of previous query nodes and relation edges.
2. Select a node whose neighborhood, relation coverage, or predicted candidate split is promising.
3. Apply a typed transformation that carries expected architectural and observation relations.
4. Execute the resulting query family under a controlled reset and sampling schedule.
5. Reject any family whose architectural relation fails.
6. Test the observation relation with an exact or statistical oracle.
7. Convert the outcome into exact, interval, or weighted constraints.
8. Retain the result if it improves relation coverage, state coverage, structural diversity, or posterior uncertainty.
9. Age low-value local clusters with a time-to-live policy.
10. Reduce strong violations to minimal relational witnesses without destroying their proof or inferred constraint.

A knowledge-base edge therefore stores more than “pass/fail.” It records transformation lineage, normalized samples, confidence, latent-state assumptions, the emitted logical formula, model-count estimates, and implication checks against the prior constraint store.

## 6. Program synthesis as experimental design

The synthesis problem is not “synthesize the secret.” The SMT solver already represents candidate secrets. The main program-synthesis problem is:

> Synthesize a bounded, well-typed related program family whose predicted observation partitions the current candidate set as evenly and robustly as possible.

Let \(H_t(K,Z)\) be the current hypothesis formula. A basic discriminating query problem asks for a query family \(q\) and two surviving configurations \((K_1,Z_1)\), \((K_2,Z_2)\) such that

\[
H_t(K_1,Z_1) \land H_t(K_2,Z_2) \land K_1\neq K_2
\]

and

\[
\widehat{o}(q,K_1,Z_1) \neq \widehat{o}(q,K_2,Z_2).
\]

The synthesizer searches a grammar of relation templates, lanes, tokens, epochs, anchors, phase-control padding, repeat counts, and reset policies. It first separates a pair or small committee of models, then verifies the query against a larger sampled committee. Counterexample models that collapse into the same partition are added to the synthesis constraints. This is a CEGIS-style loop [R9].

Candidate queries are ranked by an approximation to

\[
\operatorname{score}(q)=
  \widehat{I}(K;O_q\mid\mathcal{T}_t)
  - \lambda_c\operatorname{cost}(q)
  - \lambda_n\operatorname{noiseRisk}(q)
  - \lambda_d\operatorname{duplication}(q,\mathcal{K}),
\]

where \(\mathcal{T}_t\) is the transcript and \(\mathcal{K}\) the knowledge base. Exact model counting is optional; the initial implementation uses diverse model sampling, query-by-committee disagreement, and bounded partition estimates.

## 7. Stateful extension

Under soft reset, SphinxVM preserves replay credit, phase, and a small cache tag. The same program may produce different observations depending on history. Treating samples as IID would yield incorrect secret constraints.

Interrogator therefore has three modes:

- **hard-reset exact mode:** every logical query starts in a known microstate;
- **history-explicit mode:** the entire command prefix is part of the query and the SMT model carries latent state transitions;
- **learned-abstraction mode:** active automata learning infers a Mealy-machine abstraction whose states summarize observationally relevant history.

Membership queries correspond to input sequences ending in a measurement command. Equivalence queries are approximated with conformance testing, random walks biased toward relation violations, and solver-generated distinguishing sequences. Homing or adaptive distinguishing sequences are used when a global reset is unavailable. AALpy is the recommended initial library [R8], wrapped behind a project-owned interface.

The learned machine is not assumed to reveal the secret directly. It supplies state identifiers, reset/homing sequences, and state-conditioned observation predictions to the secret synthesizer.

## 8. Noise handling

The statistical layer must never silently turn uncertain evidence into a hard logical fact.

- Exact deterministic profiles emit hard constraints.
- Bounded-noise profiles emit interval constraints with explicit nuisance variables.
- Stochastic profiles repeat paired queries in randomized `AB`/`BA` order.
- Median-of-means or another robust location estimator handles outliers.
- A sequential probability ratio test can stop once a relation outcome reaches configured evidence.
- Contradictory stochastic observations become weighted soft constraints in MaxSMT rather than making the model spuriously unsatisfiable.
- Any conclusion records sample count, effect estimate, uncertainty, seed, and stopping rule.

A campaign should periodically replay high-value witnesses. Failure to reproduce them triggers constraint quarantine and model repair.

## 9. Calibration and controls

Fault calibration is itself a program-analysis task.

### Positive calibration

For generated secrets, measure the best achievable partition quality over a bounded probe grammar. Standard mode should contain many useful queries but few dominant one-shot queries. Target ranges are defined in `docs/EVALUATION.md`.

### Negative controls

- **Fault-free build:** all certified observation relations should hold modulo declared noise; secret recovery must remain near chance.
- **Secret-independent jitter build:** the statistical layer must not manufacture secret constraints.
- **Wrong model build:** the solver should expose inconsistency, quarantine unreliable constraints, and report model inadequacy rather than inventing a secret.
- **Boundary audit:** System B must fail if it tries to read private challenge files, environment variables, process memory, or VM source-derived helper modules.

### Mutation controls

Create scheduler mutations with different leak strengths. Recovery cost should be monotone in aggregate: stronger leaks need fewer executions, while a disabled leak should not recover. Individual seeds may vary, so claims are evaluated over campaign distributions.

## 10. Implementation strategy

### Language split

- Rust for the deterministic, cycle-sensitive SphinxVM and protocol server.
- Python for synthesis, SMT, active learning, statistics, and experiment orchestration.
- JSON Lines for the process boundary.
- JSON Schema for public messages.
- TLA+ for state-machine and reset invariants.
- SMT-LIB examples and Python/Z3 proofs for finite relational contracts.

### Milestone sequence

1. Public schemas, DSL, deterministic architectural interpreter.
2. Fault-free microarchitecture and cycle accounting.
3. Injected fault, profile configuration, and private challenge mechanism.
4. Relation templates and proof/test certificates.
5. Black-box harness and knowledge base.
6. Exact SMT secret recovery in tutorial mode.
7. Grammar-guided query synthesis and candidate-set scoring.
8. Quantization, noise, sequential sampling, and MaxSMT repair.
9. Soft-reset state and active automata learning.
10. Benchmarks, ablations, reducers, reports, and formal checks.

The normative details and acceptance criteria are in `agent/CODEX_TASK_SPEC.md`.

## 11. Expected learning outcomes

A successful implementation provides hands-on practice with:

- operational and small-step semantics;
- self-composition and relational specifications;
- symbolic execution and bit-vector encodings;
- metamorphic-relation design and oracle soundness;
- knowledge-guided test generation;
- CEGIS and syntax-guided synthesis;
- active automata learning and conformance testing;
- robust sequential statistics;
- approximate model counting and information gain;
- witness reduction and delta debugging;
- experiment reproducibility and empirical PL evaluation.

## 12. Non-claims

This document specifies a proposed system and quantitative acceptance targets. It does not claim that the scaffold already meets recovery budgets, that its synthetic fault matches a real CPU, or that a successful campaign transfers to production systems. Those statements require implementation and measured evidence.
