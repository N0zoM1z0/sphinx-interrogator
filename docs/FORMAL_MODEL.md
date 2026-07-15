# Formal model

## 1. Machine families

Let:

- \(S\) be the finite set of architectural states;
- \(M\) be the finite set of microarchitectural states;
- \(K\) be the set of hidden configurations;
- \(I\) be the set of instructions;
- \(P=I^*\) be bounded valid programs;
- \(X\) be public inputs;
- \(O\) be public observations.

For a hidden configuration \(k\in K\), define three semantics.

### Architectural semantics

\[
\llbracket P\rrbracket_A : S\times X \to S\times AOut.
\]

It does not take \(k\) as an argument. Equivalently, the concrete implementation may carry \(k\), but the projection must satisfy secret independence.

### Fault-free concrete semantics

\[
\llbracket P\rrbracket_0^k : S\times M\times X
  \to S\times M\times Trace_0.
\]

The microtrace may contain secret-indexed internal events, but the certified normalized public observation must satisfy the leakage contract for relation instances.

### Faulty semantics

\[
\llbracket P\rrbracket_F^k : S\times M\times X\times R
  \to S\times M\times Trace_F,
\]

where \(R\) supplies deterministic or stochastic noise choices. The public projection is

\[
\operatorname{pub}(Trace_F)\in O.
\]

## 2. Transition system

A complete configuration is

\[
C=(pc,s,m,k,g,t),
\]

where `g` is remaining gas and `t` accumulated exact cycles. A small-step transition has the form

\[
C \xrightarrow{\mu/e} C',
\]

where \(\mu\) is the selected micro-op and \(e\) an internal event. Internal events include:

- `ArchRead/ArchWrite`;
- `VaultAccess(bank,epoch)`;
- `AnchorAccess(bank,epoch)`;
- `Replay(delta)`;
- `Phase(old,new)`;
- `Retire(opcode)`.

The fault module is a pure relation over the pre-state, current event, and reference schedule decision:

\[
F_k(m,e,d_0)=(d_F,m_F).
\]

No fault transition may alter architectural writes chosen by the reference semantics.

## 3. Trace projections

Let a concrete trace be \(\tau\). Define:

- \(\alpha(\tau)\): final architectural state, public output, and status;
- \(\chi(\tau)\): exact cycle count and declared public static metrics;
- \(\omega_h(\tau,r)=Q_h(\chi(\tau)+\eta(r))\): public observation;
- \(\iota(\tau)\): private internal event trace, unavailable to System B.

Architectural noninterference is:

\[
\forall k_1,k_2,P,s,x,m_1,m_2,r_1,r_2.\quad
\alpha(\llbracket P\rrbracket_F^{k_1}(s,m_1,x,r_1))
=
\alpha(\llbracket P\rrbracket_F^{k_2}(s,m_2,x,r_2)).
\]

This is a two-run hyperproperty [R5]. Because experiment instructions are architecturally silent, it should be provable by induction over architectural steps.

## 4. Query semantics

A reset policy \(r\) maps the prior concrete state to a new initial state:

\[
Reset_r:S\times M\to S\times M.
\]

- `hard`: architectural initial state and unique microstate \(m_0\);
- `soft`: architectural initial state and projection-preserved microstate;
- `none`: preserve both subject to protocol rules.

A query is \(q=(r,P,x)\). In a stateful session:

\[
Run_k((s,m),q,\rho)=((s',m'),a,o,d).
\]

A query sequence is therefore the natural input to active automata learning.

## 5. Relations

A binary relation template \(\rho\) contains:

\[
\rho=(Pre,T,R_A,N,R_0,E).
\]

For source query \(q\), \(T(q)=q'\). It is **architecturally certified** when:

\[
\forall k,s,m,x.\ Pre(q,s,x) \Rightarrow
R_A(\alpha(Run_k((s,m),q)),\alpha(Run_k((s,m),q'))).
\]

Usually both runs use hard reset. Stateful templates instead quantify over related pre-microstates.

It is **fault-free observation certified** when:

\[
\forall k,s,m,x.\ Pre(q,s,x) \Rightarrow
R_0(N(\chi(\llbracket q\rrbracket_0^k)),N(\chi(\llbracket q'\rrbracket_0^k))).
\]

The normalization function can use public static metrics but not secret state.

### 5.1 Equality relation

\[
R_0(u,v) \equiv u=v.
\]

### 5.2 Monotonic relation

For a transformation that adds exactly \(n\) fault-free cells:

\[
R_0(u,v) \equiv v-u=n c_0.
\]

After normalization this is often equality.

### 5.3 Subset relation

For set-valued diagnostic abstractions used in formal testing:

\[
R_0(U,V) \equiv U\subseteq V.
\]

The public timing benchmark primarily uses equality/order relations, but the framework should keep the oracle generic enough to mirror strengthen/weaken/even interrogation transformations.

## 6. Fault constraint semantics

For a concrete relation instance \(r_i\), define symbolic normalized observations:

\[
D_i(k,z,\epsilon)=N(O_i^1)-N(O_i^0).
\]

An exact decision `greater` yields:

\[
D_i(k,z,0)>0.
\]

A quantized observation pair \((b_0,b_1)\), width \(h\), and bounded noise \(n\) yields:

\[
\exists c_0,c_1,\eta_0,\eta_1.\quad
c_j=\widehat{c}_j(k,z)+\eta_j
\land -n\le\eta_j\le n
\land hb_j\le c_j<h(b_j+1).
\]

The extractor may project nuisance variables or keep them local to an evidence block. Constraints from independent hard-reset runs share `k` but not latent state or noise variables.

For a stateful history \(q_1\ldots q_n\):

\[
z_{i+1}=\Delta(k,z_i,q_i),
\]

and all observations constrain the same state path. Treating each query with a fresh unconstrained `z_i` is sound but often too weak; assuming a fixed `z` is unsound.

## 7. Hypothesis formula

After transcript \(\mathcal{T}_t\):

\[
H_t(k,Z,E)=Domain(k)\land Reset/Transition(Z)\land
\bigwedge_{i\in Hard} C_i(k,Z_i,E_i).
\]

Soft evidence is maintained separately with weights:

\[
\operatorname*{argmax}_{k,Z,E\models H_t}
\sum_{i\in Soft} w_i [C_i(k,Z_i,E_i)].
\]

A secret \(k^*\) is exactly unique iff:

\[
H_t(k^*,Z,E)\text{ is satisfiable}
\]

and

\[
H_t(k,Z,E)\land k\neq k^*\text{ is unsatisfiable}.
\]

The second solver check is required for a `unique` result.

## 8. Synthesis problem

Let \(G\) be a finite grammar of well-typed relation instances and \(B\) a resource bound. Let `sig(q,k,z)` be a finite predicted oracle outcome such as `less/equal/greater`.

### Pair-separating synthesis

\[
\exists q\in G_{\le B}, k_1,k_2,z_1,z_2.\quad
H_t(k_1,z_1)\land H_t(k_2,z_2)\land k_1\neq k_2
\land sig(q,k_1,z_1)\neq sig(q,k_2,z_2).
\]

### Committee-balanced synthesis

Given sampled models \(M=\{m_1,\ldots,m_n\}\), partition them by signature. Minimize the maximum bucket:

\[
\min_q \max_{o}\left|\{m\in M\mid sig(q,m)=o\}\right|.
\]

Secondary objectives minimize gas, physical samples, AST size, and similarity to existing KB nodes. Z3 optimization can encode bounded versions, while CEGIS adds models missed by the initial committee [R9, R13].

## 9. CEGIS loop

1. Start with a small diverse committee \(M_0\subseteq models(H_t)\).
2. Synthesize \(q_i\) optimizing the partition of \(M_i\).
3. Ask a verifier for a surviving model pair that `q_i` fails to separate, or for a model lying in an oversized predicted partition.
4. If found, add those model(s) to \(M_{i+1}\) and repeat.
5. Otherwise return `q_i` with bounded verification evidence.

This is not a global proof of optimal information gain unless exact model counting is used. The API and report must label it `committee-verified` or `bounded-optimal`, not `optimal`.

## 10. Active-learning abstraction

A state abstraction is a map

\[
\gamma:M\to Q
\]

into finite learned states. For macro input alphabet \(\Sigma\) and output alphabet \(\Gamma\), a Mealy hypothesis is

\[
\mathcal{M}=(Q,q_0,\delta,\lambda).
\]

The abstraction is adequate for a campaign region when all tested histories mapping to the same `Q` state produce the same discretized output for tested suffixes. Counterexamples refine the observation table/hypothesis.

A secret constraint conditioned on learned state \(q\) is valid only relative to the current abstraction version and the evidence that the concrete history belongs to \(q\). It is retractable when a counterexample splits that state.

## 11. Proof obligations by component

### VM

- secret independence of architectural semantics;
- deterministic reference step;
- reset invariants;
- bounded termination;
- fault confinement to microarchitectural scheduling.

### Relation template

- source precondition decidable;
- transformation well-typed;
- architectural relation valid;
- fault-free observation relation valid;
- extractor sound with respect to observation intervals/model;
- minimization transformations preserve obligations.

### Solver

- faithful encoding of concrete bank/fault/state functions;
- no width/sign mismatch;
- uniqueness checked with an alternative-model query;
- `unknown` propagated.

### Statistics

- stopping boundaries fixed before seeing a batch or adjusted through a declared sequential method;
- paired-order randomization recorded;
- hard constraint only under a profile-declared bounded model;
- stochastic evidence remains soft unless separately certified.

## 12. Formal artifacts

- `formal/SphinxVM.tla`: reset/session/state invariants and a small abstract scheduler.
- `formal/relation_contracts.smt2`: bounded examples of architectural equality and fault-free timing equality.
- Python/Z3 executable semantics: main proof/testing vehicle for concrete relation instances.
- Property tests: differential checks between Rust concrete semantics and the symbolic model over generated small cases.

The TLA+ model is intentionally abstract; it should verify protocol and state-transition invariants, not reproduce every ALU instruction.
