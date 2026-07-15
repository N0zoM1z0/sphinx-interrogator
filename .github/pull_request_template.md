## Change

Describe the smallest behavior change and the milestone/requirement it advances.

## Soundness and boundaries

- [ ] System B still uses only the documented public process protocol.
- [ ] Architectural, fault-free, and faulty semantics remain separate.
- [ ] Every changed relation has explicit preconditions, proof/test evidence, and extractor provenance.
- [ ] No real-target adapter, private challenge data, or diagnostic leak was added.

## Verification

List exact commands and outcomes. Do not mark a check unless it was run.

```text
just fmt
just lint
just test
```

Additional semantic/formal/benchmark checks:

```text
...
```

## Documentation and project memory

- [ ] Public schemas/docs match behavior.
- [ ] The active ExecPlan and `agent/STATUS.md` reflect the result.
- [ ] Generated benchmark claims link to machine-readable artifacts.
