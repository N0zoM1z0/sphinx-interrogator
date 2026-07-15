# Interrogation testing design

## 1. From metamorphic tests to an interrogation

The oracle problem appears when a test's correct output is unavailable or expensive to compute. Metamorphic testing addresses it by relating outputs from transformed inputs [R3, R4]. Interrogation testing adds two ideas particularly useful here [R1]:

- use a richer response than one Boolean verdict;
- retain a diverse knowledge base of prior queries and responses so future tests can build on accumulated evidence.

Sphinx Interrogator applies this to a hidden-state machine. The “suspect” is not asked “what is the secret?” It is asked sequences of questions whose answers must remain mutually consistent with the public semantics, the fault-free leakage contract, and one hidden configuration.

## 2. Knowledge representation

### 2.1 Query node

A query node is keyed by `(canonical_program, public_input, reset/history abstraction, profile version)`. Its observations are not folded into the key because repeated executions and state-model revisions remain distinct evidence.

Features include:

- AST production histogram;
- instruction/control-flow summary;
- lanes/tokens/epochs/anchors used;
- phase and repetition summary;
- static cycle/gas vector;
- relation ancestry;
- learned-state entry/exit label;
- observation symbol/distribution;
- candidate partition signature.

### 2.2 Relation edge

A hyperedge links a source node to all follow-ups. It records the expected relation and the actual response. Edges may be composed, reduced, replayed, or invalidated.

### 2.3 Response richness

The stored response contains:

- public output and status;
- raw bucket samples with order and reset metadata;
- normalized intervals;
- relation decision and confidence;
- architectural-certificate result;
- fault-free-certificate result;
- extracted formula;
- implied/excluded candidate summaries;
- unsat-core membership;
- state-learner counterexample status;
- novelty and retention decision.

## 3. Main algorithm

```text
INPUT: public profile, challenge endpoint, budgets, root seed
OUTPUT: recovery result and auditable campaign artifacts

KB <- empty knowledge graph
H  <- domain constraints
L  <- initial one-state learner or exact reset model
insert certified seed queries into KB frontier

while budgets remain and H does not imply a unique secret:
    mode <- choose among inference, state learning, calibration, replay, reduction
    source <- select KB node/frontier according to mode
    candidates <- generate typed relation instances from source
    candidates += synthesize discriminator from sampled models of H
    q <- rank candidates by information, novelty, cost, and noise risk

    if q lacks valid certificates or preconditions:
        reject q with provenance
        continue

    batch <- create randomized paired/repeated schedule(q, L)
    records <- execute batch through black-box protocol
    persist records before analysis

    if architectural relation fails:
        quarantine q and relation implementation
        create model/debugging issue artifact
        continue

    decision <- relation oracle(records)
    update state learner with input/output sequence

    if decision is informative:
        c <- extract exact/bounded/soft constraint
        trial <- H plus c
        if trial inconsistent:
            diagnose with unsat core and replay
        else:
            commit c and measure candidate reduction

    score novelty and add/age KB frontier entries

    if decision is high-value and reproducible:
        minimize the relational witness and reverify it

return exact unique result, best weighted result with caveat, or unresolved summary
```

## 4. Query selection

Selection is a contextual bandit-like policy with explicit research modes rather than an opaque learned model.

### 4.1 Modes

- `infer`: maximize predicted candidate reduction.
- `learn-state`: maximize disagreement between learned-state hypotheses.
- `calibrate`: estimate noise, guard activation, or relation reliability.
- `replay`: revalidate constraints with high solver influence.
- `reduce`: minimize an existing high-value witness.
- `diversify`: fill uncovered grammar/relation/state regions.

### 4.2 Source score

A source-node score can combine:

\[
S(n)=w_1\,frontierNovelty+w_2\,pastGain+w_3\,relationPotential
+w_4\,stateUncertainty-w_5\,cost-w_6\,localDensity.
\]

Use normalized bounded components and log every component. Do not hide a hard-to-debug neural policy in the first implementation.

### 4.3 Candidate ranking

For each candidate relation instance:

- verify certificate/preconditions;
- predict output signatures for a diverse model committee;
- estimate partition balance and inconclusive risk;
- estimate required repetitions;
- check budget and state reachability;
- compute structural/semantic novelty;
- penalize dependence on low-confidence learned states.

A deterministic tie-break keeps campaigns replayable.

## 5. Diversity and local-optimum avoidance

Interrogation testing benefits from keeping diverse queries rather than recursively mutating only the latest success [R1]. The project should maintain diversity across:

- relation families;
- lanes and epochs;
- AST forms and control flow;
- phase contexts;
- candidate partition signatures;
- observation symbols;
- learned states/transitions;
- constraint forms;
- proof methods.

### TTL policy

Each active node starts with a base TTL. Expanding it consumes one unit. Novel results replenish it; duplicate or inconclusive results do not. A node with zero TTL leaves the active frontier but is not deleted. A periodic reservoir rule retains a small sample of old low-density nodes so the search can revisit abandoned regions.

### Novelty implication check

A constraint is semantically novel only if `H => C` is not already valid. Check by solving `H AND NOT C`. Timeouts yield `unknown`, not “novel.” Because implication checks can dominate runtime, use a cheap syntactic cache before invoking the solver.

## 6. Trick queries

A trick query is a transformation whose expected relation is deliberately easy to establish but whose response challenges a prior model assumption.

Examples:

- add static-cost-normalized padding to test phase interpretation;
- replay under hard reset to distinguish stochastic noise from state drift;
- alpha-rename setup registers to test fault confinement;
- reverse two independent cells to test a stateless replay model;
- insert `FENCE` to test whether a violation depends on persistent replay credit;
- use a token pair predicted equivalent by all current secret models to test model completeness.

A trick query may produce no direct secret constraint and still be valuable by invalidating a state abstraction or fault hypothesis.

## 7. Knowledge-base consistency

The KB is not automatically consistent merely because the SMT store is satisfiable. Track several consistency layers:

1. protocol/schema validity;
2. public architectural relation;
3. certificate compatibility with semantic version;
4. observation/statistical decision validity;
5. constraint satisfiability;
6. learned-state model consistency;
7. replay reproducibility.

An edge can be active at one layer and quarantined at another. Reports should distinguish them.

## 8. Relational witness reduction

Ordinary reducers seek a smaller input that preserves a test predicate [R16, R17]. Here the predicate is multi-part:

```text
valid source/follow-up family
AND architectural certificate passes
AND fault-free relation certificate passes
AND public violation reproduces
AND extracted constraint retains target consequence
```

### Reduction order

1. remove irrelevant ordinary instructions symmetrically;
2. reduce history prefix while retaining learned/exact state;
3. lower repetitions and samples;
4. remove matched probe cells;
5. simplify padding and fences;
6. shrink token/anchor constants toward canonical values;
7. collapse composed relations to primitive ones;
8. reduce public input.

Use a best-first queue ordered by `(physical executions, gas, AST nodes, history length, lexical form)`. Cache candidate predicates by canonical family hash.

### Constraint preservation options

- `equivalent`: reduced formula iff original formula under domain constraints;
- `implies-core`: reduced formula implies a selected core consequence;
- `same-partition`: identical signature over a fixed candidate committee;
- `same-true-witness`: true challenge configuration satisfies both; allowed only in white-box development, not black-box evaluation.

Release witnesses should use `equivalent` or `implies-core` without access to the secret.

## 9. Model interrogation

The system should interrogate not only SphinxVM but also its own current hypothesis.

Given a candidate query, ask:

- Which surviving model pairs does it separate?
- Which models predict an inconclusive bucket overlap?
- Which latent-state assumptions dominate the result?
- Is its extracted formula already implied?
- Does a smaller query have the same partition?
- Can any model produce an observation outside the oracle's declared outcome set?

These solver questions create counterexamples that refine the query before spending execution budget.

## 10. Campaign audit trail

Every decision should be replayable from events such as:

```json
{"kind":"selected","query_id":"q17","score":{...},"seed":41}
{"kind":"scheduled","logical_batch":"b9","order":"ABBA","repetitions":8}
{"kind":"observed","request_id":"r91","bucket":37}
{"kind":"oracle","edge_id":"e5","decision":"greater","method":"bounded"}
{"kind":"constraint-added","constraint_id":"c12","gain_bits_est":0.73}
{"kind":"state-counterexample","model_version":"m3","sequence":[...]}
{"kind":"witness-reduced","from":"e5","to":"e18","cost_delta":-14}
```

A report generator reconstructs the campaign from this append-only stream and verifies artifact hashes.

## 11. Failure modes and remedies

| Failure | Symptom | Remedy |
|---|---|---|
| Local mutation trap | many near-duplicate queries | TTL, density penalty, fresh synthesis |
| Unsound relation | true secret violates extracted formula | certificate/extractor differential tests; quarantine |
| Quantization blindness | many equal buckets | synthesize phase/repetition/context; change pair |
| Noise overconfidence | frequent unsat cores | sequential testing, soft constraints, replay |
| Hidden-state aliasing | same query has multimodal outcomes | hard reset, history constraints, active learner |
| Solver stagnation | expensive model enumeration | lane-wise decomposition, diverse sampling, caching |
| Trivial leakage | one query collapses most candidates | recalibrate bucket/fault, one-shot MI audit |
| Leak too weak | no query beats random | widen grammar/amplification or adjust fault strength |
