//! Typed parser for the version-1 probe DSL.

/// An error produced while parsing or validating a probe program.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProgramError {
    /// A source line could not be parsed.
    Parse {
        /// One-based source line.
        line: usize,
        /// Human-readable parse diagnostic.
        message: String,
    },
    /// The program exceeds a profile limit.
    Limit(String),
    /// An instruction is syntactically recognized but not implemented by this scaffold.
    Unsupported {
        /// One-based source line.
        line: usize,
        /// Canonical opcode spelling.
        opcode: String,
    },
}

impl std::fmt::Display for ProgramError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Parse { line, message } => write!(formatter, "line {line}: {message}"),
            Self::Limit(message) => write!(formatter, "program limit: {message}"),
            Self::Unsupported { line, opcode } => {
                write!(
                    formatter,
                    "line {line}: unsupported scaffold opcode {opcode}"
                )
            }
        }
    }
}

impl std::error::Error for ProgramError {}

/// A typed instruction supported by the executable scaffold.
#[derive(Debug, Clone, PartialEq, Eq)]
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
    /// Logical left shift.
    Shl { dst: u8, src: u8, amount: u8 },
    /// Logical right shift.
    Shr { dst: u8, src: u8, amount: u8 },
    /// Mix a public register into the architectural digest.
    MixOut { src: u8 },
    /// Secret-dependent microarchitectural probe with no architectural effect.
    Probe { lane: usize, token: u8, epoch: u8 },
    /// Public reference-bank access with no architectural effect.
    Anchor { bank: u8, epoch: u8 },
    /// Advance timing phase by a public amount.
    Pad { amount: u16 },
    /// Drain replay state according to the public instruction contract.
    Fence,
    /// Stop execution.
    Halt,
}

impl Instruction {
    /// Return the documented fault-free static cost of the instruction.
    #[must_use]
    pub fn static_cycles(&self) -> u64 {
        match self {
            Self::MovI { .. } | Self::Mov { .. } | Self::MixOut { .. } | Self::Halt => 1,
            Self::Add { .. }
            | Self::Xor { .. }
            | Self::And { .. }
            | Self::Or { .. }
            | Self::Shl { .. }
            | Self::Shr { .. } => 2,
            Self::Probe { .. } => 5,
            Self::Anchor { .. } => 4,
            Self::Pad { amount } => u64::from(*amount),
            Self::Fence => 2,
        }
    }

    /// Render the instruction in canonical DSL syntax.
    #[must_use]
    pub fn render(&self) -> String {
        match self {
            Self::MovI { dst, value } => format!("MOVI r{dst}, {value}"),
            Self::Mov { dst, src } => format!("MOV r{dst}, r{src}"),
            Self::Add { dst, lhs, rhs } => format!("ADD r{dst}, r{lhs}, r{rhs}"),
            Self::Xor { dst, lhs, rhs } => format!("XOR r{dst}, r{lhs}, r{rhs}"),
            Self::And { dst, lhs, rhs } => format!("AND r{dst}, r{lhs}, r{rhs}"),
            Self::Or { dst, lhs, rhs } => format!("OR r{dst}, r{lhs}, r{rhs}"),
            Self::Shl { dst, src, amount } => format!("SHL r{dst}, r{src}, {amount}"),
            Self::Shr { dst, src, amount } => format!("SHR r{dst}, r{src}, {amount}"),
            Self::MixOut { src } => format!("MIXOUT r{src}"),
            Self::Probe { lane, token, epoch } => {
                format!("PROBE {lane}, {token}, {epoch}")
            }
            Self::Anchor { bank, epoch } => format!("ANCHOR {bank}, {epoch}"),
            Self::Pad { amount } => format!("PAD {amount}"),
            Self::Fence => "FENCE".to_owned(),
            Self::Halt => "HALT".to_owned(),
        }
    }
}

/// A validated, finite probe program.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Program {
    instructions: Vec<Instruction>,
}

impl Program {
    /// Parse a program and enforce profile-dependent static bounds.
    pub fn parse(
        source: &str,
        lanes: usize,
        max_instructions: usize,
        max_gas: u64,
    ) -> Result<Self, ProgramError> {
        let mut instructions = Vec::new();
        for (index, raw_line) in source.lines().enumerate() {
            let line_number = index + 1;
            let line = strip_comment(raw_line).trim();
            if line.is_empty() {
                continue;
            }
            let instruction_text = strip_optional_label(line);
            if instruction_text.is_empty() {
                continue;
            }
            instructions.push(parse_instruction(instruction_text, line_number, lanes)?);
            if instructions.len() > max_instructions {
                return Err(ProgramError::Limit(format!(
                    "more than {max_instructions} instructions"
                )));
            }
        }
        if instructions.is_empty() {
            return Err(ProgramError::Parse {
                line: 1,
                message: "program contains no instruction".to_owned(),
            });
        }
        let program = Self { instructions };
        let static_gas = program.static_cycles();
        if static_gas > max_gas {
            return Err(ProgramError::Limit(format!(
                "static cost {static_gas} exceeds max_gas {max_gas}"
            )));
        }
        Ok(program)
    }

    /// Borrow the instruction sequence.
    #[must_use]
    pub fn instructions(&self) -> &[Instruction] {
        &self.instructions
    }

    /// Return the public fault-free static cycle count.
    #[must_use]
    pub fn static_cycles(&self) -> u64 {
        self.instructions
            .iter()
            .map(Instruction::static_cycles)
            .sum()
    }

    /// Render a canonical text representation.
    #[must_use]
    pub fn render(&self) -> String {
        let mut output = String::new();
        for instruction in &self.instructions {
            output.push_str(&instruction.render());
            output.push('\n');
        }
        output
    }
}

fn strip_comment(line: &str) -> &str {
    let hash = line.find('#');
    let semicolon = line.find(';');
    match (hash, semicolon) {
        (Some(left), Some(right)) => &line[..left.min(right)],
        (Some(index), None) | (None, Some(index)) => &line[..index],
        (None, None) => line,
    }
}

fn strip_optional_label(line: &str) -> &str {
    match line.split_once(':') {
        Some((label, rest)) if is_identifier(label.trim()) => rest.trim(),
        _ => line,
    }
}

fn is_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    match chars.next() {
        Some(first) if first.is_ascii_alphabetic() || first == '_' => {
            chars.all(|character| character.is_ascii_alphanumeric() || character == '_')
        }
        _ => false,
    }
}

fn parse_instruction(source: &str, line: usize, lanes: usize) -> Result<Instruction, ProgramError> {
    let mut pieces = source.splitn(2, char::is_whitespace);
    let opcode = pieces.next().unwrap_or_default().to_ascii_uppercase();
    let operands = pieces.next().unwrap_or_default().trim();
    let args: Vec<&str> = if operands.is_empty() {
        Vec::new()
    } else {
        operands.split(',').map(str::trim).collect()
    };

    match opcode.as_str() {
        "MOVI" => {
            require_arity(&args, 2, line, &opcode)?;
            Ok(Instruction::MovI {
                dst: parse_register(args[0], line)?,
                value: parse_u16(args[1], line, "immediate")?,
            })
        }
        "MOV" => {
            require_arity(&args, 2, line, &opcode)?;
            Ok(Instruction::Mov {
                dst: parse_register(args[0], line)?,
                src: parse_register(args[1], line)?,
            })
        }
        "ADD" | "XOR" | "AND" | "OR" => {
            require_arity(&args, 3, line, &opcode)?;
            let dst = parse_register(args[0], line)?;
            let lhs = parse_register(args[1], line)?;
            let rhs = parse_register(args[2], line)?;
            match opcode.as_str() {
                "ADD" => Ok(Instruction::Add { dst, lhs, rhs }),
                "XOR" => Ok(Instruction::Xor { dst, lhs, rhs }),
                "AND" => Ok(Instruction::And { dst, lhs, rhs }),
                _ => Ok(Instruction::Or { dst, lhs, rhs }),
            }
        }
        "SHL" | "SHR" => {
            require_arity(&args, 3, line, &opcode)?;
            let dst = parse_register(args[0], line)?;
            let src = parse_register(args[1], line)?;
            let amount = parse_bounded_u8(args[2], line, "shift amount", 15)?;
            if opcode == "SHL" {
                Ok(Instruction::Shl { dst, src, amount })
            } else {
                Ok(Instruction::Shr { dst, src, amount })
            }
        }
        "MIXOUT" => {
            require_arity(&args, 1, line, &opcode)?;
            Ok(Instruction::MixOut {
                src: parse_register(args[0], line)?,
            })
        }
        "PROBE" => {
            require_arity(&args, 3, line, &opcode)?;
            let lane_value = parse_usize(args[0], line, "lane")?;
            if lane_value >= lanes {
                return Err(parse_error(
                    line,
                    format!("lane {lane_value} is outside 0..{lanes}"),
                ));
            }
            Ok(Instruction::Probe {
                lane: lane_value,
                token: parse_bounded_u8(args[1], line, "token", 15)?,
                epoch: parse_bounded_u8(args[2], line, "epoch", 1)?,
            })
        }
        "ANCHOR" => {
            require_arity(&args, 2, line, &opcode)?;
            Ok(Instruction::Anchor {
                bank: parse_bounded_u8(args[0], line, "bank", 3)?,
                epoch: parse_bounded_u8(args[1], line, "epoch", 1)?,
            })
        }
        "PAD" => {
            require_arity(&args, 1, line, &opcode)?;
            Ok(Instruction::Pad {
                amount: parse_u16(args[0], line, "padding")?,
            })
        }
        "FENCE" => {
            require_arity(&args, 0, line, &opcode)?;
            Ok(Instruction::Fence)
        }
        "HALT" => {
            require_arity(&args, 0, line, &opcode)?;
            Ok(Instruction::Halt)
        }
        "LOAD" | "STORE" | "CMP" | "JMP" | "JZ" | "JNZ" | "CALL" | "RET" | "LOOP" => {
            Err(ProgramError::Unsupported { line, opcode })
        }
        _ => Err(parse_error(line, format!("unknown opcode {opcode}"))),
    }
}

fn require_arity(
    args: &[&str],
    expected: usize,
    line: usize,
    opcode: &str,
) -> Result<(), ProgramError> {
    if args.len() == expected {
        Ok(())
    } else {
        Err(parse_error(
            line,
            format!("{opcode} expects {expected} operands, got {}", args.len()),
        ))
    }
}

fn parse_register(value: &str, line: usize) -> Result<u8, ProgramError> {
    let index = value
        .strip_prefix('r')
        .or_else(|| value.strip_prefix('R'))
        .ok_or_else(|| parse_error(line, format!("invalid register {value}")))?;
    parse_bounded_u8(index, line, "register", 7)
}

fn parse_u16(value: &str, line: usize, role: &str) -> Result<u16, ProgramError> {
    let parsed = parse_integer(value, line, role)?;
    u16::try_from(parsed).map_err(|_| parse_error(line, format!("{role} {value} is not u16")))
}

fn parse_usize(value: &str, line: usize, role: &str) -> Result<usize, ProgramError> {
    let parsed = parse_integer(value, line, role)?;
    usize::try_from(parsed)
        .map_err(|_| parse_error(line, format!("{role} {value} is not non-negative")))
}

fn parse_bounded_u8(value: &str, line: usize, role: &str, maximum: u8) -> Result<u8, ProgramError> {
    let parsed = parse_integer(value, line, role)?;
    let converted =
        u8::try_from(parsed).map_err(|_| parse_error(line, format!("{role} {value} is not u8")))?;
    if converted > maximum {
        return Err(parse_error(
            line,
            format!("{role} {converted} exceeds {maximum}"),
        ));
    }
    Ok(converted)
}

fn parse_integer(value: &str, line: usize, role: &str) -> Result<i64, ProgramError> {
    let (negative, magnitude) = value
        .strip_prefix('-')
        .map_or((false, value), |rest| (true, rest));
    let parsed = if let Some(hex) = magnitude
        .strip_prefix("0x")
        .or_else(|| magnitude.strip_prefix("0X"))
    {
        i64::from_str_radix(hex, 16)
    } else {
        magnitude.parse::<i64>()
    }
    .map_err(|_| parse_error(line, format!("invalid {role} {value}")))?;
    Ok(if negative { -parsed } else { parsed })
}

fn parse_error(line: usize, message: String) -> ProgramError {
    ProgramError::Parse { line, message }
}

#[cfg(test)]
mod tests {
    use super::{Instruction, Program};

    #[test]
    fn parses_and_canonicalizes_experiment_program() {
        let parsed = Program::parse(
            "# comment\nPROBE 0, 3, 1\nPAD 2\nANCHOR 1, 1\nHALT\n",
            4,
            16,
            100,
        );
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("test program should parse: {error}"),
        };
        assert_eq!(program.instructions().len(), 4);
        assert_eq!(program.static_cycles(), 12);
        assert!(matches!(
            program.instructions()[0],
            Instruction::Probe {
                lane: 0,
                token: 3,
                epoch: 1
            }
        ));
        assert!(program.render().ends_with("HALT\n"));
    }

    #[test]
    fn rejects_out_of_range_lane() {
        let parsed = Program::parse("PROBE 4, 0, 0\nHALT\n", 4, 16, 100);
        let error = match parsed {
            Ok(_) => panic!("lane four should be out of range"),
            Err(error) => error,
        };
        assert!(error.to_string().contains("outside"));
    }
}
