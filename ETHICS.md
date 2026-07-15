# Ethics and scope policy

Sphinx Interrogator is a controlled educational and research artifact. Its purpose is to study formal reasoning about relational observations, active testing, and synthesis against a **deliberately vulnerable synthetic machine**.

## Allowed scope

- The in-repository SphinxVM and generated challenge instances.
- Offline simulation, symbolic models, synthetic noise, and reproducible benchmarks.
- Formal verification of leakage contracts and relation templates.
- General research discussion about black-box inference and defensive validation.

## Out of scope

- Collecting timing, cache, power, electromagnetic, or speculative-execution signals from real hardware.
- Targeting real cryptographic implementations, operating systems, cloud services, browsers, enclaves, or third-party programs.
- Adding adapters for privileged performance counters or hardware attack frameworks.
- Using the framework to recover real credentials, keys, personal data, or proprietary state.
- Publishing challenge secrets or bypasses that undermine another party's system.

Contributions that expand the project beyond the synthetic sandbox should be rejected. A separate, explicit ethical and legal review would be required before any real-system research.

## Responsible research behavior

Keep experiments reproducible, distinguish demonstrated results from proposed targets, report negative results, preserve raw benchmark metadata, and avoid overstating security conclusions. The injected fault is a pedagogical model; success against it does not establish feasibility against a real processor, and failure does not establish real-world safety.
