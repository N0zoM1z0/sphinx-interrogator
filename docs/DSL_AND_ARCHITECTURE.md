# Probe DSL and architectural semantics

This document fixes version-1 behavior shared by the authoritative Rust executor and
the independent Python query representation. `spec/probe-dsl.ebnf` defines surface
syntax; this document defines validation, canonicalization, and architectural effects.

## Program and operand model

A resolved program is a non-empty sequence of at most the profile's
`max_program_instructions`, and its final encoded instruction is `HALT`. Registers are
`r0` through `r7`; register names and opcodes are accepted case-insensitively. Labels
are case-sensitive ASCII identifiers. Decimal and `0x` hexadecimal integers are
accepted, with a leading minus only where signed syntax is allowed.

`MOVI` accepts `-32768..65535`; negative source syntax is converted to its 16-bit
two's-complement word before it enters the AST. Shift amounts are `0..15`, memory
offsets are signed 16-bit values, loop counts and pad amounts are `0..65535`, tokens
are `0..15`, epochs are `0..1`, anchor banks are `0..3`, and lanes are bounded by the
public profile. Both parsers reject an out-of-domain typed AST as well as bad text.

Only `LOOP` may have a backward target. `JMP`, `JZ`, `JNZ`, and `CALL` must target a
strictly later instruction. `LOOP` may target itself or an earlier instruction and
never a later one. Abstract control-flow validation explores both conditional paths,
tracks an exact return stack of at most 16 entries, rejects reachable empty `RET`, and
rejects any path that falls off the program. Runtime gas remains a second independent
termination bound.

## Canonical representation

Canonical text has one instruction per line, uppercase opcodes, lowercase registers,
decimal operands, normalized address spacing, and a final newline. Comments and input
label names are discarded. Every referenced target is emitted on its own line as
`LNNN:`, where `NNN` is the zero-based target index padded to at least three digits.
The canonical program hash is lowercase SHA-256 over those exact UTF-8 bytes.

The stable resolved AST serialization is compact JSON:

```json
{"instructions":[{"op":"MOVI","operands":[0,7]}],"version":1}
```

Objects use the shown lexical key order and no insignificant whitespace. Branch
operands are zero-based instruction indices. `LOAD` operands are
`[destination, base, signed_offset]`; `STORE` operands are
`[base, signed_offset, source]`. The golden corpus under
`tests/fixtures/programs/` is normative for text, AST JSON, and hash compatibility.

## Architectural state and instruction effects

The public architectural state consists of eight 16-bit registers, `Z/N/C/V` flags,
256 16-bit memory words, a zero-based program counter, a 16-entry return stack, a
64-bit digest, status, gas accounting, and public retirement/static-cycle metrics.
Arithmetic and addressing are total:

- `MOVI` and `MOV` write only the destination register.
- `ADD` wraps modulo 65536. It sets `Z` and `N` from the result, `C` on unsigned carry,
  and `V` on signed two's-complement overflow.
- `XOR`, `AND`, and `OR` write the result, set `Z/N`, and clear `C/V`.
- `SHL` and logical `SHR` use an immediate `0..15`, set `Z/N`, set `C` to the last bit
  shifted out (false for a zero shift), and clear `V`.
- `LOAD` and `STORE` use `(base register + signed offset) mod 256` and leave flags
  unchanged.
- `CMP` computes a non-stored wrapping subtraction. `C` means unsigned no-borrow;
  `Z/N/V` have their conventional 16-bit subtraction meanings.
- `JMP`, `JZ`, and `JNZ` update only control state. `CALL` pushes the following PC;
  `RET` pops it. The validator makes stack overflow and underflow unreachable.
- At `LOOP count, target`, the VM takes exactly `count` backedges on each fresh entry
  to that loop instruction, then falls through. Thus a body immediately preceding
  `LOOP 2` executes three times. Completion clears that loop site's counter so an
  enclosing loop can enter it again.
- `MIXOUT` updates the digest as `(digest XOR word) * 0x00000100000001b3` modulo
  `2^64`.
- `PROBE`, `ANCHOR`, `PAD`, and `FENCE` preserve registers, memory, flags, and digest.
  They emit an architecturally silent event to the separately implemented synthetic
  microarchitecture. They still advance PC, retire, and consume public gas/cycles.
- `HALT` sets halted status. If the next instruction's gas charge exceeds remaining
  gas, no part of that instruction retires and status becomes `gas_exhausted`.

## Public costs

One retirement costs one cycle for `MOVI`, `MOV`, `CMP`, jumps, calls, returns,
`LOOP`, `MIXOUT`, and `HALT`; two for arithmetic/logic/shift and `FENCE`; three for
`LOAD`/`STORE`; five for `PROBE`; four for `ANCHOR`; and exactly the public amount for
`PAD`. Gas is `max(static_cycles, 1)`, so `PAD 0` still makes progress.

`encoded_gas` and encoded static cycles are exact sums obtained by charging each
encoded instruction once. They are deliberately not called dynamic path bounds:
branches may skip instructions and loops may retire them repeatedly. The actual
execution metrics and gas status are calculated from the retired path.
