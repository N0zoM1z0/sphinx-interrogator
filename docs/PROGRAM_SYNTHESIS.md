# Program synthesis and active experiment design

## 1. Synthesis targets

The project uses synthesis at three levels.

1. **Experiment synthesis:** generate a related program family that separates secret/state hypotheses.
2. **Sequence synthesis:** generate a prefix, homing sequence, or distinguishing suffix that reaches/identifies useful microstate.
3. **Decoder synthesis:** optionally compress a completed campaign into a small decision tree or straight-line recovery strategy.

Experiment synthesis is required. The other two are research extensions.

## 2. Probe DSL grammar

The grammar is syntax-guided: candidates must be well-typed and resource-bounded by construction [R10]. A high-level relation grammar is preferable to enumerating raw instruction lists.

```text
Experiment ::= Relate(RelationKind, Core, Context, Schedule)
Core       ::= Cell | Seq(Core, Core) | Repeat(Core, Count)
Cell       ::= ProbeAnchor(Lane, Token, Epoch, Bank)
Context    ::= Empty | Pad(BoundedNat) | Fence | Prefix(Core) | Suffix(Core)
Schedule   ::= HardPair | SoftSequence | ABBA(Repetitions)
Count      ::= 1 | 2 | 4 | 8 | 16
```

Each production carries static typing, cost, architectural-effect summary, and state assumptions. Lowering to the assembly DSL happens only after synthesis.

## 3. Search-space decomposition

A monolithic SMT encoding of arbitrary programs is unnecessary. Split search into:

- enumerate relation family and small AST skeleton;
- fill finite holes with SMT or direct finite optimization;
- derive symbolic observation signatures;
- score against sampled models;
- verify and add counterexample models;
- lower and certify the chosen instance.

This mirrors syntax-guided synthesis while retaining control over experimental objectives.

## 4. Symbolic fault model

For a bounded candidate AST, produce a symbolic expression:

```text
predicted_cycles(secret, latent_state, bounded_noise)
predicted_bucket(...)
predicted_relation_signature(...)
next_latent_state(...)
```

Use four-bit `BitVec` values for secret cells and small bit-vectors/enums for banks and phase. Be explicit about zero extension and shifts. The Python symbolic implementation should share generated S-box tables and profile constants with the public specification, not with private challenge data.

## 5. Pair-separating CEGIS

### 5.1 Initial pair

Obtain two diverse models from the current hypothesis formula. Diversity can maximize Hamming distance over secret bits plus a weighted distance over latent state/permutation.

### 5.2 Synthesis query

Find a grammar candidate `q` with different predicted signatures:

```text
H(m1) AND H(m2)
AND well_typed(q)
AND cost(q) <= budget
AND signature(q, m1) != signature(q, m2)
```

Minimize query cost after separation.

### 5.3 Committee verification

Evaluate `q` symbolically over a diverse model committee. If the largest outcome bucket is too large, find a pair inside it and add that pair as a counterexample requirement. Repeat until:

- the balance threshold is met;
- no bounded candidate can improve it;
- the synthesis timeout expires.

### 5.4 Pseudocode

```text
committee <- diverse_models(H, initial_size)
requirements <- choose_far_pair(committee)
best <- none

repeat:
    q <- synthesize_from_grammar(requirements, resource_bound)
    if unsat:
        increase grammar bound or return best
    if unknown:
        return best with timeout label

    partition <- evaluate(q, committee)
    best <- min_by_objective(best, q)
    bad_bucket <- largest_or_noisiest_bucket(partition)
    pair <- choose_far_pair(bad_bucket)

    if pair absent or partition meets threshold:
        verify q against extra models and return

    requirements.add(separate(pair))
    committee.add(pair.models)
```

This is a CEGIS-shaped process: a synthesizer proposes a candidate satisfying current examples, and a verifier supplies model counterexamples [R9].

## 6. Information objectives

### 6.1 Exact finite candidate set

If all models can be enumerated and the prior is uniform, expected information gain is

\[
I(K;O_q)=H(K)-\sum_o p(o)H(K\mid O_q=o).
\]

For deterministic signatures this reduces to the entropy of partition sizes.

### 6.2 Sampled candidate set

For standard mode, estimate partition frequencies over diverse models. Report the committee size and effective sample strategy. Because solver-generated samples are not automatically uniform, call the result a `partition proxy`, not a Shannon-information estimate, unless a calibrated sampler/model counter is used.

### 6.3 Worst-case split

Minimize

\[
\max_o |C_o|,
\]

which is robust to an unknown prior and resembles generalized binary search.

### 6.4 Noise-aware score

A useful relation can still be poor if its predicted effects lie within the same quantization/noise region. Add a margin term:

\[
margin(q,m_i,m_j)=
\operatorname{distance}(Intervals(q,m_i),Intervals(q,m_j)).
\]

Prefer partitions with positive interval separation or a reasonable sequential-sampling cost.

### 6.5 Multiobjective order

Recommended lexicographic objective:

1. satisfy certificates and hard resource constraints;
2. minimize worst predicted partition;
3. maximize minimum observation margin;
4. minimize physical execution estimate;
5. minimize hard resets;
6. minimize AST/gas cost;
7. maximize KB novelty;
8. canonical hash tie-break.

Lexicographic optimization is easier to interpret than a fragile weighted sum. Z3 Optimize supports multiple objectives and soft constraints [R13].

## 7. Grammar growth

Use iterative deepening:

1. one `anchor-switch` cell, no context;
2. phase padding;
3. bounded repetition;
4. two-cell sequences;
5. fence and context lifting;
6. token/epoch switching;
7. state-identification prefix/suffix;
8. composed relations.

A synthesis timeout at one level does not prove no useful query exists. Record whether a level is `unsat`, `unknown`, or merely not attempted.

## 8. Lane-wise decomposition

The bank function is lane-local in tutorial/standard mode. Exploit this deliberately:

- maintain per-lane marginal candidate sets plus a global solver;
- prioritize unresolved lanes;
- synthesize cross-lane queries only for diagnostics or research profiles;
- combine lane solutions with an exact global uniqueness check.

Research mode with hidden permutation couples lanes. Use assignment variables `perm[i]`, an `Distinct` constraint, and symmetry breaking such as fixing the lexicographically smallest equivalent representation.

## 9. Query-by-committee

When model counting is unavailable:

1. generate several diverse satisfying assignments;
2. predict each candidate query's signature for all assignments;
3. select the query with highest disagreement and margin;
4. refresh the committee after each committed constraint.

Diverse models can be generated with iterative blocking and MaxSMT objectives that maximize distance from prior models. Do not assume the resulting committee is a posterior sample.

## 10. Counterexamples beyond models

The verifier can return several kinds of counterexample:

- two secret models not separated;
- a latent state causing the predicted margin to vanish;
- a bounded noise choice causing outcome overlap;
- a program input violating the architectural precondition;
- a smaller query with equal partition quality;
- a concrete VM execution disagreeing with the symbolic model.

Each counterexample refines a different part of synthesis. The last is a model-validation failure, not just another secret example.

## 11. Synthesis caching

Cache by:

```text
hypothesis fingerprint
state-model version
profile/semantic version
grammar bound
objective configuration
certificate policy
```

A weaker hypothesis can reuse an old query for scoring but not an old optimality claim. Symbolic expression DAGs should be memoized by canonical AST.

## 12. Optional SyGuS export

A benchmark exporter can encode finite experiment skeletons as SyGuS 2.1:

- functions to synthesize choose token, bank, epoch, and repeat count;
- grammar restricts choices;
- semantic constraints require signature separation for a fixed model committee;
- objective metadata remains outside standard SyGuS if necessary.

This creates standalone program-synthesis benchmarks and permits comparison with external solvers [R10].

## 13. Optional decoder synthesis

After many successful campaigns, synthesize a decision tree:

```text
node: execute certified relation instance
edge: oracle outcome
leaf: secret cell or candidate set
```

Optimize worst-case executions and tree size. Verify every leaf by symbolic enumeration over the profile's finite secret domain. A decoder is profile-specific and should not replace the adaptive solver in research mode.

## 14. Testing synthesis

- Tiny exhaustive domains where the optimal split is known.
- Differential evaluation of symbolic signatures against concrete SphinxVM diagnostic mode.
- CEGIS tests that require at least one counterexample refinement.
- Timeout/`unknown` propagation tests.
- Grammar type-safety and resource-bound tests.
- Deterministic tie-break tests.
- Negative test where no grammar query separates two observationally equivalent configurations.
- Fault-free profile test where predicted signatures are secret-independent.
