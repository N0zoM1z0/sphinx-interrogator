# Codex task specification

## 0. Status and interpretation

This document is the normative implementation contract for the repository. `MUST`, `MUST NOT`, `SHOULD`, and `MAY` have their usual requirements meaning. Design documents explain rationale; when implementation details conflict, this specification wins unless a recorded human decision changes it.

The initial archive contains a design and scaffold, not a completed system. Do not satisfy this task by adding more placeholders, mock-only demos, or claims without executable evidence.

## 1. Product goal

Implement an end-to-end synthetic research platform with two strictly separated systems:

- **System A — SphinxVM:** a Rust cycle-accurate microcoded VM with a generated hidden configuration, architecturally silent probe instructions, a configurable guarded scheduler/replay fault, reset semantics, quantized/noisy timing, and a versioned JSONL server.
- **System B — Interrogator:** a Python black-box analysis agent that creates certified related programs, executes them through the public protocol, applies exact/bounded/statistical relation oracles, stores an interrogation knowledge graph, maintains SMT/MaxSMT hypotheses, synthesizes high-information experiments with CEGIS, optionally learns persistent hidden state, reduces witnesses, and reports auditable recovery results.

A user MUST be able to run a deterministic tutorial demonstration from a clean checkout and see a generated secret recovered exactly through black-box relational queries. A user MUST also be able to run a reproducible standard benchmark matrix and inspect raw/derived artifacts.

## 2. Required demonstration flows

### 2.1 Tutorial flow

A single root command MUST:

1. generate or select a seeded 16-bit tutorial challenge;
2. launch the release-mode SphinxVM server without diagnostics;
3. run Interrogator through the public process protocol;
4. recover a unique secret;
5. ask a separate judge for one final verification;
6. write a complete run directory and Markdown summary;
7. exit zero only when the result is exact and accepted.

Target command:

    just demo-tutorial

The output MUST include challenge ID/commitment, logical and physical query counts, the recovered secret after completion, uniqueness evidence, run-directory path, and final check status. It MUST NOT print target internals during recovery.

### 2.2 Standard benchmark flow

A command MUST execute the published evaluation seed list for the full system and required baselines, resume safely, and generate machine-readable/Markdown aggregate reports:

    just benchmark-standard

The command may support a smaller smoke matrix in ordinary CI and a full matrix in scheduled/manual CI. The distinction MUST be explicit.

### 2.3 Fault-free negative control

The same public interface with the injected fault disabled MUST not produce false exact recovery. The campaign MUST end unresolved or at a candidate set consistent with no leak. Any true secret used to evaluate the control is available only to the judge/evaluation harness.

## 3. Hard boundaries and non-goals

### 3.1 Black-box boundary

System B MUST communicate with System A only through the public JSONL protocol defined in `spec/`.

System B MUST NOT:

- import/link the Rust target as a Python/native library;
- read private challenge files, secret-bearing environment variables, target process memory, debug logs, core dumps, or diagnostic sockets;
- use target-source-only helper functions at runtime;
- request diagnostic fields through the public protocol;
- submit repeated guesses to the final judge as an oracle.

Cross-language tests MUST launch a separate target process. White-box tests MAY compare concrete and symbolic semantics in a dedicated test harness, but that code path MUST be unavailable to black-box campaigns and clearly labeled.

### 3.2 Synthetic-only scope

The repository MUST NOT implement collectors/adapters for real hardware, real cryptographic software, remote services, performance counters, cache attacks, speculative gadgets, power/EM traces, or third-party targets. All examples and challenge data MUST be generated locally.

### 3.3 No benchmark cheating

The implementation MUST NOT hard-code evaluation secrets, infer them from seeds exposed to System B, place them in public commitments, or use private state when selecting queries. Challenge generation MUST derive private configuration through a domain-separated generator unavailable to Interrogator.

### 3.4 Honest result statuses

Supported result statuses MUST distinguish at least:

- `unique_exact`;
- `candidate_set`;
- `ranked_soft`;
- `budget_exhausted`;
- `model_inconsistent`;
- `target_error`;
- `blocked`.

A current best model MUST NOT be labeled exact unless an alternative-secret query is unsatisfiable under the committed exact constraints.

## 4. Technology and repository requirements

### 4.1 Languages

- Rust 2021 edition for SphinxVM.
- Python 3.12 or newer compatible with the project configuration for Interrogator.
- JSON Lines + JSON Schema for the public process boundary.
- TOML for profiles and benchmark matrices.
- SQLite for the first materialized knowledge-base view, backed by append-only JSONL campaign events.
- Z3 bit-vectors/integers/Optimize for exact and soft inference.
- AALpy behind a project-owned interface for active automata learning.
- TLA+ and SMT-LIB/Python-Z3 checks for selected formal obligations.

A dependency may be replaced only with a recorded rationale and equivalent tests/interfaces.

### 4.2 Stable root commands

The final repository MUST implement and document:

    just bootstrap
    just fmt
    just fmt-fix
    just lint
    just unit
    just test
    just schema-check
    just verify-formal
    just demo-tutorial
    just benchmark-standard
    just boundary-audit

All commands MUST be noninteractive, return meaningful exit codes, and avoid requiring unpublished local files.

### 4.3 Reproducibility

Every source of nondeterminism MUST receive an explicit seed. Run manifests MUST capture:

- repository revision and dirty status;
- target/client binary/package versions;
- profile and schema hashes;
- public challenge ID and commitment;
- campaign root seed;
- strategy/baseline variant;
- command line and environment summary;
- start/end timestamps and completion status;
- toolchain/dependency versions;
- hashes of transcripts, constraints, models, witnesses, and reports.

## 5. System A — SphinxVM requirements

## 5.1 Module structure

The target crate SHOULD be split into modules equivalent to:

```text
architecture.rs
isa.rs
parser.rs
validate.rs
microcode.rs
microarchitecture.rs
fault.rs
noise.rs
profile.rs
challenge.rs
protocol.rs
server.rs
judge.rs
```

The exact filenames may differ, but architectural, fault-free, and faulty semantics MUST be distinct types/functions. One giant evaluator with hidden boolean switches is not acceptable.

## 5.2 Architectural state

Version 1 MUST implement:

- eight 16-bit registers;
- program counter and bounded program memory;
- `Z/N/C/V` flags or a documented equivalent;
- 256 16-bit data-memory words;
- bounded return stack;
- 64-bit public digest/output accumulator;
- halt/error status;
- gas counter.

The secret MUST NOT be readable through registers, memory, flags, digest, status, error text, instruction count anomalies outside the declared observation, or protocol metadata.

## 5.3 ISA

At minimum implement:

```text
MOVI, MOV
ADD, XOR, AND, OR, SHL, SHR
LOAD, STORE
CMP
JMP, JZ, JNZ
CALL, RET or omit CALL/RET with an ADR decision and equivalent bounded control flow
LOOP or verifier-approved bounded backward branch
MIXOUT
PROBE lane, token, epoch
ANCHOR bank, epoch
PAD amount
FENCE
HALT
```

Operand ranges MUST be validated. Arithmetic semantics MUST be total and documented. Programs MUST terminate through static validation plus gas enforcement.

`PROBE`, `ANCHOR`, `PAD`, and `FENCE` MUST preserve general registers, memory, flags, and public digest. They may change PC, gas, documented public static metrics, and hidden microstate.

## 5.4 DSL and canonicalization

Implement the grammar in `spec/probe-dsl.ebnf` with:

- comments and labels;
- deterministic formatting;
- stable AST serialization/canonical hash;
- informative location-aware errors;
- no macro expansion that can create unbounded code;
- a validator separate from parsing.

Rust is the authoritative parser for execution. Python MUST implement a compatible parser/AST or use an independently generated schema representation, but it MUST NOT call private target code. Cross-language golden fixtures MUST prove compatibility.

## 5.5 Architectural semantics

Implement a pure/mostly pure step function and program evaluator. Required properties/tests:

- deterministic for fixed program/public input;
- same final architecture across all secrets/profiles/fault variants;
- parser/formatter round trip;
- invalid programs never execute partially;
- gas exhaustion is structured and secret-independent;
- no panic on arbitrary bounded protocol input.

## 5.6 Microcode and fault-free timing

Every instruction MUST lower to documented micro-ops or an equivalent explicit internal representation. Vault instructions MUST use the same microcode path in fault-free and faulty semantics.

The fault-free scheduler MUST assign public-secret-independent normalized cost. Exact static cost MUST be computable from the validated program plus documented profile constants.

The implementation MUST expose a test-only fault-free evaluator but not its private trace through the public server.

## 5.7 Hidden configuration and bank mapping

Implement the public four-bit S-box specified in `docs/SYSTEM_A_SPHINX_VM.md`. For each probe:

```text
u    = secret[permutation[lane]] XOR token XOR salt[lane]
v    = SBOX4[u]
bank = (v >> (2 * epoch)) & 3
```

Profiles MUST declare the number of lanes/cells and whether permutation/salts are enabled. Private salts MAY be deterministically derived. Interrogator knows the mapping family and public S-box, not concrete private parameters.

Use typed small integers/newtypes and exhaustive unit tests for all inputs.

## 5.8 Microarchitectural state

At minimum:

- two-bit phase;
- optional last bank;
- two-bit replay credit;
- small micro-op cache tag/valid bit or a documented equivalent persistent feature.

Hard reset MUST establish one unique documented state. Soft reset MUST preserve exactly the profile-declared subset. State transition MUST be a pure reusable function shared conceptually by concrete and symbolic models.

## 5.9 Reference fault

Implement the guarded replay fault from `docs/SYSTEM_A_SPHINX_VM.md`:

```text
collision = secret_bank == public_anchor_bank
guard = phase == ((lane XOR token XOR epoch) & 3)
suppress = replay_credit == 3
fault_delta = 1 if collision and guard and not suppress else 0
```

Then update phase, replay credit, and last bank according to the documented transition. If implementation experiments show that exact constants make the standard profile unlearnable/trivial, adjust only through versioned profile/fault configuration and preserve the relation/model contracts.

Support at least:

- `off`;
- `reference`;
- one weaker mutation;
- one stronger/signed mutation for calibration.

Fault variants MUST change only hidden scheduling/timing state, never architectural output.

## 5.10 Observation and noise

The public response MUST expose only:

- status/public digest;
- quantized cycle bucket;
- bucket width;
- public static metrics needed by certified normalizers;
- budget counters and protocol metadata.

It MUST NOT expose exact pre-quantized cycles in challenge mode.

Implement profile-selectable:

- no noise;
- deterministic bounded seeded jitter;
- stochastic seeded bounded/heavy-tail-mixture jitter;
- quantization.

Noise seed derivation MUST be domain-separated from challenge-secret generation. Repeating a public seed identifier MUST NOT reveal the private secret generator state.

## 5.11 Profiles

Implement parse/validation for at least:

- `tutorial.toml`;
- `standard.toml`;
- `research.toml`;
- `fault_free.toml`.

Validate contradictory/unsafe settings. Public and private profile fields MUST be separate types/files so serialization cannot accidentally expose private fields.

## 5.12 Challenge generation and judge

Implement a development/evaluation CLI that creates:

```text
<challenge>/public/profile.toml
<challenge>/public/challenge.json
<challenge>/private/secret.bin or protected equivalent
<challenge>/private/config.toml
```

Public challenge data includes an identifier, profile hash, non-oracular commitment, protocol version, and budgets. The judge MUST accept one guess per configured campaign token or an equivalently non-abusable policy and return only accepted/rejected plus public metadata. Post-run reveal MAY be supported for development artifacts but MUST be a separate explicit action.

## 5.13 Server robustness

The JSONL server MUST:

- handle `hello`, `execute`, and `close` at minimum;
- support sessions/reset policy through `execute` or explicit reset command;
- validate protocol version and schemas;
- enforce maximum line/program/gas/execution limits;
- return stable typed errors;
- flush one response per request line;
- continue after recoverable request errors;
- exit cleanly on EOF/close;
- avoid panics/private logs;
- support deterministic test process startup.

## 6. Public protocol requirements

Schemas under `spec/` are normative and MUST be completed. At minimum define:

### `hello` request/response

Negotiates protocol version, target build ID, public profile summary, enabled public capabilities, and limits. It MUST not identify the secret/fault-control status beyond what the benchmark intends public.

### `execute` request

Fields:

- `protocol_version`;
- `request_id`;
- `session_id`;
- `reset`: `hard|soft|none`;
- `program`: canonical DSL text or typed JSON program;
- `public_input`;
- `logical_batch_id`;
- public execution-seed identifier if applicable.

### `execute` response

Fields:

- echoed IDs;
- `ok` or typed error;
- status/public digest;
- observation bucket/width;
- public static metrics;
- budget usage;
- server semantic/profile version.

### Compatibility

Use a semantic protocol version. Unknown major versions fail. Minor-version behavior MUST be documented and tested. Golden fixtures MUST validate against JSON Schema in both languages.

## 7. System B — Interrogator requirements

## 7.1 Package structure

Implement modules equivalent to:

```text
ast.py / parser.py
protocol.py
profiles.py
relations/
certificates.py
normalization.py
statistics.py
constraints.py
solver.py
models.py
synthesis.py
knowledge_base.py
selector.py
learner.py
reducer.py
campaign.py
reporting.py
cli.py
```

The exact layout may evolve, but responsibilities MUST remain testable behind typed interfaces.

## 7.2 Python AST and DSL

Implement frozen typed AST nodes, deterministic formatting/canonical hashes, static resource/effect summaries, and compatible parsing. Property/golden tests MUST compare canonical programs accepted by Rust.

Every synthesis candidate MUST be constructed as a typed AST; do not generate arbitrary text and hope parsing succeeds.

## 7.3 Protocol client and harness

Implement:

- subprocess lifecycle and handshake;
- line-length and timeout limits;
- request/response correlation;
- structured target errors;
- session/reset handling;
- paired/randomized physical schedules;
- retry policy that does not duplicate logical evidence silently;
- raw transcript persistence before analysis;
- fake endpoint for unit tests.

Transport failure MUST not be interpreted as an oracle outcome.

## 7.4 Relation framework

Implement and enable the required templates:

1. `anchor-switch/v1`;
2. `token-switch/v1`;
3. `epoch-switch/v1`;
4. `phase-shift/v1`;
5. `repeat-amplify/v1`;
6. `independent-swap/v1`;
7. `context-lift/v1`;
8. `register-rename/v1`;
9. `hard-replay/v1`;
10. `soft-history-contrast/v1` for research mode.

Each enabled relation MUST provide:

- stable ID/version;
- applicability/precondition;
- typed instantiation;
- architectural certificate/check;
- fault-free observation certificate/check;
- normalizer;
- exact and/or bounded/statistical decision;
- constraint extractor;
- reducer rules;
- tests including true-secret satisfaction in white-box reduced-domain fixtures.

Campaigns MUST enforce a configurable minimum certificate strength. Empirical-only relations MUST NOT emit hard constraints.

## 7.5 Certificates

Implement a serialized certificate registry containing semantic/profile scope, relation instance hash, claims, proof method, artifact digest, and limitations. The first implementation MAY use exhaustive/SMT-bounded certificates generated on demand and cached. A certificate invalidates when relevant semantics/version changes.

## 7.6 Knowledge base

Implement:

- append-only campaign event log;
- SQLite materialized view/migrations;
- query nodes, execution batches, relation edges, decisions, constraints, candidate snapshots, state-model versions, witnesses;
- provenance links from constraints to raw responses/certificates;
- active frontier with TTL;
- structural, relation, state, observation, partition, and semantic novelty;
- implication-based novelty check with timeout/unknown handling;
- deterministic selection tie-break;
- crash-safe/resumable writes.

Do not serialize Z3 Python objects. Store a project constraint IR and/or SMT-LIB plus versioned metadata.

## 7.7 Constraint IR and solver

Implement a small serializable expression IR covering the needed bit-vector, Boolean, integer, finite-domain, conjunction/disjunction, comparison, and named-assumption constructs. Translate it to Z3.

The hypothesis store MUST support:

- hard domain/evidence constraints;
- named assumptions and unsat cores;
- soft weighted groups/MaxSMT;
- timeouts and `sat|unsat|unknown`;
- model enumeration with blocking;
- diverse-model generation;
- candidate snapshots/marginals;
- exact uniqueness/alternative-model check;
- implication checks;
- constraint group quarantine/retraction;
- provenance-rich diagnostics.

Widths/signs MUST be explicit. Include exhaustive concrete-vs-symbolic bank/fault/state checks over reduced domains.

## 7.8 Exact and bounded extractors

Tutorial mode MUST emit hard exact constraints. Standard bounded mode MUST use bucket/noise intervals with explicit nuisance variables or a proven elimination. Equal buckets MUST not be treated as exact equal cycles.

Every hard extractor test MUST establish that the true generated configuration satisfies the formula for all declared bounded noise values producing the observation.

## 7.9 Statistical layer

Research stochastic mode MUST implement:

- balanced randomized pair schedules;
- correlation groups;
- a robust effect estimator;
- a predeclared sequential or fixed-sample decision rule;
- `inconclusive` distinct from equality;
- calibrated/capped grouped soft weights;
- replay and evidence quarantine;
- deterministic fake distributions and simulation tests.

The exact robust/sequential method may be chosen after a reduced simulation, but it MUST be documented and evaluated for false-positive/inconclusive behavior.

## 7.10 Query synthesis

Implement a grammar of relation skeletons and typed finite holes. Required backend:

1. bounded skeleton enumeration;
2. SMT hole filling;
3. pair-separating synthesis from two surviving models;
4. diverse model committee scoring;
5. CEGIS counterexample refinement for unseparated/oversized buckets;
6. noise-margin and resource objectives;
7. deterministic tie-breaking and caching.

The first implementation may use lexicographic objectives rather than exact entropy. It MUST label committee partition scores as proxies unless candidate enumeration/sampling justifies information claims.

Required tests:

- tiny domain with known optimal query;
- no discriminator exists;
- at least one CEGIS iteration adds a counterexample pair;
- interval/noise margin changes selected query;
- fault-free profile has no secret-dependent discriminator;
- symbolic predictions agree with concrete test evaluator.

## 7.11 Selector and interrogation loop

Implement modes `infer`, `learn-state`, `calibrate`, `replay`, `reduce`, and `diversify`. Selection MUST use logged score components and integrate KB TTL/diversity plus current candidate model predictions.

A committed logical interrogation follows:

1. select/synthesize candidate;
2. validate preconditions/certificates;
3. schedule executions;
4. persist raw responses;
5. validate architectural relation;
6. decide observation relation;
7. update learner;
8. extract and trial constraint;
9. diagnose inconsistency or commit;
10. update KB/metrics;
11. optionally replay/reduce.

## 7.12 Active automata learning

Implement three interchangeable modes:

- one-state hard-reset learner;
- exact-history state adapter;
- AALpy-backed deterministic Mealy learner over versioned macro input/output alphabets.

The AALpy integration MUST include membership queries, cached start-state preparation, an approximate equivalence/conformance portfolio, counterexample handling, model serialization, state access/distinguishing support where available, and held-out prediction metrics.

State-conditioned constraints MUST be grouped by learned-model version and retractable after counterexamples. Research mode MUST compare at least exact-history/no-learner and learned-state variants.

## 7.13 Relational reducer

Implement a best-first or generation-integrated reducer over relation families. It MUST preserve:

- valid typed programs;
- architectural certificate;
- fault-free observation certificate;
- reproducible violation/decision;
- configured logical consequence (`equivalent`, `implies-core`, or `same-partition`);
- strict lexicographic cost improvement.

Required reductions include symmetric deletion, repeat/sample shrink, padding/fence simplification, token/anchor simplification, context/history shortening, and relation-composition collapse where valid.

## 7.14 Campaign persistence and reporting

A campaign run directory MUST follow the structure in `docs/ARCHITECTURE.md`. Implement resume/replay, integrity hashes, and report generation.

Reports MUST distinguish:

- exact facts;
- bounded conclusions;
- soft rankings;
- heuristic/committee estimates;
- quarantined evidence;
- model/solver unknowns;
- measured results versus configured acceptance targets.

## 7.15 CLI

Implement at least:

```text
sphinx-interrogate doctor
sphinx-interrogate recover
sphinx-interrogate replay
sphinx-interrogate inspect
sphinx-interrogate reduce
sphinx-interrogate benchmark
```

Commands MUST have useful `--help`, structured exit statuses, noninteractive operation, and explicit profile/run paths.

## 8. Formal and verification requirements

## 8.1 TLA+

Complete `formal/SphinxVM.tla` at an abstract session/scheduler level and check at least:

- hard reset uniqueness;
- soft reset preservation set;
- architectural state not changed by vault events;
- gas/step progress in the abstract bounded model;
- fault-disabled normalized cost independence in the reduced configuration.

TLC state bounds/configuration MUST be small enough for CI or a documented separate formal job.

## 8.2 SMT/relational checks

Implement executable Z3 or SMT-LIB checks for core relation templates on reduced finite bounds. Prefer generated checks from the same public semantic specification where possible. Formal checks MUST fail when a deliberate mutation breaks an obligation.

## 8.3 Differential testing

Rust concrete and Python symbolic semantics MUST be compared via generated fixtures/process calls for:

- S-box/bank mapping;
- fault guard/delta;
- phase/replay transition;
- exact cycles on small programs;
- reset semantics;
- relation extractors.

The production black-box boundary remains intact; this is test-only development evidence.

## 9. Testing requirements

## 9.1 Unit/property tests

Cover success and failure paths for parsers, validators, semantics, profiles, protocol, constraints, solvers, synthesis, KB, statistics, learner adapters, reducer, and reports.

Use property-based generation for valid programs and relation instances. Randomness MUST be seeded/reproducible, with failing examples minimized and persisted where helpful.

## 9.2 Integration tests

Launch the release target process and test:

- handshake/execute/errors/close;
- hard/soft reset;
- transcript persistence;
- small exact recovery;
- server crash/timeout handling;
- resume/replay;
- boundary audit.

## 9.3 Negative/mutation tests

Required controls:

- fault disabled;
- secret-independent jitter only;
- deliberately wrong symbolic model causes inconsistency rather than false recovery;
- broken relation normalizer/certificate is detected;
- diagnostic/private field injection is rejected/scanned;
- stronger/weaker fault mutations change recovery cost in aggregate;
- state-model counterexample retracts dependent constraints.

## 9.4 Flakiness

Ordinary CI MUST be deterministic. Stochastic behavior is tested through seeded simulations and tolerance/confidence rules that have demonstrated stability. Never fix flakes by retrying indefinitely or broadening assertions without analysis.

## 10. Evaluation requirements

Implement benchmark profiles, calibration/evaluation seed lists, baselines B0–B7 where feasible, and the primary ablations in `docs/EVALUATION.md`.

Before tuning final profile constants:

1. run a one-shot leakage audit;
2. run a white-box learnability upper bound in development mode;
3. run a fault mutation ladder;
4. select/version standard constants using calibration seeds only.

Release acceptance targets:

### Tutorial

- 100/100 exact unique recovery;
- median logical pairs <= 48;
- maximum <= 80;
- no false hard constraints in exhaustive reduced tests.

### Standard

- at least 95/100 exact unique recovery on published seeds;
- median logical families <= 180;
- 95th percentile <= 300;
- median physical executions <= 3,000;
- no false exact declarations on fault-free controls.

If calibration demonstrates these exact budgets are unreasonable while preserving the intended challenge, update targets only through a documented decision with baseline/full-system evidence. Do not silently weaken them.

Research targets are experimental but MUST be measured honestly.

## 11. Performance and resource limits

- Every solver call has a configurable timeout.
- Every protocol request/program/campaign has explicit resource limits.
- Candidate enumeration/model sampling is bounded and resumable.
- SQLite writes use transactions and migrations.
- A standard campaign should run on an ordinary developer workstation without privileged access.
- Cache keys include semantic/profile/model versions.
- Reports include time spent in VM, solver, synthesis, statistics, learning, and persistence.

## 12. Milestone deliverables

### M0 — Bootstrap/protocol

Complete workspace, dependency lock, schemas, hello/execute round trip, CI, status evidence.

### M1 — DSL/architecture

Complete parser/validator/interpreter/static effect/cost, cross-language AST compatibility, secret-independence tests.

### M2 — Microarchitecture/fault/challenges

Complete microcode, fault-free and faulty semantics, profiles, noise, challenge/judge, reset/boundary tests.

### M3 — Relations/certificates

Complete core stateless relations, normalizers, exact/bounded extractors, reduced exhaustive soundness.

### M4 — Harness/KB/solver

Complete process harness, persistence, constraint IR, exact solver, provenance, model snapshots, uniqueness.

### M5 — Tutorial recovery

Complete deterministic selector/campaign/report and meet tutorial acceptance.

### M6 — CEGIS synthesis

Complete grammar, model committees, counterexample refinement, cost/margin scoring, integration.

### M7 — Noise/standard

Complete bounded/statistical layer, MaxSMT/quarantine, calibration, meet standard acceptance.

### M8 — Stateful learning

Complete soft reset, exact history, AALpy adapter, conformance/counterexamples/retraction, research evaluation.

### M9 — Reducer/evaluation/release

Complete witness reduction, baselines/ablations, formal jobs, boundary audit, reports, release review.

An implementation agent MUST keep the active ExecPlan synchronized with actual completion/evidence.

## 13. Definition of complete

The project is complete only when all of the following are true and evidence paths are recorded in `agent/STATUS.md` and the active ExecPlan:

1. all required root commands are implemented;
2. `just fmt`, `just lint`, `just test`, and `just schema-check` pass cleanly;
3. formal checks pass with documented tool versions;
4. the release-mode black-box boundary audit passes;
5. tutorial flow meets its acceptance suite;
6. standard benchmark targets are met or an explicitly approved/versioned target revision is documented with evidence;
7. fault-free controls produce no false exact recovery;
8. every enabled relation has certificates and extractor-soundness evidence;
9. exact recovery includes alternative-model unsat evidence;
10. CEGIS, KB interrogation, and state-learning/retraction paths have real tests, not dead code;
11. run persistence, replay, reduction, and reports work from clean generated artifacts;
12. docs/schemas/CLI help match behavior;
13. no synthetic-only or black-box boundary restriction has been weakened;
14. the review checklist is completed honestly, with remaining non-blocking limitations listed.

## 14. Forbidden shortcuts

Do not:

- reveal exact cycles or internal banks to make recovery easy;
- call the judge repeatedly;
- compare against true secrets inside the black-box selector;
- mark empirical relation equality as a proof;
- turn solver `unknown` into `unsat`;
- interpret nonsignificance as equality;
- ignore quantization/noise nuisance variables;
- disable persistent state while claiming research-mode support;
- return the first Z3 model as unique;
- weaken negative controls or delete failing seeds;
- skip baselines and claim synthesis/interrogation value;
- expose a diagnostic protocol flag in the release server;
- add real-target capabilities.

## 15. Handling genuine blockers

If a required external tool cannot be installed, record the exact attempted command/error, complete all independent work, and provide a fallback check where possible. If an algorithm misses a benchmark target, diagnose using calibration, concrete/symbolic agreement, candidate partitions, and baselines before changing the fault/profile. Preserve failing artifacts and report uncertainty.

A blocker report MUST state:

- requirement blocked;
- work completed;
- approaches attempted;
- command/artifact evidence;
- why further local attempts are not defensible;
- exact input/tool/decision that would unblock it.
