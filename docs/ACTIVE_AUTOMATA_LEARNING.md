# Active automata learning

## 1. Why a state learner is needed

Under soft reset, observations depend on persistent replay credit, phase, and cache state. Secret inference that assumes a fresh initial state becomes unsound. Explicitly carrying every concrete history is exact but makes query search and constraint solving expensive.

Active automata learning offers a middle layer: infer a finite Mealy-machine abstraction of observationally relevant hidden state from adaptive queries [R7, R8].

## 2. Learning target

A Mealy machine is

\[
\mathcal{M}=(Q,q_0,\Sigma,\Gamma,\delta,\lambda),
\]

with input symbols \(\Sigma\), output symbols \(\Gamma\), state transition \(\delta\), and output function \(\lambda\).

The target is not the entire VM. It is a macro-level abstraction of persistent microarchitecture under architecturally silent command sequences.

## 3. Input alphabet

Keep the alphabet finite and semantically meaningful. Candidate symbols:

- `SOFT_RESET`
- `HARD_RESET` when budget permits
- `DRAIN` (`FENCE` macro)
- `PHASE_STEP_1`, `PHASE_STEP_2`, `PHASE_STEP_3`
- `PROBE_CLASS(lane_class, token_class, epoch, anchor)`
- `MEASURE(relation_template_id, finite_hole_class)`

Raw tokens and lanes can make the alphabet too large. Start with a campaign-selected abstraction and refine it when counterexamples show aliasing.

## 4. Output alphabet

Raw timing buckets are noisy and can create a huge/stochastic alphabet. Prefer output symbols such as:

```text
PUBLIC_OK
REL_EQUAL
REL_GREATER
REL_LESS
REL_INCONCLUSIVE
TRANSPORT_ERROR
```

A state-learning membership query executes a sequence using a configured repeated-sampling policy and returns a discretized symbol sequence. The discretizer version is part of the learned-model identity.

For research extensions, AALpy supports stochastic models, but the first milestone should learn a deterministic abstraction after robust discretization [R8].

## 5. Membership queries

A membership query executes an input word from a known start condition. With hard reset:

```text
hard_reset; symbol_1; ...; symbol_n
```

When hard reset is unavailable or expensive, prepend a known homing/access sequence and carry uncertainty over possible start states. Do not pretend ordinary soft reset is a global reset.

Membership-query caching is valid only when:

- the same challenge/profile/model version is used;
- start-state preparation is equivalent;
- deterministic seed/noise policy matches;
- no target drift is detected.

## 6. Equivalence-query approximation

Real black-box systems do not provide a true equivalence oracle. Approximate it with a portfolio:

- W/Wp/HSI-style conformance sequences when a state bound is plausible;
- random walks biased toward uncovered transitions;
- transition-cover plus distinguishing suffixes;
- relation-guided sequences that maximize disagreement between the learned model and symbolic fault model;
- solver-generated candidate counterexamples;
- replay of sequences with unstable output.

A returned counterexample is a sequence whose observed output differs from the hypothesis. It refines the learner and may invalidate state-conditioned secret constraints.

## 7. Homing and distinguishing sequences

### Distinguishing sequence

A suffix distinguishes two candidate states when their output traces differ. Adaptive distinguishing sequences branch on observed outputs and can be shorter than one fixed suffix.

### Homing sequence

A homing sequence need not reveal the initial state immediately; after observing its output, the resulting state is known. This is useful when reset preserves hidden state.

### Integration

The synthesizer can request:

```text
identify current state with confidence
reach a state where guard is active
separate state hypotheses q1/q2
produce a prefix whose final state has a stable measurement margin
```

The learner returns a sequence plus evidence and cost. The relation engine then composes the sequence with the measurement, subject to entry/exit certificates.

## 8. Interaction with secret inference

Secret and state are coupled: output transitions depend on the secret, while the state learner normally assumes one fixed target. A practical staged strategy is:

1. use hard-reset experiments to recover enough secret structure in tutorial/standard mode;
2. learn state per fixed challenge without trying to generalize across secrets;
3. condition symbolic state transitions on remaining secret candidates;
4. alternate state counterexamples and secret constraints;
5. optionally learn a family model parameterized by secret equivalence classes.

Avoid pooling traces from different challenge secrets into one Mealy target unless the secret is explicitly part of the state.

## 9. Versioning and retraction

Every learned model has:

- abstraction version;
- input/output alphabets;
- learner algorithm/options;
- membership-query cache digest;
- conformance test evidence;
- known counterexamples;
- state/transition coverage.

A constraint that depends on learned state `q` stores this model ID. If a counterexample splits `q`, re-evaluate or retract the constraint. The hypothesis store needs named assumptions so a model-version group can be disabled without rebuilding every independent hard-reset constraint.

## 10. State abstraction quality metrics

- number of states/transitions;
- counterexamples per equivalence round;
- membership and conformance queries;
- prediction accuracy on held-out sequences;
- fraction of secret-inference batches using exact versus learned state;
- constraint retraction count;
- average homing/access-sequence cost;
- observation nondeterminism after discretization.

A smaller machine is not automatically better. Prefer the smallest model that passes the configured conformance budget and supports stable inference.

## 11. Planned implementation

Wrap AALpy behind project interfaces:

```python
class StateLearner(Protocol):
    def observe(self, sequence: InputWord, outputs: OutputWord) -> None: ...
    def hypothesis(self) -> LearnedMachine: ...
    def access_sequence(self, state: StateId) -> InputWord | None: ...
    def distinguish(self, states: frozenset[StateId]) -> AdaptiveSequence | None: ...
    def find_counterexample(self, budget: Budget) -> Counterexample | None: ...
```

Provide a fake learner for deterministic tests and a one-state learner for hard-reset campaigns.

## 12. Research variants

- Compare L*, TTT, and discrimination-tree learners.
- Learn a stochastic Mealy/Markov decision abstraction directly.
- Jointly synthesize the input alphabet from secret-candidate disagreements.
- Use active learning to infer the fault model, not only hidden state.
- Learn register automata if tokens must remain data parameters instead of finite classes.
- Compare explicit history constraints against learned abstraction in solver time and recovery accuracy.

## 13. Safety checks

State learning must not become a path around the public protocol. Membership queries are ordinary documented VM commands. No memory snapshots, debugging APIs, private diagnostics, or process instrumentation are permitted.
