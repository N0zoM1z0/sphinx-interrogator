# System B: Interrogator

## 1. Purpose

Interrogator is an adaptive black-box analysis system. Its output is not merely a guessed secret; it is a recovery result accompanied by a transcript, a constraint provenance graph, relation certificates, candidate-set evidence, and reproducibility metadata.

## 2. Public knowledge and prohibited knowledge

Interrogator may know:

- the ISA and probe DSL;
- public profile limits;
- the family of bank-mapping and fault equations;
- the reset contract;
- public observation schemas;
- relation templates and their fault-free proofs.

It may not know or access:

- concrete secret values;
- hidden permutations or salts unless designated public;
- concrete microstate before a run;
- exact jitter samples;
- VM diagnostic traces;
- the private challenge file;
- implementation-only helper functions from the Rust crate.

A solution that reconstructs the secret by importing or reusing private target code is invalid even if it produces the right bits.

## 3. Core abstractions

### 3.1 Query

```python
@dataclass(frozen=True)
class Query:
    reset: ResetPolicy
    program: Program
    public_input: PublicInput
    logical_seed: int
```

A query is canonicalizable. Physical repetitions derive seeds from the campaign root and logical query ID.

### 3.2 Relation instance

```python
@dataclass(frozen=True)
class RelationInstance:
    template_id: str
    source: Query
    follow_ups: tuple[Query, ...]
    certificate: CertificateRef
    predicted_partitions: PartitionSummary | None
```

### 3.3 Observation summary

```python
@dataclass(frozen=True)
class ObservationSummary:
    raw_batch_ids: tuple[str, ...]
    normalized_intervals: tuple[Interval, ...]
    effect_estimate: float
    confidence: float | None
    decision: Literal["equal", "less", "greater", "violation", "inconclusive"]
    method: str
```

### 3.4 Constraint artifact

```python
@dataclass(frozen=True)
class ConstraintArtifact:
    formula: ConstraintExpr
    strength: Literal["hard", "bounded", "soft"]
    weight: float | None
    assumptions: tuple[str, ...]
    provenance: tuple[str, ...]
    model_version: str
```

## 4. Campaign loop

```text
initialize public profile, protocol client, KB, hypothesis store
add domain constraints for secret and optional latent state
seed KB with simple certified relations

until stop condition:
    choose source/strategy based on coverage and candidate uncertainty
    synthesize or instantiate a related query family
    verify static preconditions and certificate
    schedule paired executions with reset and randomized order
    normalize results and run the relation oracle
    extract constraints or mark inconclusive
    check consistency; quarantine suspect evidence if needed
    compute exact/sampled candidate reduction
    store diverse/high-value evidence in KB
    optionally reduce and replay the witness
    update state learner and query policy

produce unique secret, candidate set, or honest unresolved report
```

Stop conditions include verified uniqueness, posterior confidence threshold, budget exhaustion, repeated solver `unknown`, detected model mismatch, or target/process failure.

## 5. Interrogation knowledge base

### 5.1 Graph model

Nodes represent canonical queries plus execution contexts. Directed hyperedges represent relation instances from one source to one or more follow-ups.

A node contains:

- AST and canonical hash;
- static resource vector;
- reset/history context;
- public output;
- observation batches and summaries;
- learned-state labels;
- relation coverage bitmap;
- candidate split signature;
- age and time-to-live.

An edge contains:

- transformation stack;
- certificate ID/version;
- expected architectural relation;
- expected fault-free observation relation;
- oracle decision and confidence;
- emitted constraints and provenance;
- estimated/actual entropy reduction;
- reduction lineage.

### 5.2 Diversity

A new item is retained when it contributes at least one of:

- unseen relation/template coverage;
- unseen AST feature combination;
- unseen normalized observation signature;
- a new learned-state transition;
- a constraint not implied by the current store;
- material candidate-set reduction;
- a smaller witness for the same logical consequence;
- a reproducible model contradiction.

Novelty should not be a single scalar hash distance. Use a lexicographic or Pareto policy over semantic and structural features.

### 5.3 Time-to-live

Each node receives a TTL. Selection spends TTL; successful novelty replenishes it. Expired low-value leaves are removed from the active frontier but remain in the append-only transcript. This follows the spirit of interrogation testing: preserve a rich history while avoiding local clusters that dominate future transformations.

## 6. Seed generation and relation expansion

Initial seeds should be small certified programs covering every lane, epoch, anchor bank, and phase. They are not expected to recover the secret alone.

Expansion strategies:

- mutate one typed hole in an existing relation instance;
- compose a source program with a neutral context;
- switch relation families while reusing a useful core probe;
- amplify a weak witness by bounded repetition;
- synthesize a fresh experiment against two candidate models;
- generate a distinguishing suffix from the current state learner;
- replay a high-value witness to check drift.

## 7. Constraint extraction

### 7.1 Exact mode

For exact cycles and known initial state, compile the concrete delta relation directly:

```text
observed_delta == predicted_fault_delta(secret, query_pair)
```

Use bit-vectors for secret cells and finite enumerations for latent state.

### 7.2 Quantized bounded mode

A returned bucket `b` of width `h` implies an interval for pre-quantized cycles. With bounded noise `[-n,n]`:

```text
h*b - n <= true_cycles <= h*(b+1)-1 + n
```

For a pair, introduce separate nuisance variables unless the profile explicitly declares common-mode noise. Eliminate them where cheap or retain them as bounded integers.

### 7.3 Stochastic mode

Map a statistical decision to a weighted predicate such as `delta_a > delta_b`. Weight can be a monotone transform of the log-likelihood ratio, capped to prevent one batch from dominating. Store the raw statistic and calibration method.

### 7.4 Latent state

Under hard reset, initial state is a constant. Under history-explicit mode, introduce state variables connected by exact transition constraints. Under learned-abstraction mode, state labels are assumptions; constraints remain associated with the machine-model version and are retractable.

## 8. Hypothesis management

### 8.1 Exact store

Use a Z3 `Solver` for hard constraints and an `Optimize`/MaxSMT layer for soft constraints. Keep a project-owned expression IR so constraints can be serialized and translated to another backend later.

### 8.2 Candidate enumeration

For small tutorial spaces, enumerate all models. For standard mode:

- enumerate up to a cap with blocking clauses;
- ask for diverse models by maximizing Hamming distance from previous samples;
- sample per-secret-cell marginals;
- derive lower/upper cardinality estimates;
- use exact uniqueness checks: assert `secret != candidate` and test unsatisfiable.

Never infer uniqueness merely because repeated `model()` calls return the same assignment.

### 8.3 Inconsistency repair

When hard constraints become unsatisfiable:

1. obtain an unsat core over named evidence assumptions;
2. replay the smallest/highest-risk evidence in the core;
3. check relation certificate versions and reset assumptions;
4. downgrade statistically derived constraints to soft if policy allows;
5. invalidate constraints tied to superseded learned-state models;
6. report unresolved model mismatch if consistency cannot be restored.

## 9. Query synthesis

### 9.1 Grammar

The grammar includes:

- relation family;
- lane variables;
- token constants or expressions;
- epoch;
- anchor banks;
- phase-control padding;
- order and context;
- repeat count from a bounded set;
- reset policy;
- optional distinguishing prefix/suffix.

The AST cost is a weighted sum of instruction count, gas, physical repeats, hard resets, and estimated variance.

### 9.2 Backends

1. **Template enumeration + SMT holes:** required first backend.
2. **CEGIS backend:** required main backend; verifies partition quality against counterexample models.
3. **SyGuS exporter:** optional but desirable for reproducible synthesis benchmarks.
4. **Rosette backend:** optional research backend.

### 9.3 Selection objectives

The selector balances:

- expected entropy reduction;
- worst-partition size;
- probability of an inconclusive statistical result;
- cost and remaining budget;
- novelty relative to the KB;
- state-identification value;
- certificate strength.

Use deterministic tie-breaking by canonical query hash.

## 10. Active state learning

The input alphabet should be abstract, not every raw program. Symbols can represent short certified macro-programs: `set_phase_0`, `probe_class(lane,epoch,anchor)`, `drain`, `soft_reset`, and `measure`.

Outputs should be discretized relation signatures rather than raw timestamps. The abstraction version and thresholds are part of the model identity.

The learner supplies:

- a predicted state after a command prefix;
- a homing/reset sequence where possible;
- distinguishing suffixes between current state candidates;
- state-transition coverage;
- a counterexample when observed output disagrees with the hypothesis.

Any state-dependent secret constraint must say whether it used exact history or a learned state label.

## 11. Witness reduction

A reducer starts from a relation family, not from one flat byte string. It may:

- delete matched instructions from both sides;
- shrink repeat counts;
- simplify neutral contexts;
- reduce tokens and anchors;
- shorten history prefixes;
- replace a composed relation with a primitive one;
- remove samples while preserving the confidence threshold.

A candidate reduction is accepted only if:

1. the architectural relation still verifies;
2. the fault-free observation relation still verifies;
3. the actual violation reproduces;
4. the extracted constraint is equivalent to, or at least implies a configured core consequence of, the original;
5. resource cost decreases lexicographically.

## 12. Recovery result

A final result should include:

```json
{
  "status": "unique",
  "secret_hex": "3a71...",
  "configuration": {"permutation": [0, 2, 1, 3]},
  "proof": {
    "alternative_model_check": "unsat",
    "hard_constraints": 84,
    "soft_constraints": 12,
    "quarantined_constraints": 2
  },
  "budget": {"logical_queries": 137, "physical_executions": 1844},
  "artifacts": {"transcript": "...", "report": "..."}
}
```

If unique recovery is not established, return a candidate summary and reason. Do not silently print the current best model as the secret.
