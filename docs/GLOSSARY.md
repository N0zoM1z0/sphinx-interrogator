# Glossary

**Architectural state** — Programmer-visible registers, memory, flags, control state, and public output.

**Microarchitectural state** — Hidden implementation state such as vault bank history, scheduler phase, replay credit, and cache tag.

**System A / SphinxVM** — The synthetic target containing the hidden configuration and injected fault.

**System B / Interrogator** — The black-box analysis, learning, and synthesis system attempting recovery.

**Relation oracle** — A checker over several executions whose expected outputs satisfy a known relation; here it also supports secret-constraint extraction.

**Metamorphic relation** — A necessary relation between source and follow-up executions when a direct expected output is unavailable.

**Interrogation testing** — A testing method that uses rich responses, transformations, and a diverse knowledge base of prior queries to force inconsistencies.

**Hyperproperty** — A property of sets of execution traces, used for relational security properties such as noninterference.

**Self-composition/product program** — A construction that reasons about several executions together as one verification problem.

**Leakage contract** — An explicit declaration of which observations may depend on secrets; the fault-free model should satisfy it.

**Observation refinement** — Making an observation model more discriminating to expose hidden behavior or model inadequacy.

**CEGIS** — Counterexample-guided inductive synthesis: synthesize from current examples, verify, add counterexamples, repeat.

**SyGuS** — Syntax-guided synthesis: constrain candidate programs with a grammar.

**Probe grammar** — The typed grammar from which Interrogator synthesizes related experiment programs.

**Candidate/hypothesis set** — Secret and latent-state assignments consistent with committed constraints.

**Model committee** — A finite set of diverse satisfying assignments used as a proxy for candidate partitions.

**Information gain** — Reduction in uncertainty caused by an observation; exact only under stated sampling/prior assumptions.

**Logical query family** — One related experiment considered by the oracle, potentially requiring many physical executions.

**Physical execution** — One protocol request that runs one concrete program.

**Hard reset** — Reset to a unique architectural and microarchitectural initial state.

**Soft reset** — Reset architectural state while preserving profile-declared hidden state.

**Homing sequence** — An input sequence after which the resulting state can be identified from observed outputs.

**Distinguishing sequence** — An input sequence producing different outputs from different possible states.

**Mealy machine** — A finite-state machine whose outputs are associated with transitions.

**Knowledge base (KB)** — The persistent graph of queries, relations, responses, constraints, and state-model evidence.

**Certificate** — Evidence that a concrete relation instance satisfies architectural and fault-free proof obligations.

**Normalizer** — A function that removes public static cost or maps observations to a common relational domain.

**Extractor** — A function translating an oracle outcome into exact, bounded, or soft logical constraints.

**Constraint quarantine** — Disabling suspect evidence while retaining its provenance and transcript.

**Witness reduction** — Shrinking a related experiment while preserving validity, violation, and a logical consequence.

**Quantization** — Mapping exact cycles into coarse public buckets.

**MaxSMT** — Optimization that maximizes the weight of satisfied soft logical assertions while retaining hard constraints.

**Boundary audit** — Tests ensuring System B cannot access private target data or diagnostic interfaces.

**ExecPlan** — A living, self-contained implementation plan maintained by a coding agent for a complex milestone.
