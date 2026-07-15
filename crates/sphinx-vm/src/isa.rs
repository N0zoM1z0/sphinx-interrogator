//! Typed version-1 instruction set and canonical program representation.

use serde_json::{json, Value};
use sha2::{Digest as _, Sha256};

use crate::parser::parse_program;
use crate::validate::validate_program;

/// An error produced while parsing or validating a probe program.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProgramError {
    /// A source line could not be parsed.
    Parse {
        /// One-based source line.
        line: usize,
        /// One-based source column when known.
        column: usize,
        /// Human-readable parse diagnostic.
        message: String,
    },
    /// A resolved instruction violates a semantic control-flow rule.
    Validation {
        /// Zero-based instruction index.
        instruction: usize,
        /// Human-readable validation diagnostic.
        message: String,
    },
    /// The program exceeds a profile or validator resource limit.
    Limit(String),
}

impl std::fmt::Display for ProgramError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Parse {
                line,
                column,
                message,
            } => write!(formatter, "line {line}, column {column}: {message}"),
            Self::Validation {
                instruction,
                message,
            } => write!(formatter, "instruction {instruction}: {message}"),
            Self::Limit(message) => write!(formatter, "program limit: {message}"),
        }
    }
}

impl std::error::Error for ProgramError {}

/// A typed instruction accepted by the version-1 VM.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Instruction {
    /// Load a 16-bit immediate into a register.
    MovI { dst: u8, value: u16 },
    /// Copy a register.
    Mov { dst: u8, src: u8 },
    /// Add two registers with wrapping 16-bit arithmetic.
    Add { dst: u8, lhs: u8, rhs: u8 },
    /// Bitwise exclusive OR.
    Xor { dst: u8, lhs: u8, rhs: u8 },
    /// Bitwise AND.
    And { dst: u8, lhs: u8, rhs: u8 },
    /// Bitwise OR.
    Or { dst: u8, lhs: u8, rhs: u8 },
    /// Logical left shift by an immediate in `0..=15`.
    Shl { dst: u8, src: u8, amount: u8 },
    /// Logical right shift by an immediate in `0..=15`.
    Shr { dst: u8, src: u8, amount: u8 },
    /// Load a word from `(register + signed offset) mod 256`.
    Load { dst: u8, base: u8, offset: i16 },
    /// Store a word to `(register + signed offset) mod 256`.
    Store { base: u8, offset: i16, src: u8 },
    /// Compare two registers and update `Z/N/C/V` as 16-bit subtraction.
    Cmp { lhs: u8, rhs: u8 },
    /// Unconditional validated forward jump.
    Jmp { target: usize },
    /// Jump forward when the zero flag is set.
    Jz { target: usize },
    /// Jump forward when the zero flag is clear.
    Jnz { target: usize },
    /// Call a validated forward target.
    Call { target: usize },
    /// Return to the most recent bounded call site.
    Ret,
    /// Execute a statically bounded backward loop.
    Loop { count: u16, target: usize },
    /// Mix a public register into the architectural digest.
    MixOut { src: u8 },
    /// Secret-dependent microarchitectural probe with no architectural data effect.
    Probe { lane: usize, token: u8, epoch: u8 },
    /// Public reference-bank access with no architectural data effect.
    Anchor { bank: u8, epoch: u8 },
    /// Advance timing phase by a public amount without an architectural data effect.
    Pad { amount: u16 },
    /// Drain replay state without an architectural data effect.
    Fence,
    /// Stop execution.
    Halt,
}

impl Instruction {
    /// Return the documented fault-free static cycle count of one retirement.
    #[must_use]
    pub fn static_cycles(&self) -> u64 {
        match self {
            Self::MovI { .. }
            | Self::Mov { .. }
            | Self::Cmp { .. }
            | Self::Jmp { .. }
            | Self::Jz { .. }
            | Self::Jnz { .. }
            | Self::Call { .. }
            | Self::Ret
            | Self::Loop { .. }
            | Self::MixOut { .. }
            | Self::Halt => 1,
            Self::Add { .. }
            | Self::Xor { .. }
            | Self::And { .. }
            | Self::Or { .. }
            | Self::Shl { .. }
            | Self::Shr { .. } => 2,
            Self::Load { .. } | Self::Store { .. } => 3,
            Self::Probe { .. } => 5,
            Self::Anchor { .. } => 4,
            Self::Pad { amount } => u64::from(*amount),
            Self::Fence => 2,
        }
    }

    /// Return the gas charged for one retirement.
    #[must_use]
    pub fn gas_cost(&self) -> u64 {
        self.static_cycles().max(1)
    }

    pub(crate) fn render_with_labels(&self) -> String {
        match self {
            Self::MovI { dst, value } => format!("MOVI r{dst}, {value}"),
            Self::Mov { dst, src } => format!("MOV r{dst}, r{src}"),
            Self::Add { dst, lhs, rhs } => format!("ADD r{dst}, r{lhs}, r{rhs}"),
            Self::Xor { dst, lhs, rhs } => format!("XOR r{dst}, r{lhs}, r{rhs}"),
            Self::And { dst, lhs, rhs } => format!("AND r{dst}, r{lhs}, r{rhs}"),
            Self::Or { dst, lhs, rhs } => format!("OR r{dst}, r{lhs}, r{rhs}"),
            Self::Shl { dst, src, amount } => format!("SHL r{dst}, r{src}, {amount}"),
            Self::Shr { dst, src, amount } => format!("SHR r{dst}, r{src}, {amount}"),
            Self::Load { dst, base, offset } => {
                format!("LOAD r{dst}, {}", render_address(*base, *offset))
            }
            Self::Store { base, offset, src } => {
                format!("STORE {}, r{src}", render_address(*base, *offset))
            }
            Self::Cmp { lhs, rhs } => format!("CMP r{lhs}, r{rhs}"),
            Self::Jmp { target } => format!("JMP {}", canonical_label(*target)),
            Self::Jz { target } => format!("JZ {}", canonical_label(*target)),
            Self::Jnz { target } => format!("JNZ {}", canonical_label(*target)),
            Self::Call { target } => format!("CALL {}", canonical_label(*target)),
            Self::Ret => "RET".to_owned(),
            Self::Loop { count, target } => {
                format!("LOOP {count}, {}", canonical_label(*target))
            }
            Self::MixOut { src } => format!("MIXOUT r{src}"),
            Self::Probe { lane, token, epoch } => format!("PROBE {lane}, {token}, {epoch}"),
            Self::Anchor { bank, epoch } => format!("ANCHOR {bank}, {epoch}"),
            Self::Pad { amount } => format!("PAD {amount}"),
            Self::Fence => "FENCE".to_owned(),
            Self::Halt => "HALT".to_owned(),
        }
    }

    pub(crate) fn branch_target(&self) -> Option<usize> {
        match self {
            Self::Jmp { target }
            | Self::Jz { target }
            | Self::Jnz { target }
            | Self::Call { target }
            | Self::Loop { target, .. } => Some(*target),
            _ => None,
        }
    }

    fn canonical_ast_value(&self) -> Value {
        let (op, operands) = match self {
            Self::MovI { dst, value } => ("MOVI", json!([dst, value])),
            Self::Mov { dst, src } => ("MOV", json!([dst, src])),
            Self::Add { dst, lhs, rhs } => ("ADD", json!([dst, lhs, rhs])),
            Self::Xor { dst, lhs, rhs } => ("XOR", json!([dst, lhs, rhs])),
            Self::And { dst, lhs, rhs } => ("AND", json!([dst, lhs, rhs])),
            Self::Or { dst, lhs, rhs } => ("OR", json!([dst, lhs, rhs])),
            Self::Shl { dst, src, amount } => ("SHL", json!([dst, src, amount])),
            Self::Shr { dst, src, amount } => ("SHR", json!([dst, src, amount])),
            Self::Load { dst, base, offset } => ("LOAD", json!([dst, base, offset])),
            Self::Store { base, offset, src } => ("STORE", json!([base, offset, src])),
            Self::Cmp { lhs, rhs } => ("CMP", json!([lhs, rhs])),
            Self::Jmp { target } => ("JMP", json!([target])),
            Self::Jz { target } => ("JZ", json!([target])),
            Self::Jnz { target } => ("JNZ", json!([target])),
            Self::Call { target } => ("CALL", json!([target])),
            Self::Ret => ("RET", json!([])),
            Self::Loop { count, target } => ("LOOP", json!([count, target])),
            Self::MixOut { src } => ("MIXOUT", json!([src])),
            Self::Probe { lane, token, epoch } => ("PROBE", json!([lane, token, epoch])),
            Self::Anchor { bank, epoch } => ("ANCHOR", json!([bank, epoch])),
            Self::Pad { amount } => ("PAD", json!([amount])),
            Self::Fence => ("FENCE", json!([])),
            Self::Halt => ("HALT", json!([])),
        };
        json!({"op": op, "operands": operands})
    }
}

/// Public static effect summary used by validators and synthesis.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EffectSummary {
    /// Program may read data memory.
    pub reads_memory: bool,
    /// Program may write data memory.
    pub writes_memory: bool,
    /// Program may change non-sequential control flow.
    pub changes_control_flow: bool,
    /// Program may update the public output digest.
    pub writes_digest: bool,
    /// Number of architecturally silent experiment instructions.
    pub experiment_instructions: usize,
}

/// Public static resource summary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResourceSummary {
    /// Number of encoded instructions.
    pub instructions: usize,
    /// Sum of one-retirement fault-free cycle costs.
    pub static_cycles: u64,
    /// Exact sum of one-retirement gas costs for encoded instructions.
    ///
    /// This is not a dynamic path bound: branches can skip instructions and LOOP
    /// can retire instructions repeatedly. Runtime gas remains authoritative.
    pub encoded_gas: u64,
}

/// A parsed and semantically validated finite program.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Program {
    instructions: Vec<Instruction>,
}

impl Program {
    /// Parse and validate a program under public profile limits.
    pub fn parse(
        source: &str,
        lanes: usize,
        max_instructions: usize,
        max_gas: u64,
    ) -> Result<Self, ProgramError> {
        let instructions = parse_program(source, lanes)?;
        Self::new(instructions, lanes, max_instructions, max_gas)
    }

    /// Validate an already typed instruction sequence.
    pub fn new(
        instructions: Vec<Instruction>,
        lanes: usize,
        max_instructions: usize,
        max_gas: u64,
    ) -> Result<Self, ProgramError> {
        validate_program(&instructions, lanes, max_instructions, max_gas)?;
        Ok(Self { instructions })
    }

    /// Borrow the instruction sequence.
    #[must_use]
    pub fn instructions(&self) -> &[Instruction] {
        &self.instructions
    }

    /// Return the public static cycle sum, excluding extra loop retirements.
    #[must_use]
    pub fn static_cycles(&self) -> u64 {
        self.instructions
            .iter()
            .map(Instruction::static_cycles)
            .sum()
    }

    /// Return a deterministic static resource summary.
    #[must_use]
    pub fn resources(&self) -> ResourceSummary {
        ResourceSummary {
            instructions: self.instructions.len(),
            static_cycles: self.static_cycles(),
            encoded_gas: self.instructions.iter().map(Instruction::gas_cost).sum(),
        }
    }

    /// Return a deterministic public effect summary.
    #[must_use]
    pub fn effects(&self) -> EffectSummary {
        let mut summary = EffectSummary {
            reads_memory: false,
            writes_memory: false,
            changes_control_flow: false,
            writes_digest: false,
            experiment_instructions: 0,
        };
        for instruction in &self.instructions {
            match instruction {
                Instruction::Load { .. } => summary.reads_memory = true,
                Instruction::Store { .. } => summary.writes_memory = true,
                Instruction::Jmp { .. }
                | Instruction::Jz { .. }
                | Instruction::Jnz { .. }
                | Instruction::Call { .. }
                | Instruction::Ret
                | Instruction::Loop { .. } => summary.changes_control_flow = true,
                Instruction::MixOut { .. } => summary.writes_digest = true,
                Instruction::Probe { .. }
                | Instruction::Anchor { .. }
                | Instruction::Pad { .. }
                | Instruction::Fence => summary.experiment_instructions += 1,
                _ => {}
            }
        }
        summary
    }

    /// Render a canonical, label-normalized, newline-terminated program.
    #[must_use]
    pub fn render(&self) -> String {
        let targets: std::collections::BTreeSet<usize> = self
            .instructions
            .iter()
            .filter_map(Instruction::branch_target)
            .collect();
        let mut output = String::new();
        for (index, instruction) in self.instructions.iter().enumerate() {
            if targets.contains(&index) {
                output.push_str(&canonical_label(index));
                output.push_str(":\n");
            }
            output.push_str(&instruction.render_with_labels());
            output.push('\n');
        }
        output
    }

    /// Return the SHA-256 digest of canonical program text.
    #[must_use]
    pub fn canonical_sha256(&self) -> String {
        let digest = Sha256::digest(self.render().as_bytes());
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut output = String::with_capacity(64);
        for byte in digest {
            output.push(char::from(HEX[usize::from(byte >> 4)]));
            output.push(char::from(HEX[usize::from(byte & 0x0f)]));
        }
        output
    }

    /// Serialize the resolved typed AST as deterministic compact JSON.
    pub fn canonical_ast_json(&self) -> Result<String, serde_json::Error> {
        let instructions: Vec<Value> = self
            .instructions
            .iter()
            .map(Instruction::canonical_ast_value)
            .collect();
        serde_json::to_string(&json!({"instructions": instructions, "version": 1}))
    }
}

fn canonical_label(target: usize) -> String {
    format!("L{target:03}")
}

fn render_address(base: u8, offset: i16) -> String {
    match offset.cmp(&0) {
        std::cmp::Ordering::Equal => format!("[r{base}]"),
        std::cmp::Ordering::Greater => format!("[r{base} + {offset}]"),
        std::cmp::Ordering::Less => format!("[r{base} - {}]", offset.unsigned_abs()),
    }
}

#[cfg(test)]
mod tests {
    use super::{Instruction, Program};

    #[test]
    fn parses_every_instruction_and_round_trips_canonical_labels() {
        let source = r#"
            start: MOVI r0, -1
            MOV r1, r0
            ADD r2, r0, r1
            XOR r2, r2, r1
            AND r2, r2, r0
            OR r2, r2, r1
            SHL r3, r2, 1
            SHR r3, r3, 1
            STORE [r0 - 2], r3
            LOAD r4, [r0 + 2]
            CMP r3, r4
            JZ after
            CALL function
            JMP after
            function: MIXOUT r4
            RET
            after: PROBE 0, 3, 1
            ANCHOR 2, 1
            PAD 2
            FENCE
            LOOP 2, after
            HALT
        "#;
        let program = match Program::parse(source, 4, 64, 4096) {
            Ok(value) => value,
            Err(error) => panic!("complete test program should parse: {error}"),
        };
        let canonical = program.render();
        let reparsed = match Program::parse(&canonical, 4, 64, 4096) {
            Ok(value) => value,
            Err(error) => panic!("canonical program should parse: {error}"),
        };
        assert_eq!(program.instructions(), reparsed.instructions());
        assert_eq!(canonical, reparsed.render());
        assert_eq!(program.canonical_sha256().len(), 64);
        assert!(matches!(
            program.instructions()[0],
            Instruction::MovI {
                dst: 0,
                value: u16::MAX
            }
        ));
    }

    #[test]
    fn reports_duplicate_and_unknown_labels() {
        let duplicate = Program::parse("a: PAD 1\na: HALT\n", 1, 8, 32);
        assert!(matches!(duplicate, Err(super::ProgramError::Parse { .. })));
        let unknown = Program::parse("JMP nowhere\nHALT\n", 1, 8, 32);
        assert!(matches!(unknown, Err(super::ProgramError::Parse { .. })));
    }

    #[test]
    fn every_opcode_rejects_wrong_source_arity() {
        let opcodes = [
            "MOVI", "MOV", "ADD", "XOR", "AND", "OR", "SHL", "SHR", "LOAD", "STORE", "CMP", "JMP",
            "JZ", "JNZ", "CALL", "RET", "LOOP", "MIXOUT", "PROBE", "ANCHOR", "PAD", "FENCE",
            "HALT",
        ];
        for opcode in opcodes {
            let source = if matches!(opcode, "RET" | "FENCE" | "HALT") {
                format!("{opcode} 0\nHALT\n")
            } else {
                format!("{opcode}\nHALT\n")
            };
            let result = Program::parse(&source, 4, 64, 4096);
            assert!(matches!(result, Err(super::ProgramError::Parse { .. })));
        }
    }

    #[test]
    fn rejects_noncanonical_register_and_ambiguous_address_syntax() {
        for source in [
            "MOVI r01, 0\nHALT\n",
            "LOAD r0, [r1 + -1]\nHALT\n",
            "STORE [r1 - -1], r0\nHALT\n",
        ] {
            assert!(matches!(
                Program::parse(source, 4, 16, 128),
                Err(super::ProgramError::Parse { .. })
            ));
        }
    }

    #[test]
    fn rejects_profile_and_control_flow_violations() {
        let lane = Program::parse("PROBE 4, 0, 0\nHALT\n", 4, 8, 64);
        assert!(lane.is_err());
        let backward = Program::parse("a: PAD 1\nJMP a\nHALT\n", 1, 8, 64);
        assert!(matches!(
            backward,
            Err(super::ProgramError::Validation { .. })
        ));
        let ret = Program::parse("RET\nHALT\n", 1, 8, 64);
        assert!(matches!(ret, Err(super::ProgramError::Validation { .. })));
    }

    #[test]
    fn typed_construction_validates_every_operand_domain() {
        let invalid = [
            Instruction::MovI { dst: 8, value: 0 },
            Instruction::Shl {
                dst: 0,
                src: 0,
                amount: 16,
            },
            Instruction::Probe {
                lane: 4,
                token: 0,
                epoch: 0,
            },
            Instruction::Probe {
                lane: 0,
                token: 16,
                epoch: 0,
            },
            Instruction::Anchor { bank: 4, epoch: 0 },
            Instruction::Anchor { bank: 0, epoch: 2 },
        ];
        for instruction in invalid {
            let result = Program::new(vec![instruction, Instruction::Halt], 4, 8, 64);
            assert!(matches!(
                result,
                Err(super::ProgramError::Validation { .. })
            ));
        }
    }

    #[test]
    fn bounded_malformed_text_never_panics() {
        let mut state = 0x4d59_5df4_d0f3_3173_u64;
        for length in 0..512 {
            let mut source = String::with_capacity(length);
            for _ in 0..length {
                state = state
                    .wrapping_mul(6_364_136_223_846_793_005)
                    .wrapping_add(1_442_695_040_888_963_407);
                let byte = 0x20 + u8::try_from((state >> 32) % 95).unwrap_or_default();
                source.push(char::from(byte));
            }
            let _result = Program::parse(&source, 4, 128, 4096);
        }
    }

    #[test]
    fn agrees_with_cross_language_golden_corpus() {
        const SOURCE: &str = include_str!("../../../tests/fixtures/programs/full-v1.source.spx");
        const CANONICAL: &str =
            include_str!("../../../tests/fixtures/programs/full-v1.canonical.spx");
        const HASH: &str = include_str!("../../../tests/fixtures/programs/full-v1.sha256");
        const AST: &str = include_str!("../../../tests/fixtures/programs/full-v1.ast.json");
        let parsed = Program::parse(SOURCE, 4, 128, 4096);
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("golden program should validate: {error}"),
        };
        assert_eq!(program.render(), CANONICAL);
        assert_eq!(program.canonical_sha256(), HASH.trim());
        let ast = match program.canonical_ast_json() {
            Ok(value) => value,
            Err(error) => panic!("canonical AST serialization failed: {error}"),
        };
        assert_eq!(ast, AST.trim());
        let reparsed = Program::parse(CANONICAL, 4, 128, 4096);
        assert_eq!(reparsed, Ok(program));
    }
}
