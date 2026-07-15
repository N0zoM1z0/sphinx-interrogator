# Threat model and safety boundary

## 1. Assets

The protected asset in a challenge is a generated synthetic hidden configuration:

- secret cells;
- optional lane permutation;
- optional derived salts;
- current persistent microarchitectural state.

These values have no external security significance. They exist solely to evaluate analysis methods.

## 2. Adversary/System B capabilities

Interrogator may:

- start and communicate with the local SphinxVM server through the public JSONL protocol;
- submit valid bounded programs and reset requests allowed by the public profile;
- repeat and adapt queries within budgets;
- observe public architectural outputs, timing buckets, and documented public metrics;
- use arbitrary offline computation on its own transcript;
- know the public source/specification of the machine family and reference fault equation.

## 3. Prohibited capabilities

Interrogator may not:

- read the private challenge files or process environment containing them;
- inspect SphinxVM memory, debug output, core dumps, or IPC other than the protocol;
- import/link the Rust implementation into the Python process;
- request diagnostic mode through the public protocol;
- modify the target binary during a campaign;
- bypass budgets through process restarts unless the profile permits them;
- use the final judge as an unlimited guess oracle;
- contact or target external systems.

## 4. Security property

The architectural confidentiality property is:

> For any two secrets and the same valid program/public input, the public architectural output and status are equal.

SphinxVM intentionally violates a stronger timing noninterference contract through the injected fault. The objective is to recover the synthetic secret from that violation.

This means “security” has two layers:

- architectural noninterference should hold and is a correctness requirement;
- observation noninterference should fail only through the controlled fault and declared noise model.

## 5. Boundary enforcement

Recommended enforcement for tests/CI:

- run System A and B as separate OS processes;
- place private files in a temporary directory with restrictive permissions;
- pass only the target process a private file descriptor/path;
- sanitize environment inherited by Interrogator;
- forbid target source/crate paths in Python import configuration;
- scan transcripts for secret/internal field names and known concrete values;
- disable diagnostics in the release target binary;
- rate-limit final judge submissions;
- record target binary digest.

A strong local sandbox/container is desirable but not required for the conceptual benchmark. The boundary audit should assume honest-but-buggy project code, not defend against a malicious user with host root access.

## 6. Attacker knowledge variants

### Known model

Interrogator knows the exact family equation and profile, except secret/state. This is the primary benchmark and focuses on query synthesis/inference.

### Model family

Interrogator knows several possible fault variants and must identify one while recovering the secret. This tests model interrogation/refinement.

### Partial model

Interrogator knows only relation families and uses symbolic templates with holes for guard/state transitions. This is an advanced synthesis/learning problem.

Results from these variants must not be compared without naming the knowledge assumption.

## 7. Availability and malformed inputs

SphinxVM should treat malformed input as a structured error and enforce:

- maximum JSON line length;
- schema and semantic validation;
- instruction/program/gas limits;
- request timeout;
- bounded memory allocation;
- no file/network operations requested by programs;
- no panics crossing the server loop.

These are normal robust-engineering requirements, not part of the intended leakage.

## 8. Scope exclusion: real targets

The repository must not include:

- native timing collectors for real code;
- cache priming/probing implementations;
- speculative-execution gadgets;
- performance-counter collectors;
- power/EM acquisition;
- real cryptographic victim adapters;
- remote service interrogation;
- exploit delivery or credential/key handling.

Keeping the target synthetic makes the project suitable for learning and reproducible PL/security research without becoming an operational attack framework.

## 9. Disclosure model

Because the fault is intentional, reporting it is not a security disclosure. Accidental boundary bypasses or unsafe tooling should be handled through the repository's private security-advisory process. Reports must not include real third-party secrets or victim data.
