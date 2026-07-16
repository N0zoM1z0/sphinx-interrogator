# Public process protocol

## Version policy

SphinxVM and Interrogator communicate through one UTF-8 JSON object per line. The
version-1 server implements protocol `1.0` exactly. It rejects unknown major versions
and, until a backward-compatible minor extension is specified, also rejects unknown
minor versions. Adding optional fields therefore requires a protocol minor-version
decision, updated schemas and fixtures, and cross-process compatibility tests.

Every request carries `protocol_version`, `request_id`, and a tagged `kind`. Every
response echoes the accepted request ID, carries the same exact protocol version, and
is either a typed success response or a typed `error`. Interrogator rejects mismatched
request IDs, response kinds, versions, and unexpected top-level fields before any
response can become inference evidence.

## Transport bounds

The server bounds the encoded request line before JSON decoding. An oversized or
invalid UTF-8 line is discarded through its terminating newline, receives a recoverable
typed error, and does not terminate the session. The `hello_result` publishes request,
program, instruction, gas, session, reset, logical-query, and physical-execution limits.

The synchronous Python client applies a response timeout and line bound. A timeout,
EOF, malformed response, or correlation failure is a transport error, never an oracle
outcome. Callers can abort an unresponsive child process without an unbounded wait.

## Public response boundary

An execution response contains only architectural status/digest, a quantized cycle
bucket, documented static metrics, public budget counters, and semantic versions. It
does not expose the challenge secret, selected bank, phase, replay state, concrete
fault delta, jitter sample, private configuration, or pre-quantized exact cycle count.

The JSON Schema in `spec/protocol.schema.json` is normative. Golden fixtures and live
Rust/Python process tests validate the same response shapes.

The challenge and one-shot judge documents have separate normative schemas at
`spec/challenge.schema.json` and `spec/judge.schema.json`. The public challenge document
contains its ID, exact profile hash, opaque salted commitment, protocol version, public
campaign token, and budget copy. It contains no secret, mapping, fault assignment,
noise key, or commitment nonce.

## Public inputs and session state

`public_input.registers` supplies a prefix of `r0..r7`. `public_input.memory` is a
sparse object whose canonical decimal keys are addresses `0..255` and whose values are
16-bit words. Inputs are applied after the requested reset and before execution. A
hard or soft reset first clears architectural data; reset `none` preserves prior
architectural data and overlays only supplied entries. The program itself is parsed
and fully validated before a session, budget counter, input, or machine state changes.

Hard reset clears all hidden scheduler state. Soft reset preserves exactly the typed
fields listed by the public profile and clears every other hidden field. A logical
batch ID is charged once even when several physical executions form a paired or sampled
experiment; every execution is still charged to the physical budget. Hard reset is
charged per accepted hard-reset execution.

## Challenge and judge commands

The target is served only from a split generated challenge. Trusted local
orchestration creates the private root and private directory; System B receives only
the public challenge directory and the public socket path.

```text
sphinx-vm challenge private-root --output <private-root-file>
sphinx-vm challenge create --profile <profile.toml> \
  --public-output <public-dir> --private-output <private-dir> \
  --private-root-file <private-root-file> \
  [--challenge-id <opaque-public-id>] --campaign-label <private-label> \
  [--fault off|reference|weak|signed]
sphinx-vm serve --public-challenge <public-dir> \
  --private-challenge-fd <trusted-private-dir-fd> --socket <vm.sock>
sphinx-vm judge-serve --public-challenge <public-dir> \
  --private-challenge-fd <trusted-private-dir-fd> --socket <judge.sock>
```

The private root is a protected 256-bit file and is never serialized into public
challenge metadata. Public campaign seeds may schedule benchmark runs, but they do
not control the private root, secret, salts, noise key, or fault assignment. In blind
controls, `standard.toml` and `fault_free.toml` are byte-identical public profiles
and differ only in private challenge assignment.

The judge validates a complete guess, atomically consumes the campaign token on its
first well-formed submission, and returns only public IDs plus `submission_recorded`
and `accepted`. A later invocation for the same token returns
`submission_recorded=false, accepted=false`, so it cannot be used as a repeated guess
oracle.
