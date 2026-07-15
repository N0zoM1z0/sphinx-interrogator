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

## Public inputs and session state

`public_input.registers` supplies a prefix of `r0..r7`. `public_input.memory` is a
sparse object whose canonical decimal keys are addresses `0..255` and whose values are
16-bit words. Inputs are applied after the requested reset and before execution. A
hard or soft reset first clears architectural data; reset `none` preserves prior
architectural data and overlays only supplied entries. The program itself is parsed
and fully validated before a session, budget counter, input, or machine state changes.
