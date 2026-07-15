# System A: SphinxVM

## 1. Purpose

SphinxVM is a deterministic transition-system core wrapped in configurable observation and noise models. It should be interesting enough to exercise program analyses without becoming an unmanageable processor simulator.

The key separation is:

\[
\text{architectural semantics} \quad\neq\quad
\text{fault-free timing semantics} \quad\neq\quad
\text{faulty concrete semantics}.
\]

Only the last is exposed as the challenge target. The first two exist to certify relations and evaluate the injected defect.

## 2. Architectural machine

### 2.1 State

Recommended fixed sizes for version 1:

- eight 16-bit general-purpose registers `r0..r7`;
- 12-bit program counter with a program limit of 256 instructions;
- flags `Z`, `N`, `C`, and `V`;
- 256 words of 16-bit data memory;
- 16-entry bounded return stack;
- a 64-bit public output digest accumulator;
- halt/error status;
- gas counter.

The secret is absent from architectural state.

### 2.2 ISA

Ordinary instructions:

- `MOVI rd, imm`
- `MOV rd, rs`
- `ADD`, `XOR`, `AND`, `OR`, `SHL`, `SHR`
- `LOAD`, `STORE`
- `CMP`
- `JMP`, `JZ`, `JNZ`
- `CALL`, `RET`
- `LOOP count, target` or a verifier-approved bounded loop form
- `MIXOUT rs`
- `HALT`

Experiment instructions:

- `PROBE lane, token, epoch`
- `ANCHOR bank, epoch`
- `PAD amount`
- `FENCE`

`PROBE`, `ANCHOR`, `PAD`, and `FENCE` do not alter general registers, data memory, flags, or the output digest. They advance control and consume gas. This makes insertion, deletion under a matched static-cost normalizer, exchange, repetition, and phase manipulation available as relation transformations.

### 2.3 Program validity

The validator rejects:

- invalid registers, lanes, banks, tokens, or epochs;
- out-of-range branches;
- unbounded loops or recursion;
- programs above instruction or gas limits;
- writes outside data memory;
- malformed control flow;
- undefined arithmetic behavior.

Programs are parsed into a typed AST before execution. No instruction stream is self-modifying.

## 3. Microcode

Each architectural instruction expands into a short list of micro-ops. Ordinary instructions may use one to three micro-ops. Experiment instructions use the vault pipeline:

```text
PROBE  -> DecodeProbe -> VaultIndex -> VaultRead -> MixDiscard -> Retire
ANCHOR -> DecodeAnchor -> PublicBankRead -> MixDiscard -> Retire
PAD    -> PhaseStep(amount) -> Retire
FENCE  -> DrainReplay -> Retire
```

The architectural result of `MixDiscard` is discarded. It exists to make the microcode path nontrivial and to allow a small micro-op cache.

The microcode engine is in-order. The scheduling bug is in resource reservation/replay, not in architectural speculation. This keeps exact reasoning tractable.

## 4. Hidden configuration

### 4.1 Secret cells

Tutorial and standard profiles use four or eight four-bit cells. The recovery target is their ordered concatenation.

### 4.2 Bank mapping

Let `SBOX4` be the public permutation:

```text
index: 0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F
value: 6  B  0  4  D  3  F  8  A  2  5  C  1  E  7  9
```

For lane `i`, token `q`, and epoch `p`:

```text
u       = secret[perm[i]] XOR q XOR salt[i]
v       = SBOX4[u]
bank    = (v >> (2 * p)) & 0b11
```

In tutorial/standard mode `perm[i]=i` and `salt[i]=0` unless a calibration variant says otherwise. Research mode enables a hidden permutation and nonzero salts. A profile must specify whether these are part of the recovery target or nuisance configuration. The recommended research target is `(secret, permutation)` while salts remain deterministically derived from the challenge seed.

### 4.3 Microarchitectural state

```text
phase:          2 bits
last_bank:      Option<2-bit bank>
replay_credit:  2 bits
uop_cache_tag:  4 bits
uop_cache_valid:boolean
history_hash:   small diagnostic-only internal value, never public
```

Hard reset clears every field. Soft reset clears architectural state but preserves the fields named by the profile. The profile declares reset semantics as part of the public contract.

## 5. Fault-free scheduler

The fault-free scheduler allocates a fixed timing envelope to every vault cell. Static cost is known from the program:

```text
base(PROBE)  = 5 cycles
base(ANCHOR) = 4 cycles
base(PAD n)  = n cycles
base(FENCE)  = 2 cycles
```

An experiment cell consists of a probe and a nearby anchor in the same epoch. Regardless of bank equality, the fault-free scheduler reserves one replay slot and charges a fixed normalized cost. A normalizer subtracts all ordinary and declared padding costs, leaving zero for every fault-free relation template.

The exact constants may change during implementation, but these properties may not:

1. static cost is computable without the secret;
2. the fault-free normalized observation is secret-independent;
3. the faulty delta is small relative to total cost;
4. the same microcode path is used with and without the defect.

## 6. Reference fault: guarded replay accounting

For a probe event `e`, subsequent matching-epoch anchor bank `b`, and pre-event microstate `z`, define:

```text
collision = bank(secret, e) == b
guard     = phase(z) == ((lane(e) XOR token(e) XOR epoch(e)) & 0b11)
suppress  = replay_credit(z) == 0b11
```

Reference profile:

```text
fault_delta = 1 if collision and guard and not suppress else 0
```

Optional signed mutation:

```text
fault_delta =
    +1 if collision and guard and not suppress
    -1 if not collision and guard and replay_credit == 0b10
     0 otherwise
```

State update occurs even when the aggregate observation is quantized:

```text
phase' = (phase + 1 + epoch) mod 4
replay_credit' =
    min(3, replay_credit + 1) if collision
    max(0, replay_credit - 1) otherwise
last_bank' = bank(secret, e)
```

The exact update should be captured once in a pure function and reused by concrete and symbolic semantics.

### 6.1 Why use an anchor

A public anchor gives relation synthesis a controllable reference bank. Absolute execution time still does not directly reveal equality because static cost, quantization, phase, replay state, and noise intervene. A related pair that changes only the anchor can isolate a signed constraint.

### 6.2 Why use two epochs

Each epoch reveals a two-bit projection of the S-box output. Neither projection alone identifies a secret nibble. Combining relations from both epochs and several tokens gives a unique bit-vector solution.

### 6.3 Why use phase

Phase prevents a fixed small query set from working uniformly. `PAD`, order changes, and context transformations can select or discover the active guard. This creates a genuine synthesis problem.

### 6.4 Why retain replay state

Persistent replay credit turns the research profile into a hidden-state system. Interrogator must either reset, model the history exactly, or learn a finite abstraction. Ignoring state should measurably degrade recovery.

## 7. Observation model

A successful run returns:

```json
{
  "status": "halted",
  "public_digest": "...",
  "observation": {
    "cycle_bucket": 37,
    "bucket_width": 4,
    "samples_in_vm": 1
  },
  "public_metrics": {
    "retired_instructions": 24,
    "static_cycles": 132
  }
}
```

No per-event trace, bank ID, phase, replay flag, secret-derived digest, or exact pre-quantized cycle count is public in challenge mode.

The observation pipeline is:

1. compute fault-free static cycles;
2. add concrete fault deltas;
3. add profile-defined deterministic or stochastic jitter;
4. clamp to a valid range;
5. quantize with `floor(cycles / bucket_width)`;
6. return the bucket and public metadata.

Internal transition values are available only to in-crate System A tests; the release
server implements no diagnostic request or response shape. Boundary tests inspect the
actual generated public artifacts, permissions, Python imports, and live response keys.

## 8. Profiles

### Tutorial

- four secret cells, 16 bits;
- identity lane map and zero salts;
- hard reset before each logical experiment;
- exact cycles (`bucket_width=1`), no jitter;
- phase guard enabled but known reset state;
- no persistent replay suppression.

### Standard

- eight secret cells, 32 bits;
- identity lane map and zero salts;
- hard reset available;
- bucket width 4;
- seeded jitter in `{-1,0,+1}` per physical execution;
- replay credit active within a program;
- query and execution budgets.

### Research

- eight secret cells plus hidden lane permutation;
- salts derived from private challenge seed;
- hard reset expensive or rate-limited; soft reset normal;
- bucket width 8;
- stochastic jitter with bounded support plus rare outliers;
- replay and cache state persistent;
- history-dependent suppression;
- stricter program and execution budgets.

### Fault-free control

Same public profile as standard, but the fault delta is disabled. The public profile must not say whether this control is active during blind evaluation.

## 9. Challenge isolation

A challenge package has public and private halves:

```text
public/profile.toml
public/challenge.json       # id, profile hash, commitment, budgets
private/secret.bin
private/config.toml
```

The version-1 commitment hashes a domain tag and length-framed challenge ID, profile
hash, secret cells, private lane permutation, salts, private fault assignment, logged
private generation root, noise key, and a 256-bit private nonce. The nonce remains private; therefore the public
commitment identifies an immutable challenge package without becoming a practical
offline guess oracle. Loading or judging rejects any public or private material that
does not reproduce the commitment.

Challenge creation refuses an existing output path. On POSIX systems, public
directories/files use modes `0755`/`0644`, while the private tree and files use
`0700`/`0600`. The judge atomically creates a mode-`0600` marker for the public campaign
token before comparing the final ordered-cell guess, enforcing one submission.

## 10. Required invariants

1. Public architectural output is independent of the secret for every valid program.
2. Fault-free normalized cost is independent of the secret for every certified relation instance.
3. The server never serializes private configuration or diagnostic events.
4. Hard reset produces the unique documented initial state.
5. Soft reset preserves exactly the documented state subset.
6. Same secret, profile, program, seed, reset history, and request schedule produce the same deterministic-profile transcript.
7. Gas and size bounds guarantee termination.
8. Fault selection changes only timing deltas; the hidden state transition and architectural semantics are shared by all variants.

These invariants should be represented in unit/property tests and, where practical, in TLA+/SMT models.
