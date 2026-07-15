# Test organization

- `tests/python/`: Python unit/property/integration tests.
- `tests/fixtures/protocol/`: JSON messages validated against the public protocol schema.
- `tests/fixtures/relations/`: serialized relation/certificate examples.
- Future `tests/exhaustive/`: reduced finite-domain semantic fixtures.

Production cross-language tests must launch `sphinx-vm` as a separate process. White-box semantic comparisons belong in clearly labeled development tests and must not be callable by black-box campaigns.
