# Architecture

## 1. Design constraints

The architecture is organized around four non-negotiable constraints.

1. **Black-box integrity.** Interrogator receives only documented protocol responses.
2. **Relational legitimacy.** Every inference-producing experiment carries a certificate for its architectural and fault-free observation relation.
3. **Explicit uncertainty.** Noise, latent state, approximation, and solver timeouts appear in data structures rather than being hidden in control flow.
4. **Reproducibility.** A campaign is replayable from a profile, challenge commitment, root seed, protocol transcript, and tool versions.

## 2. Deployment topology

```text
+---------------------------+       JSONL        +-------------------------+
| Interrogator process      | <----------------> | SphinxVM process        |
|                           | stdin/stdout pipe   |                         |
| - campaign controller     |                    | - private challenge     |
| - relation engine         |                    | - architectural machine |
| - knowledge base          |                    | - microarchitecture     |
| - SMT/MaxSMT              |                    | - fault + noise model   |
| - query synthesizer       |                    | - public protocol       |
| - state learner           |                    |                         |
+---------------------------+                    +-------------------------+
           |
           v
+---------------------------+
| append-only run directory |
| transcript, models,       |
| witnesses, reports        |
+---------------------------+
```

For challenge runs, the VM receives a private file descriptor or path inaccessible to Interrogator. Interrogator receives a public profile and a cryptographic commitment sufficient to identify the challenge, not to test guesses offline. A separate judge command may return only `accepted` or `rejected` after the campaign.

## 3. System A modules

The Rust crate should keep the following conceptual layers separate:

- `isa`: instruction and program types, validation, static cost.
- `architecture`: architectural state and small-step semantics.
- `microcode`: expansion of instructions into micro-ops.
- `microarchitecture`: vault banks, scheduler phase, replay state, micro-op cache.
- `fault`: pure function that modifies scheduling decisions; selectable `off`, `reference`, and mutation variants.
- `noise`: quantization and seeded noise, isolated from core semantics.
- `challenge`: private secret generation/loading and public commitment.
- `protocol`: versioned request/response types.
- `server`: JSONL loop with resource limits and structured errors.

The implementation must support three evaluators sharing the same instruction definitions:

1. architectural-only semantics;
2. fault-free cycle semantics;
3. faulty concrete semantics.

They must not be implemented as boolean flags threaded through one large function. Separate types make accidental use of the wrong semantics visible.

## 4. System B modules

The Python package should expose stable internal interfaces:

```text
ast / parser
    -> relation templates
        -> experiment plans
            -> harness / sampler
                -> observation summaries
                    -> oracle decisions
                        -> constraint extractor
                            -> hypothesis store
                                -> query synthesizer

knowledge base <------------------------------------------+
state learner  <------------------------------------------+
reducer        <------------------------------------------+
```

### 4.1 Query AST

The AST is immutable and canonicalizable. Each node reports static resources, architectural effect summary, and grammar cost. Canonical serialization is used for structural hashes and deterministic noise seeds where configured.

### 4.2 Relation registry

A relation implementation provides:

- a stable name and version;
- source precondition;
- follow-up constructor or synthesis grammar;
- architectural relation checker;
- fault-free observation relation;
- normalizer;
- exact and noisy extractors;
- minimization invariants;
- generated-test strategy.

### 4.3 Harness

The harness owns process lifecycle, request IDs, timeouts, reset scheduling, randomized pair ordering, retries for transport failures, and raw transcript persistence. It does not interpret a timing difference as evidence; that belongs to the oracle/statistics layer.

### 4.4 Knowledge base

Use an append-only event log plus an indexed materialized view. SQLite is appropriate for the first implementation. Core records are:

- `QueryNode`;
- `ExecutionBatch`;
- `RelationEdge`;
- `OracleDecision`;
- `ConstraintArtifact`;
- `CandidateSnapshot`;
- `StateModelVersion`;
- `ReducedWitness`;
- `CampaignEvent`.

Store schemas and protocol payloads as versioned JSON. Keep solver expressions in a portable project AST or SMT-LIB text plus a semantic version; do not pickle Z3 objects.

### 4.5 Hypothesis store

The hypothesis store offers:

- exact satisfiability and implication;
- model enumeration with blocking clauses and limits;
- diverse model sampling;
- approximate candidate cardinality;
- unsat-core provenance;
- weighted soft constraints;
- snapshots and rollback/quarantine;
- uniqueness and confidence checks.

Every added constraint has a provenance edge back to concrete transcript records.

### 4.6 Synthesizer

The first implementation uses bounded template enumeration plus SMT-filled holes. A later backend may emit SyGuS 2.1 or use Rosette. Backends implement the same `SynthesisBackend` protocol and return a proof-carrying `CandidateExperiment` with cost, assumptions, predicted partitions, and verification evidence.

### 4.7 State learner

The learner maps concrete input sequences to a finite alphabet and quantized output symbols. The M8 implementation is replaceable: a trivial one-state model for hard-reset mode, a bounded exact-history Mealy model, and an AALpy-backed deterministic L* Mealy learner for soft-reset mode. Learned models serialize with membership-cache digests, conformance metrics, access/distinguishing support, and counterexamples that retract state-conditioned constraint groups.

## 5. Data flow for one logical interrogation

1. `Selector` chooses a source node or asks for a fresh synthesized seed.
2. `Synthesizer` proposes a relation instance and predicts candidate partitions.
3. `RelationRegistry` validates preconditions and proof-certificate availability.
4. `Sampler` builds an execution schedule such as `ABBA`, with resets and repetition blocks.
5. `Harness` executes requests and persists raw replies.
6. `Normalizer` removes static costs and converts buckets to intervals/distributions.
7. `Oracle` decides equality/order/violation/inconclusive.
8. `Extractor` creates hard or soft constraints with latent variables.
9. `HypothesisStore` checks consistency and computes information gain.
10. `KnowledgeBase` retains, links, scores, or ages the nodes.
11. `Reducer` may minimize a high-value violation asynchronously within the same campaign process; reduced evidence is reverified before use.
12. `CampaignController` updates stopping criteria and selects the next interrogation.

## 6. Run directory

A campaign should produce:

```text
runs/<campaign-id>/
  manifest.json
  public-profile.toml
  transcript.jsonl
  events.jsonl
  knowledge.sqlite3
  constraints/
  models/
  witnesses/
  learned-machines/
  reports/
  logs/
```

`manifest.json` records the repository revision, tool versions, challenge commitment, root seed, operating profile, command line, start/end times, and completion status. Private challenge material must never be copied into the run directory.

## 7. Failure containment

- A malformed program is a typed protocol error, not a VM crash.
- A solver timeout returns `unknown` and cannot be treated as `unsat`.
- An inconclusive statistical test emits no hard constraint.
- A failed architectural relation quarantines the relation implementation and the batch.
- A transport retry receives a new request ID but retains a logical-batch ID.
- A learned state model is versioned; constraints depending on an invalidated model are rolled back.
- An unsatisfiable hypothesis store triggers provenance-guided diagnosis before any recovery result is reported.

## 8. Trust base

The initial trusted computing base is intentionally small:

- parsers and schema validators;
- architectural reference semantics;
- relation proof checker;
- fault-free cost semantics;
- Z3 and the exact bit-vector encoding;
- campaign transcript integrity.

The query heuristic, approximate model counter, active learner, and reducer are untrusted optimizers. Their suggestions must be checked by trusted components before they affect a recovery claim.
